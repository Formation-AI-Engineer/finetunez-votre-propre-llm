"""Drapeaux rouges sur le texte du patient : critères FRENCH de tri 1 et 2 dits en langage courant.

Troisième garde-fou, après les constantes et la cohérence du critère cité : si le récit contient
un signe de gravité, son niveau sert de plancher. Il rattrape les cas où le modèle reconnaît mal
le motif, ou se laisse convaincre par le patient (docs/EVALUATION.md, jeu de sécurité).

Chaque drapeau est une conjonction d'expressions (toutes doivent apparaître), sur le texte mis en
minuscules et sans accents. Les règles viennent des lignes de configs/french_table.json ; elles
ont été écrites après le premier jeu de sécurité (qui les a inspirées) et après la rédaction du
second (configs/safety_cases_v2.yaml), sur lequel elles sont mesurées. Leur auteur connaissait
donc les deux jeux : le second en surestime probablement le rappel. Les fausses alertes sont
contrôlées sur les vignettes de validation et sur les « faux amis » du second jeu.

Une expression précédée de près par une négation (« sans idée suicidaire », « pas de grossesse
possible ») ne compte pas. Certaines lignes ont une exclusion tirée du critère FRENCH de moindre
gravité : déficit ou membre froid depuis plusieurs jours (≥ 24 h, tri 3B), saignement abondant
arrêté (résolutif, tri 3B), intoxication vue tard (≥ 24 h, tri 5).

Ajustées sur les vignettes d'entraînement seulement (négations, exclusions) ; la validation et le
test ne servent qu'à mesurer. Limites : négations simples seulement ; français seulement. Un
drapeau ne fait que relever le niveau : une fausse alerte coûte un sur-triage, que l'IOA corrige.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class RedFlag:
    name: str
    level: str  # tri FRENCH imposé
    motif: str  # ligne de la table FRENCH
    patterns: tuple[str, ...]  # toutes doivent apparaître, sans négation juste avant
    unless: str | None = None  # exclusion : critère FRENCH de moindre gravité (durée, arrêt…)


_ARM_FACE = r"(bras|jambe|main|visage|bouche|cote du corps|moitie du corps)"
_DAYS = r"depuis (deux|trois|quatre|cinq|plusieurs|quelques|\d+) (jours|semaines|mois)"
_NEGATION = re.compile(r"(sans|pas d'|pas de|pas|aucune?|ni|absence d[e']|nie)\s*(\w+\s+){0,2}$")
FLAGS = (
    RedFlag(
        "douleur thoracique typique",
        "2",
        "Douleur thoracique/ syndrome coronaire aigu (SCA)",
        (
            r"(poitrine|thorax|thoracique)",
            r"(serre|oppression|poids|etau|ecrase|sueur|transpir|bras gauche|machoire)",
        ),
    ),
    RedFlag(
        "déficit neurologique brutal",
        "2",
        "Déficit moteur, sensitif, sensoriel ou du langage/AVC",
        (
            r"(ne bouge plus|bouge plus|paralys|faiblesse|engourdi|de travers|"
            r"trouve plus (ses|mes) mots|parle bizarrement|du mal a parler|n'arrive plus a parler"
            r"|difficulte a parler|mots qui ne sortent)",
            rf"({_ARM_FACE}|parler|parle|mots|langage)",
        ),
        unless=_DAYS,
    ),
    RedFlag(
        "idées suicidaires",
        "2",
        "Idée / comportement suicidaire",
        (
            r"(me tuer|me suicider|suicid|en finir|mettre fin a mes jours|mieux sans moi|"
            r"plus envie de vivre|me faire du mal)",
        ),
    ),
    RedFlag(
        "intoxication volontaire",
        "2",
        "Intoxication médicamenteuse",
        (r"(toute (ma|la|une) boite|tous mes (comprimes|medicaments)|avale .*(boite|plaquette))",),
        unless=rf"(hier|avant-hier|{_DAYS})",
    ),
    RedFlag(
        "hématémèse",
        "2",
        "Vomissement de sang/ hématémèse",
        (r"(vomi|vomit|vomir|vomis)", r"sang"),
    ),
    RedFlag(
        "hémorragie abondante",
        "2",
        "Rectorragie / hémorragie",
        (r"(beaucoup de sang|saigne beaucoup|saignement abondant|ca ne s'arrete pas de saigner)",),
        unless=r"(arrete a l'arrivee|s'est arrete|c'est arrete|ne saigne plus)",
    ),
    RedFlag(
        "risque d'obstruction allergique",
        "2",
        "Allergie",
        (
            r"(gonfle|gonfl|oedeme|enfle)",
            r"(langue|levres|du mal a avaler|du mal a respirer)",
        ),
    ),
    RedFlag(
        "céphalée brutale",
        "2",
        "Céphalée",
        (
            r"(mal de tete|mal a la tete|cephalee|migraine)",
            r"(coup de tonnerre|d'un coup|brutal|pire de ma vie|jamais eu aussi mal)",
        ),
    ),
    RedFlag(
        "crises convulsives répétées",
        "2",
        "Convulsions",
        (
            r"(deuxieme crise|refait une (crise|deuxieme)|crises? a repetition|plusieurs crises|"
            r"sans (s'etre |se )?reveill)",
        ),
    ),
    RedFlag(
        "dyspnée à la parole",
        "2",
        "Dyspnée / insuffisance respiratoire",
        (
            r"(n'arrive (presque )?plus a parler|ne peut plus parler|essouffle en parlant|"
            r"du mal a finir (ses|mes) phrases)",
            r"(respir|souffle|siffle|tousse|essouffl|etouff)",
        ),
    ),
    RedFlag(
        "purpura",
        "2",
        "Fièvre",
        (r"(purpura|taches? (violettes?|rouges?|noires?).*(ne s'effacent pas|ne partent pas))",),
    ),
    RedFlag(
        "accouchement imminent",
        "1",
        "Accouchement imminent ou réalisé",
        (r"(envie de pousser|la tete sort|contractions.{0,15}toutes les (une|deux|1|2) minutes?)",),
    ),
    RedFlag(
        "grossesse avec saignement ou douleur",
        "2",
        "Problème de grossesse 1er et 2ème trimestre",
        (r"(enceinte|grossesse|retard de regles)", r"(saign|metrorragie|douleur|mal au ventre)"),
    ),
    RedFlag(
        "douleur testiculaire brutale",
        "2",
        "Douleur de bourse/ orchite*/torsion testicule*",
        (r"(testicule|bourse)", r"(tres forte|intense|d'un coup|brutal|insupportable)"),
    ),
    RedFlag(
        "brûlure du visage, des mains ou étendue",
        "2",
        "Brûlure",
        (
            r"brul(?!ures? (d'estomac|mictionnel|en urinant))",
            r"(visage|figure|cou|mains?|tout le (bras|dos|ventre)|etendue)",
        ),
    ),
    RedFlag(
        "électrisation avec perte de connaissance",
        "2",
        "Electrisation",
        (r"(electris|electrocut|decharge electrique|foudre)", r"(perdu connaissance|evanoui)"),
    ),
    RedFlag(
        "surdité brutale",
        "2",
        "Trouble de l'audition/accouphènes",
        (r"(n'entends? plus|plus rien entendu|surdite|sourd)", r"(d'un coup|brutal|soudain)"),
    ),
    RedFlag(
        "brûlure chimique de l'œil",
        "2",
        "Corps étranger / brûlure oculaire",
        (r"(oeil|yeux)", r"(produit|chimique|javel|acide|soude|chaux|detergent|nettoyant)"),
    ),
    RedFlag(
        "ischémie de membre",
        "2",
        "Membre douloureux/ froid ou pâle/ischémie",
        (
            r"(jambe|bras|pied|main)",
            r"(froide?|pale|blanche?|violette?)",
            r"(douleur|douloureu|mal)",
        ),
        unless=_DAYS,
    ),
    RedFlag(
        "occlusion",
        "2",
        "Constipation",
        (r"(plus de selles|ni gaz|plus de gaz|arret des (matieres|gaz))", r"(vomi|vomit)"),
    ),
    RedFlag(
        "agitation ou hallucinations",
        "2",
        "Troubles du comportement / psychiatrie",
        (r"(entend(s)? des voix|hallucin|tres agite|agressif|devenu violent|delire)",),
    ),
    RedFlag(
        "confusion fébrile",
        "2",
        "Confusion/désorientation temporo spatiale",
        (r"(fievre|febrile)", r"(confus|desoriente|ne reconnait plus|delire)"),
    ),
    RedFlag(
        "traumatisme crânien sous anticoagulant",
        "2",
        "Traumatisme crânien",
        (
            r"(tete|crane|cogne)",
            r"(anticoagulant|avk|previscan|coumadine|eliquis|xarelto|pradaxa|sintrom)",
        ),
    ),
    RedFlag(
        "attaque de panique",
        "2",
        "Anxiété / dépression / consultation psychiatrique",
        (r"(attaque de panique|crise de panique)",),
    ),
)
_COMPILED = [
    (f, [re.compile(p) for p in f.patterns], re.compile(f.unless) if f.unless else None)
    for f in FLAGS
]
INFANT_FEVER_AGE = 0.25  # ≤ 3 mois : « Fièvre ≤ 3 mois », tri 2


def _affirmed(pattern: re.Pattern, text: str) -> re.Match | None:
    """Première occurrence qui n'est pas niée par les mots qui la précèdent."""
    for match in pattern.finditer(text):
        if not _NEGATION.search(text[max(0, match.start() - 30) : match.start()]):
            return match
    return None


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower().replace("’", "'").replace("œ", "oe"))
    return "".join(c for c in text if not unicodedata.combining(c))


@dataclass(frozen=True)
class Hit:
    name: str
    level: str
    motif: str
    excerpt: str


def red_flags(text: str, age_years: float | None = None) -> list[Hit]:
    """Drapeaux présents dans le récit, du plus grave au moins grave."""
    norm = normalize(text)
    hits = []
    for flag, patterns, unless in _COMPILED:
        if unless is not None and unless.search(norm):
            continue
        matches = [_affirmed(p, norm) for p in patterns]
        if all(matches):
            excerpt = " … ".join(m.group(0) for m in matches)
            hits.append(Hit(flag.name, flag.level, flag.motif, excerpt))
    if age_years is not None and age_years <= INFANT_FEVER_AGE and re.search(r"fievre", norm):
        hits.append(Hit("fièvre du nourrisson ≤ 3 mois", "2", "Fièvre ≤ 3 mois", "fievre"))
    return sorted(hits, key=lambda h: h.level)


def red_flag_floor(text: str, age_years: float | None = None) -> Hit | None:
    hits = red_flags(text, age_years)
    return hits[0] if hits else None
