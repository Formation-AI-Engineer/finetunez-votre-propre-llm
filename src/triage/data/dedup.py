"""Clés de dédoublonnage et contrôle de fuite entre jeux."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from triage.data.schema import DPORecord, SFTRecord

Record = SFTRecord | DPORecord


def normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation ni espaces multiples."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def question_text(record: Record) -> str:
    """Contenu des messages utilisateur, hors prompt système."""
    return "\n".join(m.content for m in record.prompt if m.role == "user")


def question_key(record: Record) -> str:
    return hashlib.sha256(normalize(question_text(record)).encode()).hexdigest()


def drop_duplicates(records: list[Record]) -> tuple[list[Record], int]:
    """Garde la première occurrence de chaque question normalisée."""
    seen: set[str] = set()
    kept = []
    for record in records:
        key = question_key(record)
        if key not in seen:
            seen.add(key)
            kept.append(record)
    return kept, len(records) - len(kept)


def drop_overlap(records: list[Record], forbidden: set[str]) -> tuple[list[Record], int]:
    """Retire les enregistrements dont la question figure dans un jeu d'évaluation."""
    kept = [r for r in records if question_key(r) not in forbidden]
    return kept, len(records) - len(kept)


def overlap(a: list[Record], b: list[Record]) -> int:
    return len({question_key(r) for r in a} & {question_key(r) for r in b})
