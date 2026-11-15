"""Anonymisation des textes avec Presidio (spaCy fr_core_news_md et en_core_web_md).

Choix, justifiés dans docs/RGPD.md :
- entités masquées : personnes, téléphones, e-mails, NIR, IBAN, cartes bancaires, adresses IP,
  dates explicites (jour, mois et année) ;
- entités conservées : lieux (un séjour au Gabon est une information clinique) et durées
  relatives (« depuis 3 jours ») ;
- stratégie « replace » : l'entité devient une balise typée (<PERSONNE>), ce qui garde la phrase
  lisible sans révéler la longueur de la valeur (contrairement à « mask ») ;
- les éponymes médicaux (Parkinson, Guillain-Barré…) ne sont pas des personnes ;
- un nom détecté par spaCy n'est retenu que dans un contexte de nom (civilité, présentation, lien
  de parenté) : sur du texte médical, spaCy prend aussi pour des personnes des termes comme
  « Splénomégalie » ou « Rhabdomyosarcoma », et les lettres d'options de QCM (« D. Est »).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    CreditCardRecognizer,
    EmailRecognizer,
    IbanRecognizer,
    IpRecognizer,
    PhoneRecognizer,
)
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

LANGUAGES = ("fr", "en")
SCORE_THRESHOLD = 0.5

TAGS = {
    "PERSON": "<PERSONNE>",
    "PHONE_NUMBER": "<TELEPHONE>",
    "EMAIL_ADDRESS": "<EMAIL>",
    "FR_NIR": "<NIR>",
    "IBAN_CODE": "<IBAN>",
    "CREDIT_CARD": "<CARTE_BANCAIRE>",
    "IP_ADDRESS": "<IP>",
    "EXPLICIT_DATE": "<DATE>",
    "TITLED_PERSON": "<PERSONNE>",
}

EPONYMS_PATH = Path("configs/eponymes.txt")
EPONYMS = frozenset(
    line.strip()
    for line in EPONYMS_PATH.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
)
EPONYM_CONTEXT = re.compile(
    r"(maladie|syndrome|signe|score|test|manœuvre|manoeuvre|classification|échelle|bacille|"
    r"disease|syndrome|sign|score|test|maneuver|scale|classification)\s+(de\s+|d'|of\s+)?$",
    re.IGNORECASE,
)

_TITLES = (
    r"m\.|mr\.?|mrs\.?|ms\.?|mme|mlle|monsieur|madame|mademoiselle|dr\.?|docteur|doctor|"
    r"pr\.?|professeur|prof\.?"
)
_INTRODUCTIONS = (
    r"je m'appelle|je suis|my name is|i am|i'm|this is|my ?self|"
    r"thanks?|thank you|regards|sincerely|merci|cordialement|bien à vous|director:"
)
_RELATIVES = (
    r"mari|femme|épouse|époux|fils|fille|frère|sœur|soeur|père|mère|ami|amie|voisine?|"
    r"husband|wife|son|daughter|brother|sister|father|mother|friend|neighbou?r|boyfriend|"
    r"girlfriend|baby"
)
# Ce qui doit précéder un nom détecté par spaCy pour qu'il soit retenu.
NAME_CONTEXT = re.compile(
    rf"(\b({_TITLES})|\b({_INTRODUCTIONS})|\b(mon|ma|sa|son|my|his|her|our)\s+({_RELATIVES}))"
    r"\s*,?\s*$",
    re.IGNORECASE,
)
OPTION_LETTER = re.compile(r"^(-\s*)?[A-Ea-e][.)]\s")
SENTENCE_START = re.compile(r"(^|[.!\n]\s*|,\s+)$")
TITLE_AFTER = re.compile(r"\s*,?\s*(M\.D\.|MD\b|Ph\.?D|R\.?N\.)")
# Civilité suivie d'un nom capitalisé, indépendamment de spaCy.
TITLED_PERSON_PATTERN = Pattern(
    "civilite_nom",
    r"\b(?:M\.|Mr\.?|Mrs\.?|Ms\.?|Mme|Mlle|Monsieur|Madame|Mademoiselle|Dr\.?|Docteur|"
    r"Pr\.?|Professeur)\s+(?!(?:La|Le|Les|Un|Une|Il|Elle|Ce|The|My|Here|Ordered|Advised|Said|"
    r"Told|Suggested|Prescribed|Is|Was|Has|Gave|Asked)\b)"
    r"[A-ZÉÈÀ][a-zà-ÿ'-]+(?:[ -][A-ZÉÈÀ][a-zà-ÿ'-]+)?",
    0.7,
)

_MONTHS = (
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|"
    "décembre|decembre|january|february|march|april|may|june|july|august|september|october|"
    "november|december"
)
DATE_PATTERNS = [
    Pattern("date_numerique", r"\b\d{1,2}[/.-]\d{1,2}[/.-](19|20)\d{2}\b", 0.8),
    Pattern("date_iso", r"\b(19|20)\d{2}-\d{2}-\d{2}\b", 0.8),
    Pattern("date_textuelle", rf"\b\d{{1,2}}(er)?\s+({_MONTHS})\s+(19|20)\d{{2}}\b", 0.8),
    Pattern("date_anglaise", rf"\b({_MONTHS})\s+\d{{1,2}},?\s+(19|20)\d{{2}}\b", 0.8),
]
# Le PhoneRecognizer de Presidio score ces formats à 0,4, sous le seuil : motifs explicites.
PHONE_PATTERNS = [
    Pattern("telephone_fr", r"(?<!\d)(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}(?!\d)", 0.7),
    Pattern("telephone_nanp", r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)", 0.7),
]
NIR_PATTERN = Pattern(
    "nir",
    r"\b[12]\s?\d{2}\s?(0[1-9]|1[0-2])\s?(\d{2}|2[AB])\s?\d{3}\s?\d{3}(\s?\d{2})?\b",
    0.7,
)


@dataclass(frozen=True)
class Finding:
    entity: str
    text: str
    score: float


@lru_cache(maxsize=1)
def _engines() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "fr", "model_name": "fr_core_news_md"},
                {"lang_code": "en", "model_name": "en_core_web_md"},
            ],
        }
    )
    analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=LANGUAGES)
    for lang in LANGUAGES:
        # Les reconnaisseurs à motifs prédéfinis ne sont chargés qu'en anglais par défaut.
        if lang != "en":
            for recognizer in (
                EmailRecognizer,
                IbanRecognizer,
                IpRecognizer,
                CreditCardRecognizer,
            ):
                analyzer.registry.add_recognizer(recognizer(supported_language=lang))
            analyzer.registry.add_recognizer(
                PhoneRecognizer(supported_language=lang, supported_regions=("FR", "US", "GB"))
            )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="EXPLICIT_DATE", patterns=DATE_PATTERNS, supported_language=lang
            )
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="PHONE_NUMBER", patterns=PHONE_PATTERNS, supported_language=lang
            )
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="TITLED_PERSON",
                patterns=[TITLED_PERSON_PATTERN],
                supported_language=lang,
                # Presidio ignore la casse par défaut : la majuscule du nom est indispensable.
                global_regex_flags=re.DOTALL | re.MULTILINE,
            )
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="FR_NIR", patterns=[NIR_PATTERN], supported_language=lang
            )
        )
    return analyzer, AnonymizerEngine()


def is_eponym(text: str, start: int, end: int) -> bool:
    words = re.split(r"[\s\-']+", text[start:end].lower())
    if any(word.strip(".,;:") in EPONYMS for word in words):
        return True
    return bool(EPONYM_CONTEXT.search(text[max(0, start - 30) : start]))


def is_person(text: str, start: int, end: int) -> bool:
    """Un nom détecté par spaCy est retenu s'il suit un contexte de nom et n'est pas un éponyme."""
    if is_eponym(text, start, end):
        return False
    if OPTION_LETTER.match(text[start:end]):
        return False
    if NAME_CONTEXT.search(text[max(0, start - 40) : start]):
        return True
    after = text[end:]
    if TITLE_AFTER.match(after):
        return True
    # Signature : nom d'au moins deux mots qui ouvre la dernière phrase du message. Exclut les
    # options de QCM (« E. Leucopénie ») et les fins de question (« How to diagnose X ? »).
    span = text[start:end]
    return (
        len(span.split()) >= 2
        and not OPTION_LETTER.match(span)
        and bool(SENTENCE_START.search(text[max(0, start - 3) : start]) or start == 0)
        and len(after.strip()) <= 40
        and "?" not in after
    )


def analyze(text: str, language: str) -> list[RecognizerResult]:
    analyzer, _ = _engines()
    results = analyzer.analyze(
        text=text, language=language, entities=list(TAGS), score_threshold=SCORE_THRESHOLD
    )
    return [r for r in results if r.entity_type != "PERSON" or is_person(text, r.start, r.end)]


def anonymize(text: str, language: str) -> tuple[str, list[Finding]]:
    """Texte anonymisé et liste des entités remplacées."""
    results = analyze(text, language)
    if not results:
        return text, []
    _, anonymizer = _engines()
    operators = {
        entity: OperatorConfig("replace", {"new_value": tag}) for entity, tag in TAGS.items()
    }
    output = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    findings = [Finding(r.entity_type, text[r.start : r.end], round(r.score, 2)) for r in results]
    return output.text, findings
