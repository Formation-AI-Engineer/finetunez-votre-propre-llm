"""Métriques d'évaluation et seuils d'acceptation (définitions détaillées : docs/EVALUATION.md).

Fonctions pures, sans dépendance GPU : elles prennent les niveaux attendus et les réponses déjà
lues (`triage.output.parse_assessment`, `parse_mcq`) et renvoient des taux avec leur intervalle
de confiance. Une réponse illisible n'est jamais ignorée : elle compte comme une erreur, et comme
un sous-triage si le cas n'était pas de priorité différée.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from triage.data.schema import PriorityLevel
from triage.output import Assessment

PRIORITIES: tuple[PriorityLevel, ...] = ("maximale", "moderee", "differee")
INVALID = "invalide"

# « Bonne réponse : A » ou « Bonnes réponses : A, C et E », sur une seule ligne.
_MCQ_HEADER = re.compile(
    r"[Bb]onnes? [Rr]éponses?[ \t]*:[ \t]*([A-E](?:[ \t]*(?:,|;|/|et)[ \t]*[A-E])*)\b"
)
# Lecture tolérante, pour mesurer les connaissances d'un modèle qui n'a pas appris le format :
# « Réponse : c », « La réponse correcte est : **B. … »,  « Réponses : a, d ». La lettre ne doit pas
# commencer un mot (« Réponse : La … » n'est pas lu comme A).
_MCQ_LENIENT = re.compile(
    r"[Rr]éponses?(?:[ \t]+(?:correctes?|exactes?|justes?))?(?:[ \t]+(?:est|sont))?[ \t]*:"
    r"[ \t]*\**[ \t]*([A-Ea-e](?:[ \t]*(?:,|;|/|et)[ \t]*[A-Ea-e])*)(?![A-Za-zÀ-ÿ'’])"
)


@dataclass(frozen=True)
class Rate:
    """Proportion k / n et son intervalle de confiance de Wilson à 95 %."""

    k: int
    n: int

    @property
    def value(self) -> float:
        return self.k / self.n if self.n else math.nan

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.k, self.n)

    def __str__(self) -> str:
        low, high = self.interval
        return f"{self.value:.1%} [{low:.1%} ; {high:.1%}] ({self.k}/{self.n})"


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de Wilson : reste valable pour les petits effectifs et les taux proches de 0,
    là où l'intervalle « ± 1,96 × écart-type » sortirait de [0, 1]."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, center - half), min(1.0, center + half))


# ------------------------------------------------------------------------------- triage


@dataclass(frozen=True)
class TriageScores:
    accuracy: Rate
    under_triage_maximale: Rate
    under_triage: Rate
    over_triage: Rate
    format_ok: Rate
    confusion: dict[str, dict[str, int]]


def _rank(priority: str) -> int:
    return PRIORITIES.index(priority)


def triage_scores(
    expected: Sequence[PriorityLevel], predicted: Sequence[Assessment | None]
) -> TriageScores:
    """Compare les priorités attendues aux réponses lues (None = réponse illisible)."""
    if len(expected) != len(predicted):
        raise ValueError("autant de réponses que de cas attendus")
    n = len(expected)
    confusion = {e: {p: 0 for p in (*PRIORITIES, INVALID)} for e in PRIORITIES}
    correct = under = over = valid = 0
    maximale = missed_maximale = 0
    for exp, pred in zip(expected, predicted, strict=True):
        got = pred.priority if pred else INVALID
        confusion[exp][got] += 1
        # Une réponse illisible laisse le patient sans priorité : sous-triage, sauf s'il était
        # déjà au niveau le plus bas.
        is_under = exp != "differee" if got == INVALID else _rank(got) > _rank(exp)
        valid += got != INVALID
        correct += got == exp
        under += is_under
        over += got != INVALID and _rank(got) < _rank(exp)
        if exp == "maximale":
            maximale += 1
            missed_maximale += got != "maximale"
    return TriageScores(
        accuracy=Rate(correct, n),
        under_triage_maximale=Rate(missed_maximale, maximale),
        under_triage=Rate(under, n),
        over_triage=Rate(over, n),
        format_ok=Rate(valid, n),
        confusion=confusion,
    )


def format_confusion(confusion: dict[str, dict[str, int]]) -> str:
    """Matrice de confusion en tableau Markdown : lignes = attendu, colonnes = prédit."""
    columns = (*PRIORITIES, INVALID)
    lines = [
        "| attendu \\ prédit | " + " | ".join(columns) + " |",
        "|---" * (len(columns) + 1) + "|",
    ]
    for exp, row in confusion.items():
        lines.append(f"| {exp} | " + " | ".join(str(row[c]) for c in columns) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------- QCM


@dataclass(frozen=True)
class MCQScores:
    exact_match: Rate
    hamming: float
    format_ok: Rate


def parse_mcq(text: str) -> frozenset[str] | None:
    """Lettres annoncées après « Bonne(s) réponse(s) : », ou None si le format n'est pas suivi."""
    match = _MCQ_HEADER.search(text)
    if not match:
        return None
    return frozenset(re.findall(r"[A-E]", match.group(1)))


def parse_mcq_lenient(text: str) -> frozenset[str] | None:
    """Lettres de la première « réponse : X » du texte, quel que soit le format exact."""
    match = _MCQ_HEADER.search(text) or _MCQ_LENIENT.search(text)
    if not match:
        return None
    letters = re.sub(r"\bet\b", " ", match.group(1)).upper()
    return frozenset(re.findall(r"[A-E]", letters))


def mcq_scores(
    expected: Sequence[frozenset[str]], predicted: Sequence[frozenset[str] | None]
) -> MCQScores:
    """Exact match (toutes les bonnes lettres, rien de plus) et score de Hamming
    (|A ∩ B| / |A ∪ B|, crédit partiel), les métriques d'usage pour les QCM à réponses multiples
    comme FrenchMedMCQA."""
    if len(expected) != len(predicted):
        raise ValueError("autant de réponses que de questions")
    exact = valid = 0
    hamming = 0.0
    for exp, pred in zip(expected, predicted, strict=True):
        if pred is None:
            continue
        valid += 1
        exact += pred == exp
        hamming += len(exp & pred) / len(exp | pred) if exp | pred else 1.0
    n = len(expected)
    return MCQScores(
        exact_match=Rate(exact, n),
        hamming=hamming / n if n else math.nan,
        format_ok=Rate(valid, n),
    )


# ----------------------------------------------------------------- seuils d'acceptation


@dataclass(frozen=True)
class Threshold:
    metric: str
    description: str
    limit: float
    higher_is_better: bool

    def passes(self, value: float) -> bool:
        return value >= self.limit if self.higher_is_better else value <= self.limit


# Propositions à valider avec le mentor (docs/TACHES.md, étape 2). La décision se prend sur la
# valeur mesurée ; l'intervalle de confiance est toujours rapporté à côté.
ACCEPTANCE = (
    Threshold("under_triage_maximale", "Sous-triage des cas de priorité maximale", 0.05, False),
    Threshold("accuracy", "Exactitude à 3 niveaux sur les vignettes", 0.75, True),
)


def check_acceptance(scores: TriageScores) -> dict[str, bool | None]:
    """Seuil atteint ou non ; None si la métrique n'a pas pu être mesurée (aucun cas)."""
    result: dict[str, bool | None] = {}
    for t in ACCEPTANCE:
        rate = getattr(scores, t.metric)
        result[t.metric] = t.passes(rate.value) if rate.n else None
    return result
