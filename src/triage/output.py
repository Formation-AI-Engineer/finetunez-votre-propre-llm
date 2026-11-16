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


_LOOSE_LEVEL = re.compile(r"tri\s+FRENCH\s*:?\s*(1|2|3A|3B|4|5)\b", re.IGNORECASE)
# « niveau » seul : « Vous êtes à niveau modérée » (test sur le vrai modèle du 16/11/2026), qui
# restait lu comme une question et faisait tourner le questionnaire en boucle.
_LOOSE_PRIORITY = re.compile(
    r"(?:priorit[ée]|\bniveau)\s*:?\s*(?:est\s+)?(maximale?|mod[ée]r[ée]e?|diff[ée]r[ée]e?)\b",
    re.IGNORECASE,
)


def parse_loose(text: str) -> Assessment | None:
    """Lecture de secours, pour le service seulement : niveau annoncé hors du format attendu
    (« niveau de priorité maximal (tri FRENCH 2) », vu en démonstration le 15/11/2026, ou
    « Vous êtes à niveau modérée », vu le 16/11/2026).

    L'évaluation et le jeu de sécurité gardent le format strict (`parse_assessment`) : un format
    non respecté y compte comme une erreur, et les métriques publiées restent comparables.
    """
    level_match = _LOOSE_LEVEL.search(text)
    priority_match = _LOOSE_PRIORITY.search(text)
    if not level_match and not priority_match:
        return None
    level = level_match.group(1).upper() if level_match else None
    candidates = [FRENCH_TO_PRIORITY[level]] if level else []
    if priority_match:
        word = priority_match.group(1).lower()
        candidates.append(
            "maximale"
            if word.startswith("max")
            else "moderee"
            if word.startswith("mod")
            else "differee"
        )
    order = ("maximale", "moderee", "differee")
    return Assessment(priority=min(candidates, key=order.index), french_level=level)
