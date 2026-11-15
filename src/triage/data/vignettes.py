"""Vignettes de triage synthétiques, générées par règles à partir du référentiel FRENCH.

Chaque vignette part d'un motif et d'un critère du tableau FRENCH (configs/french_vignettes.yaml),
tire un patient (âge, sexe, antécédents, constantes) et la rédige sous une de trois formes :
note d'infirmière d'accueil (IOA), récit du patient, ou dialogue où l'agent pose d'abord une
question. Le niveau attendu est le plus grave entre le critère FRENCH et les règles de sécurité
sur les constantes (triage.rules).

Ces données sont synthétiques : elles ne sont pas validées cliniquement.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from triage.data.french_table import Motif, load_table
from triage.data.schema import (
    FRENCH_TO_PRIORITY,
    ClinicalContext,
    DPORecord,
    Message,
    Metadata,
    SFTRecord,
    TriageLabel,
    Vitals,
    record_id,
)
from triage.prompts import SYSTEM_PROMPT
from triage.rules import ADULT_AGE, most_severe, severity, vital_floor
from triage.wording import EXPLANATION, ORIENTATION, PRIORITY_LABEL  # noqa: F401

CONFIG_PATH = Path("configs/french_vignettes.yaml")
SOURCE = "french_vignettes"
LICENSE = "Synthétique, dérivé du référentiel FRENCH (SFMU)"
STYLES = ("note", "patient", "dialogue")

DISCLAIMER = (
    "Cet avis est une aide à la décision : l'infirmier ou l'infirmière d'accueil valide le niveau "
    "de tri."
)
CLOSINGS = (
    "",
    "Quel niveau de priorité proposez-vous ?",
    "Merci d'évaluer le niveau de priorité.",
    "Que proposez-vous ?",
)

# Constantes critiques injectées pour apprendre la règle de sécurité (vignettes « escalade »).
CRITICAL_VITALS = (
    {"spo2": (80, 85)},
    {"systolic_bp": (60, 70)},
    {"heart_rate": (182, 200)},
    {"respiratory_rate": (40, 44)},
    {"gcs": (6, 8)},
)


@dataclass(frozen=True)
class Alternative:
    level: str
    signs: tuple[str, ...]
    patient: str | None
    vitals: dict[str, tuple[float, float]]
    age: tuple[float, float] | None
    context: str | None


@dataclass
class MotifSpec:
    motif: Motif
    complaints: list[str]
    patient: list[str]
    question: str
    age: tuple[float, float]
    sex: str | None
    history: list[str]
    alternatives: list[Alternative] = field(default_factory=list)
    # Phrases de `patient` dites par un proche (« Mon mari… ») : âge, antécédents à la 3e personne.
    proxy: frozenset[str] = frozenset()


@dataclass
class Case:
    spec: MotifSpec
    alternative: Alternative
    level: str
    criterion: str
    escalation: str | None
    age: float
    sex: str
    history: list[str]
    vitals: Vitals
    style: str


def load_specs(config_path: Path = CONFIG_PATH) -> tuple[list[MotifSpec], list[str]]:
    """Charge la configuration et vérifie chaque niveau contre le tableau FRENCH extrait."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    table = load_table()
    specs = []
    for entry in config["motifs"]:
        name = entry["motif"]
        if name not in table:
            raise ValueError(f"motif absent du tableau FRENCH : {name!r}")
        motif = table[name]
        spec = MotifSpec(
            motif=motif,
            complaints=entry["plaintes"],
            # Même liste, dans le même ordre, que la phrase soit dite par le patient ou un proche :
            # les tirages aléatoires ne dépendent pas de ce marquage.
            patient=[p["tiers"] if isinstance(p, dict) else p for p in entry["patient"]],
            question=entry["question"],
            age=tuple(entry["age"]),
            sex=entry.get("sexe"),
            history=entry.get("antecedents", []),
            proxy=frozenset(p["tiers"] for p in entry["patient"] if isinstance(p, dict)),
        )
        for key, alternatives in entry["niveaux"].items():
            key = str(key)
            level = motif.default_level if key == "defaut" else key
            if key != "defaut" and level not in motif.criteria:
                raise ValueError(f"{name} : aucun critère FRENCH en colonne tri {level}")
            for alt in alternatives:
                spec.alternatives.append(
                    Alternative(
                        level=level,
                        signs=tuple(alt.get("signes", [])),
                        patient=alt.get("patient"),
                        vitals={k: tuple(v) for k, v in alt.get("constantes", {}).items()},
                        age=tuple(alt["age"]) if "age" in alt else None,
                        context=alt.get("contexte"),
                    )
                )
        specs.append(spec)
    return specs, config["antecedents_generiques"]


