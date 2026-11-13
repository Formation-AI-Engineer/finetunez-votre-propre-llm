"""Garde-fou de cohérence : le critère FRENCH cité par le modèle contre le niveau annoncé.

Le modèle cite un motif (« Motif de recours : … ») et un critère (« Critère FRENCH : « … » »).
Quand les deux correspondent à une ligne de la table FRENCH (configs/french_table.json), le
niveau de cette ligne sert de plancher : le niveau final n'est jamais moins grave que celui du
critère que le modèle a lui-même retenu. Exemple observé : « dyspnée à la parole » cité
(tri 2) avec une priorité DIFFÉRÉE.

La correspondance est approximative (indice de Jaccard sur les mots, accents et mots vides
retirés), car le modèle recopie les libellés avec des variantes. Un motif ou un critère
inventé (absent de la table) ne déclenche rien : ce garde-fou ne rattrape pas les
hallucinations, seulement les contradictions internes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from triage.data.schema import FRENCH_TO_PRIORITY
from triage.output import Assessment

TABLE_PATH = Path("configs/french_table.json")
MIN_SIMILARITY = 0.5
_ORDER = ("maximale", "moderee", "differee")
_STOPWORDS = frozenset(
    [
        "de",
        "du",
        "des",
        "la",
        "le",
        "les",
        "et",
        "ou",
        "à",
        "a",
        "au",
        "aux",
        "en",
        "d",
        "l",
        "un",
        "une",
        "avec",
        "par",
        "pour",
        "sur",
    ]
)
# Une négation présente d'un seul côté inverse le sens : « FC 40-50/min sans mauvaise
# tolérance » (réponse de référence, tri 3B) ne doit pas correspondre à « FC 40-50/min avec
# mauvaise tolérance » (tri 2).
_NEGATIONS = frozenset({"sans", "pas", "non", "absence", "aucun", "aucune"})
_MOTIF = re.compile(r"Motif de recours\s*:\s*(.+)")
_CRITERION = re.compile(r"Critère FRENCH\s*:\s*«\s*(.+?)\s*»")


@dataclass(frozen=True)
class CitedCriterion:
    motif: str
    criterion: str
    level: str
    similarity: float


def _words(text: str) -> frozenset[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Les signes de comparaison comptent : « PAS 90 - 100 mmHg et FC ≤ 100/min » (tri 3B) contre
    # « … FC > 100/min » (tri 2).
    words = re.findall(r"[a-z0-9]+|[≤≥<>]", text)
    return frozenset(w for w in words if len(w) > 1 or not w.isalnum()) - _STOPWORDS


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b or (a & _NEGATIONS) != (b & _NEGATIONS):
        return 0.0
    return len(a & b) / len(a | b)


def _closest(text: str, keys: list[str]) -> tuple[str | None, float]:
    words = _words(text)
    best, best_score = None, 0.0
    for key in keys:
        score = _jaccard(words, _words(key))
        if score > best_score:
            best, best_score = key, score
    return (best, best_score) if best_score >= MIN_SIMILARITY else (None, best_score)


@cache
def _table(path: Path = TABLE_PATH) -> dict[str, dict[str, str]]:
    """Motif -> {critère: niveau} (la table range les critères par niveau)."""
    motifs = json.loads(path.read_text(encoding="utf-8"))["motifs"]
    return {m["name"]: {text: level for level, text in m["criteria"].items()} for m in motifs}


def cited_criterion(answer: str) -> CitedCriterion | None:
    """Ligne de la table FRENCH citée par la réponse, ou None si le motif ou le critère cité
    n'y figure pas."""
    motif_match, criterion_match = _MOTIF.search(answer), _CRITERION.search(answer)
    if not motif_match or not criterion_match:
        return None
    table = _table()
    motif, _ = _closest(motif_match.group(1), list(table))
    if motif is None:
        return None
    criterion, similarity = _closest(criterion_match.group(1), list(table[motif]))
    if criterion is None:
        return None
    return CitedCriterion(motif, criterion, table[motif][criterion], round(similarity, 2))


def consistency_floor(answer: str, assessment: Assessment | None) -> Assessment | None:
    """Priorité relevée au niveau du critère cité s'il est plus grave. Une réponse illisible
    reste illisible."""
    cited = cited_criterion(answer)
    if assessment is None or cited is None:
        return assessment
    cited_priority = FRENCH_TO_PRIORITY[cited.level]
    if _ORDER.index(cited_priority) < _ORDER.index(assessment.priority):
        return Assessment(priority=cited_priority, french_level=cited.level)
    return assessment
