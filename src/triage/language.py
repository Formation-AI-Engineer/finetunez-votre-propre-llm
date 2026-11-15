"""Détection d'un message patient en anglais.

Le triage n'est entraîné et validé qu'en français, et les drapeaux rouges sur le texte sont écrits
en français : un message en anglais part directement à l'IOA (test de robustesse du 15/11/2026,
douleur thoracique en anglais sans niveau et avec le numéro « 911 »).

Règle volontairement prudente, sur les mots outils : au moins 3 mots outils anglais et plus de
deux fois plus que de mots outils français. Un message court en style télégraphique français
(« fièvre, toux, courbatures ») n'est donc jamais pris pour de l'anglais. Les autres langues ne
sont pas détectées : limite documentée.
"""

from __future__ import annotations

import re

_ENGLISH = frozenset(
    [
        "the",
        "and",
        "i",
        "i'm",
        "i've",
        "my",
        "me",
        "is",
        "are",
        "was",
        "have",
        "has",
        "had",
        "it",
        "it's",
        "with",
        "for",
        "of",
        "to",
        "you",
        "your",
        "can",
        "can't",
        "since",
        "this",
        "that",
        "be",
        "been",
        "feel",
        "feeling",
        "pain",
        "hurts",
        "hurt",
        "very",
        "not",
        "don't",
        "no",
        "yes",
        "what",
        "when",
    ]
)
_FRENCH = frozenset(
    [
        "le",
        "la",
        "les",
        "et",
        "je",
        "j'",
        "mon",
        "ma",
        "mes",
        "est",
        "sont",
        "ai",
        "a",
        "avec",
        "pour",
        "dans",
        "de",
        "des",
        "du",
        "un",
        "une",
        "pas",
        "mal",
        "depuis",
        "il",
        "elle",
        "ce",
        "cette",
        "ça",
        "très",
        "me",
        "m'",
        "suis",
        "j'ai",
        "au",
        "aux",
        "sur",
        "ne",
        "n'",
        "qui",
        "que",
    ]
)
_WORD = re.compile(r"[a-zàâäçéèêëîïôöùûüÿœ]+(?:'[a-z]+)?|[a-zàâäçéèêëîïôöùûüÿœ]+'", re.IGNORECASE)


def is_english(text: str) -> bool:
    words = [w.lower() for w in _WORD.findall(text)]
    english = sum(w in _ENGLISH for w in words)
    french = sum(w in _FRENCH or w.split("'")[0] + "'" in _FRENCH for w in words)
    return english >= 3 and english > 2 * french