# ---------------------------------------------------------------------------- tirage


def _baseline_vitals(age: float, rng: random.Random) -> dict[str, float]:
    if age < 2:
        ranges = {"heart_rate": (105, 150), "systolic_bp": (75, 95), "respiratory_rate": (26, 40)}
    elif age < ADULT_AGE:
        ranges = {"heart_rate": (75, 115), "systolic_bp": (95, 115), "respiratory_rate": (16, 24)}
    elif age < 65:
        ranges = {"heart_rate": (62, 95), "systolic_bp": (110, 140), "respiratory_rate": (12, 20)}
    else:
        ranges = {"heart_rate": (60, 92), "systolic_bp": (120, 155), "respiratory_rate": (14, 20)}
    vitals = {k: rng.randint(*r) for k, r in ranges.items()}
    vitals["diastolic_bp"] = max(40, vitals["systolic_bp"] - rng.randint(35, 60))
    vitals["spo2"] = rng.randint(95, 100) if age < 65 else rng.randint(94, 99)
    vitals["temperature"] = round(rng.uniform(36.4, 37.5), 1)
    return vitals


def _draw(value_range: tuple[float, float], rng: random.Random) -> float:
    low, high = value_range
    if isinstance(low, int) and isinstance(high, int):
        return rng.randint(low, high)
    return round(rng.uniform(low, high), 1)


def _make_vitals(
    age: float, overrides: dict[str, tuple[float, float]], rng: random.Random
) -> Vitals:
    vitals = _baseline_vitals(age, rng)
    vitals.update({k: _draw(r, rng) for k, r in overrides.items()})
    if "systolic_bp" in overrides:
        vitals["diastolic_bp"] = int(vitals["systolic_bp"] * rng.uniform(0.5, 0.65))
    return Vitals(**vitals)


def sample_case(
    spec: MotifSpec,
    alternative: Alternative,
    generic_history: list[str],
    rng: random.Random,
    style: str,
    escalate: bool = False,
) -> Case:
    age_range = alternative.age or spec.age
    age = round(rng.uniform(*age_range), 2 if age_range[1] < 2 else 0)
    sex = spec.sex or rng.choice("FM")
    pool = spec.history + (generic_history if age >= ADULT_AGE else [])
    history = rng.sample(pool, k=min(len(pool), rng.choice((0, 1, 1, 2)))) if age >= 2 else []
    if alternative.context:
        history = [alternative.context, *history]

    criterion = alternative_criterion(spec.motif, alternative.level)
    for _ in range(50):
        overrides = dict(alternative.vitals)
        if escalate:
            overrides.update({k: v for k, v in rng.choice(CRITICAL_VITALS).items()})
        vitals = _make_vitals(age, overrides, rng)
        alert = vital_floor(vitals, age)
        aggravates = alert is not None and severity(alert.level) < severity(alternative.level)
        if escalate and aggravates:
            level = most_severe(alternative.level, alert.level)
            return Case(
                spec, alternative, level, criterion, alert.reason, age, sex, history, vitals, style
            )
        if not escalate and not aggravates:
            return Case(
                spec,
                alternative,
                alternative.level,
                criterion,
                None,
                age,
                sex,
                history,
                vitals,
                style,
            )
        if not escalate and alternative.vitals:
            raise ValueError(
                f"{spec.motif.name} tri {alternative.level} : les constantes imposées "
                f"déclenchent une règle plus grave ({alert.reason})"
            )
    raise RuntimeError(f"constantes incohérentes pour {spec.motif.name} tri {alternative.level}")


