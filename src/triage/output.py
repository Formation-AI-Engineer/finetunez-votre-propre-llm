"""Lecture de la réponse de triage produite par le modèle."""

from __future__ import annotations

import re
from dataclasses import dataclass

from triage.data.schema import FRENCH_TO_PRIORITY, PriorityLevel

_HEADER = re.compile(
    r"Niveau de priorité\s*:\s*(MAXIMALE|MODÉRÉE|MODEREE|DIFFÉRÉE|DIFFEREE)"
    r"(?:\s*\(tri FRENCH\s*(1|2|3A|3B|4|5)\))?",
    re.IGNORECASE,
)
_PRIORITY = {
    "maximale": "maximale",
    "modérée": "moderee",
    "moderee": "moderee",
    "différée": "differee",
    "differee": "differee",
}


@dataclass(frozen=True)
class Assessment:
    priority: PriorityLevel
    french_level: str | None


def parse_assessment(text: str) -> Assessment | None:
    """Niveau annoncé par la réponse, ou None si elle ne suit pas le format attendu.

    Si le tri FRENCH contredit la priorité annoncée, on retient la plus grave des deux.
    """
    match = _HEADER.search(text)
    if not match:
        return None
    priority = _PRIORITY[match.group(1).lower()]
    level = match.group(2).upper() if match.group(2) else None
    if level and FRENCH_TO_PRIORITY[level] != priority:
        order = ("maximale", "moderee", "differee")
        priority = min(priority, FRENCH_TO_PRIORITY[level], key=order.index)
    return Assessment(priority=priority, french_level=level)
