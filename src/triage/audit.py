"""Journal d'audit des échanges (JSON Lines, une ligne par tour).

Chaque ligne : horodatage UTC, session (identifiant aléatoire, sans lien avec le patient), tour,
modèle, message envoyé et réponse, niveau du modèle et niveau final, garde-fous déclenchés,
alertes, latence. Les textes sont **masqués** avant écriture : courriels, téléphones, numéros de
sécurité sociale, dates, et nom après « je m'appelle », « Mme », « M. »… Ce masquage par
expressions régulières ne garantit pas l'anonymat (un nom cité autrement passe) : en production,
il faudrait l'anonymiseur Presidio de l'étape 1 et un hébergement HDS (docs/RGPD.md).
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from triage.service import TriageResult

_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<EMAIL>"),
    (re.compile(r"(?:\+33\s?|\b0)[1-9](?:[\s.-]?\d{2}){4}\b"), "<TELEPHONE>"),
    (re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b"), "<NIR>"),
    (re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"), "<DATE>"),
    (
        re.compile(
            r"(?i:\b(?:je m'appelle|je suis|mon nom est|nom\s*:|madame|monsieur|mme|mlle|m\.|"
            r"dr|docteur))\s+((?:[A-ZÉÈÀÂÎÔÛÇ][\w'-]+\s?){1,3})"
        ),
        None,
    ),
]


def scrub(text: str) -> str:
    for pattern, label in _PATTERNS:
        if label is None:  # nom propre après une formule : seul le nom est masqué
            text = pattern.sub(lambda m: m.group(0).replace(m.group(1).strip(), "<NOM>"), text)
        else:
            text = pattern.sub(label, text)
    return text


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(self, result: TriageResult, request: dict) -> None:
        """`request` : message du patient, âge, constantes et observation de l'IOA."""
        entry = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            **{k: v for k, v in asdict(result).items() if k not in ("message", "disclaimer")},
            "age_years": request.get("age_years"),
            "vitals": request.get("vitals"),
            "user_message": scrub(request["message"]),
            "observation": scrub(request["observation"]) if request.get("observation") else None,
            "answer": scrub(result.message),
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read(self, session_id: str | None = None, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        entries = [json.loads(line) for line in lines if line]
        if session_id is not None:
            entries = [e for e in entries if e["session_id"] == session_id]
        return entries[-limit:]