def alternative_criterion(motif: Motif, level: str) -> str:
    if level in motif.criteria:
        return motif.criteria[level]
    return f"aucun critère modulateur : niveau de base du motif (tri M {motif.default_level})"


# --------------------------------------------------------------------------- rédaction


def _gender(text: str, sex: str) -> str:
    return text.replace("{e}", "e" if sex == "F" else "")


def _age_text(age: float) -> str:
    if age < 1 / 12:
        return f"{max(1, round(age * 52))} semaines"
    if age < 2:
        return f"{max(1, round(age * 12))} mois"
    return f"{int(age)} ans"


def _person(age: float, sex: str) -> str:
    if age < 2:
        return f"Nourrisson de {_age_text(age)} ({'fille' if sex == 'F' else 'garçon'})"
    if age < ADULT_AGE:
        return f"{'Fille' if sex == 'F' else 'Garçon'} de {_age_text(age)}"
    return f"{'Femme' if sex == 'F' else 'Homme'} de {_age_text(age)}"


def _number(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") if isinstance(value, float) else str(value)


def format_vitals(v: Vitals) -> str:
    parts = [
        f"FC {v.heart_rate}/min",
        f"PA {v.systolic_bp}/{v.diastolic_bp} mmHg",
        f"FR {v.respiratory_rate}/min",
        f"SpO2 {v.spo2} %",
        f"T° {_number(v.temperature)} °C",
    ]
    if v.gcs is not None:
        parts.append(f"Glasgow {v.gcs}")
    if v.glycemia is not None:
        parts.append(f"glycémie capillaire {_number(v.glycemia)} mmol/l")
    return ", ".join(parts)


def _vital_findings(case: Case) -> list[str]:
    labels = {
        "heart_rate": ("FC", "/min"),
        "systolic_bp": ("PAS", " mmHg"),
        "respiratory_rate": ("FR", "/min"),
        "spo2": ("SpO2", " %"),
        "temperature": ("T°", " °C"),
        "gcs": ("Glasgow", ""),
        "glycemia": ("glycémie", " mmol/l"),
    }
    return [
        f"{labels[k][0]} {_number(getattr(case.vitals, k))}{labels[k][1]}"
        for k in case.alternative.vitals
    ]


def _history_text(history: list[str]) -> str:
    return ", ".join(history) if history else "aucun"


def _patient_opening(case: Case, rng: random.Random) -> tuple[str, bool]:
    """Première prise de parole, par un parent si un motif d'adulte concerne un enfant, et si
    elle est dite par un proche plutôt que par le patient."""
    if case.age < ADULT_AGE and case.spec.age[0] >= ADULT_AGE:
        relation = "ma fille" if case.sex == "F" else "mon fils"
        complaint = rng.choice(case.spec.complaints)
        return f"Je viens pour {relation} de {_age_text(case.age)} : {complaint}.", True
    line = rng.choice(case.spec.patient)
    return _gender(line, case.sex), line in case.spec.proxy


def _clinical_block(case: Case, include_signs: bool) -> str:
    lines = [f"Constantes prises à l'accueil : {format_vitals(case.vitals)}."]
    if include_signs and case.alternative.signs:
        lines.append(f"Observation de l'infirmière : {' ; '.join(case.alternative.signs)}.")
    return "\n".join(lines)


def render_note(case: Case, rng: random.Random) -> str:
    lines = [
        f"{_person(case.age, case.sex)}.",
        f"Motif de venue : {rng.choice(case.spec.complaints)}.",
        f"Antécédents : {_history_text(case.history)}.",
        f"Constantes : {format_vitals(case.vitals)}.",
    ]
    if case.alternative.signs:
        lines.append(f"Observation IOA : {' ; '.join(case.alternative.signs)}.")
    closing = rng.choice(CLOSINGS)
    return "\n".join(lines) + (f"\n\n{closing}" if closing else "")


def render_patient(case: Case, rng: random.Random) -> str:
    said = _gender(case.alternative.patient, case.sex) if case.alternative.patient else None
    text, proxy = (said, False) if said and case.age >= ADULT_AGE else _patient_opening(case, rng)
    if case.age >= ADULT_AGE:
        if proxy:
            text += f" {'Elle' if case.sex == 'F' else 'Il'} a {_age_text(case.age)}."
        else:
            text += f" J'ai {_age_text(case.age)}."
        if case.history:
            text += f" {'Ses' if proxy else 'Mes'} antécédents : {', '.join(case.history)}."
    include_signs = not said or rng.random() < 0.5
    return f"{text}\n\n{_clinical_block(case, include_signs)}"


def _question(case: Case) -> str:
    return (
        "Je vais vous aider à évaluer votre niveau de priorité. "
        f"{_gender(case.spec.question, case.sex)}"
    )


def render_dialogue(case: Case, rng: random.Random) -> list[Message]:
    said = _gender(case.alternative.patient, case.sex) if case.alternative.patient else ""
    answer = f"{said}\n\n" if said else ""
    answer += _clinical_block(case, include_signs=True)
    if said and case.age >= ADULT_AGE:
        opening = f"Bonjour, je viens pour {rng.choice(case.spec.complaints)}."
    else:
        opening, _ = _patient_opening(case, rng)
    return [
        Message(role="user", content=opening),
        Message(role="assistant", content=_question(case)),
        Message(role="user", content=answer),
    ]


def render_assessment(case: Case, level: str | None = None, ignore_findings: bool = False) -> str:
    """Réponse de triage. `level` et `ignore_findings` servent à fabriquer un sous-triage."""
    level = level or case.level
    priority = FRENCH_TO_PRIORITY[level]
    if ignore_findings:
        findings = f"{case.spec.complaints[0]}, sans signe de gravité retenu."
    elif case.escalation:
        findings = (
            f"{case.escalation}. Règle de sécurité : une constante vitale en zone critique impose "
            "ce niveau, quel que soit le motif."
        )
    else:
        observed = [*case.alternative.signs, *_vital_findings(case)]
        findings = f"{' ; '.join(observed)}." if observed else ""
        if case.level in case.spec.motif.criteria:
            findings += f" Critère FRENCH : « {case.criterion} »."
        else:
            findings += (
                " Aucun critère de gravité spécifique du motif : niveau de base "
                f"(tri M {case.spec.motif.default_level})."
            )
    return "\n".join(
        [
            f"Niveau de priorité : {PRIORITY_LABEL[priority]} (tri FRENCH {level})",
            f"Motif de recours : {case.spec.motif.name.rstrip('*').strip()}",
            f"Éléments déterminants : {findings.strip()}",
            f"Explication : {EXPLANATION[priority]}",
            f"Conduite proposée : {ORIENTATION[level]}",
            DISCLAIMER,
        ]
    )


def under_triage_level(level: str, rng: random.Random) -> str | None:
    """Un niveau d'une catégorie de priorité moins grave, ou None pour une priorité différée."""
    priority = FRENCH_TO_PRIORITY[level]
    if priority == "maximale":
        return rng.choice(("3A", "3B"))
    if priority == "moderee":
        return rng.choice(("4", "5"))
    return None


# ----------------------------------------------------------------------- enregistrements


def _metadata(case: Case, split: str, variant: str, task: str = "triage") -> Metadata:
    signs = list(case.alternative.signs)
    return Metadata(
        source=SOURCE,
        source_id=variant,
        source_split=split,
        license=LICENSE,
        language="fr",
        task=task,
        confidence="synthetic_rules",
        synthetic=True,
        anonymized=True,
        clinical=ClinicalContext(
            age_years=case.age,
            sex=case.sex,
            chief_complaint=case.spec.complaints[0],
            symptoms=signs,
            history=case.history,
            vitals=case.vitals,
        ),
        triage=TriageLabel(
            french_level=case.level,
            priority=FRENCH_TO_PRIORITY[case.level],
            motif=case.spec.motif.name,
            category=case.spec.motif.category,
            deciding_criterion=case.escalation or case.criterion,
        ),
        extra={"style": case.style, "escalation": case.escalation is not None},
    )


def _prompt(case: Case, rng: random.Random) -> list[Message]:
    system = Message(role="system", content=SYSTEM_PROMPT)
    if case.style == "dialogue":
        return [system, *render_dialogue(case, rng)]
    render = render_note if case.style == "note" else render_patient
    return [system, Message(role="user", content=render(case, rng))]


def _cases(n: int, seed: int, escalation_rate: float = 0.05) -> Iterator[Case]:
    """Tire n cas équilibrés entre les trois priorités, puis entre alternatives."""
    specs, generic_history = load_specs()
    rng = random.Random(seed)
    by_priority: dict[str, list[tuple[MotifSpec, Alternative]]] = {}
    for spec in specs:
        for alt in spec.alternatives:
            by_priority.setdefault(FRENCH_TO_PRIORITY[alt.level], []).append((spec, alt))
    priorities = ("maximale", "moderee", "differee")
    for _ in range(n):
        escalate = rng.random() < escalation_rate
        priority = rng.choice(priorities[1:] if escalate else priorities)
        spec, alt = rng.choice(by_priority[priority])
        style = rng.choices(STYLES, weights=(0.4, 0.35, 0.25))[0]
        yield sample_case(spec, alt, generic_history, rng, style, escalate)


def generate_sft(n: int, split: str, seed: int, question_rate: float = 0.08) -> list[SFTRecord]:
    rng = random.Random(seed + 1)
    records = []
    for i, case in enumerate(_cases(n, seed)):
        variant = f"{split}-{seed}-{i}"
        records.append(
            SFTRecord(
                id=record_id(SOURCE, variant),
                prompt=_prompt(case, rng),
                completion=[Message(role="assistant", content=render_assessment(case))],
                metadata=_metadata(case, split, variant),
            )
        )
        # Premier tour seul : l'agent doit poser une question avant de trier, sauf urgence vitale
        # évidente dès la première phrase (motifs dont le niveau de base est le tri 1).
        asks = case.style == "dialogue" and case.spec.motif.default_level != "1"
        if asks and rng.random() < question_rate / 0.25:
            question_variant = f"{variant}-question"
            meta = _metadata(case, split, question_variant)
            meta.extra["turn"] = "question"
            records.append(
                SFTRecord(
                    id=record_id(SOURCE, question_variant),
                    prompt=records[-1].prompt[:2],
                    completion=[Message(role="assistant", content=_question(case))],
                    metadata=meta,
                )
            )
    return records


def generate_dpo(n: int, split: str, seed: int) -> list[DPORecord]:
    """Paires « bon niveau » contre « sous-triage », sur les cas de priorité maximale ou modérée."""
    rng = random.Random(seed + 1)
    records = []
    i = 0
    for case in _cases(n * 3, seed):
        wrong = under_triage_level(case.level, rng)
        if wrong is None:
            continue
        variant = f"{split}-{seed}-{i}"
        meta = _metadata(case, split, variant, task="preference")
        meta.extra["rejected_level"] = wrong
        records.append(
            DPORecord(
                id=record_id(SOURCE, f"dpo-{variant}"),
                prompt=_prompt(case, rng),
                chosen=[Message(role="assistant", content=render_assessment(case))],
                rejected=[
                    Message(
                        role="assistant",
                        content=render_assessment(case, level=wrong, ignore_findings=True),
                    )
                ],
                metadata=meta,
            )
        )
        i += 1
        if i == n:
            break
    return records
