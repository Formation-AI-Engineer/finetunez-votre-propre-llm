"""Service de pré-triage : conversation avec le modèle, puis garde-fous déterministes.

Le modèle (servi par vLLM, format OpenAI) répond soit par une question, soit par une évaluation
« Niveau de priorité : … ». Sur une évaluation, deux garde-fous peuvent relever le niveau, jamais
le baisser (docs/DECISIONS.md, point 7) :
1. les règles sur les constantes saisies par l'IOA (src/triage/rules.py) ;
2. la cohérence du critère FRENCH cité par le modèle (src/triage/consistency.py) ;
3. les drapeaux rouges sur le récit du patient (src/triage/red_flags.py).
Les constantes sont aussi contrôlées quand le modèle pose une question, ou s'il est indisponible :
une constante critique produit une alerte dans tous les cas.
"""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from triage.consistency import cited_criterion
from triage.data.schema import FRENCH_TO_PRIORITY, PriorityLevel, Vitals
from triage.output import parse_assessment
from triage.prompts import SYSTEM_PROMPT
from triage.red_flags import red_flag_floor
from triage.rules import vital_alerts, vital_floor

PRIORITIES: tuple[PriorityLevel, ...] = ("maximale", "moderee", "differee")
DISCLAIMER = (
    "Cet avis est une aide à la décision : l'infirmier ou l'infirmière d'accueil valide le "
    "niveau de tri."
)
MAX_TURNS = 8  # échanges patient-agent par session ; au-delà, l'IOA prend le relais
SESSION_TTL_SECONDS = 3600


class ModelUnavailable(RuntimeError):
    """Le serveur du modèle ne répond pas, ou répond une erreur."""


class ChatModel(Protocol):
    model_id: str

    def complete(self, messages: list[dict]) -> str: ...


@dataclass
class Guard:
    name: Literal["constantes", "coherence", "drapeau_rouge"]
    reason: str
    french_level: str


@dataclass
class TriageResult:
    session_id: str
    status: Literal["question", "evaluation", "relais_ioa"]
    message: str
    priority: PriorityLevel | None = None
    french_level: str | None = None
    model_priority: PriorityLevel | None = None
    guards: list[Guard] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    turn: int = 0
    model_id: str = ""
    latency_ms: int = 0


@dataclass
class Session:
    messages: list[dict]
    created: float
    age_years: float | None = None
    vitals: Vitals | None = None
    turns: int = 0


def _number(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def format_vitals(v: Vitals) -> str:
    """Constantes saisies, au format des vignettes d'entraînement ; les valeurs absentes sont
    omises."""
    parts = []
    if v.heart_rate is not None:
        parts.append(f"FC {v.heart_rate}/min")
    if v.systolic_bp is not None:
        diastolic = f"/{v.diastolic_bp}" if v.diastolic_bp is not None else ""
        parts.append(f"PA {v.systolic_bp}{diastolic} mmHg")
    if v.respiratory_rate is not None:
        parts.append(f"FR {v.respiratory_rate}/min")
    if v.spo2 is not None:
        parts.append(f"SpO2 {v.spo2} %")
    if v.temperature is not None:
        parts.append(f"T° {_number(v.temperature)} °C")
    if v.gcs is not None:
        parts.append(f"Glasgow {v.gcs}")
    if v.glycemia is not None:
        parts.append(f"glycémie capillaire {_number(v.glycemia)} mmol/l")
    return ", ".join(parts)


def render_turn(
    text: str, age_years: float | None, vitals: Vitals | None, observation: str | None
) -> str:
    """Message du patient, complété comme à l'entraînement par l'âge, les constantes et
    l'observation de l'IOA."""
    body = text.strip()
    if age_years is not None and not re.search(r"\b\d+\s*ans\b", body):
        body += f" J'ai {_number(age_years)} ans."
    if vitals is not None and (formatted := format_vitals(vitals)):
        body += f"\n\nConstantes prises à l'accueil : {formatted}."
    if observation:
        body += f"\nObservation de l'infirmière : {observation.strip().rstrip('.')}."
    return body


def _rank(priority: str) -> int:
    return PRIORITIES.index(priority)


class TriageService:
    def __init__(self, model: ChatModel, clock: Callable[[], float] = time.monotonic):
        self.model = model
        self.clock = clock
        self.sessions: dict[str, Session] = {}

    def _session(self, session_id: str | None) -> tuple[str, Session]:
        now = self.clock()
        for sid in [s for s, v in self.sessions.items() if now - v.created > SESSION_TTL_SECONDS]:
            del self.sessions[sid]
        if session_id is None:
            session_id = secrets.token_urlsafe(12)
            self.sessions[session_id] = Session(
                messages=[{"role": "system", "content": SYSTEM_PROMPT}], created=now
            )
        elif session_id not in self.sessions:
            raise KeyError(session_id)
        return session_id, self.sessions[session_id]

    def triage(
        self,
        text: str,
        session_id: str | None = None,
        age_years: float | None = None,
        vitals: Vitals | None = None,
        observation: str | None = None,
    ) -> TriageResult:
        sid, session = self._session(session_id)
        session.age_years = age_years if age_years is not None else session.age_years
        session.vitals = vitals if vitals is not None else session.vitals
        alerts = [a.reason for a in vital_alerts(session.vitals, session.age_years)]
        result = TriageResult(sid, "question", "", alerts=alerts, model_id=self.model.model_id)

        if session.turns >= MAX_TURNS:
            return self._handover(result, session, "nombre maximal d'échanges atteint")
        session.messages.append(
            {"role": "user", "content": render_turn(text, age_years, vitals, observation)}
        )
        start = self.clock()
        try:
            answer = self.model.complete(session.messages)
        except ModelUnavailable:
            session.messages.pop()
            return self._handover(result, session, "modèle indisponible")
        result.latency_ms = round((self.clock() - start) * 1000)
        session.messages.append({"role": "assistant", "content": answer})
        session.turns += 1
        result.turn = session.turns
        result.message = answer.strip()

        assessment = parse_assessment(answer)
        if assessment is None:
            # Question de recueil : pas de niveau. Une constante critique reste signalée.
            return result
        result.status = "evaluation"
        result.model_priority = assessment.priority
        priority, level = assessment.priority, assessment.french_level

        floor = vital_floor(session.vitals, session.age_years)
        if floor and _rank(FRENCH_TO_PRIORITY[floor.level]) < _rank(priority):
            priority, level = FRENCH_TO_PRIORITY[floor.level], floor.level
            result.guards.append(Guard("constantes", floor.reason, floor.level))
        cited = cited_criterion(answer)
        if cited and _rank(FRENCH_TO_PRIORITY[cited.level]) < _rank(priority):
            priority, level = FRENCH_TO_PRIORITY[cited.level], cited.level
            reason = f"critère cité « {cited.criterion} » ({cited.motif}) : tri {cited.level}"
            result.guards.append(Guard("coherence", reason, cited.level))
        story = " ".join(m["content"] for m in session.messages if m["role"] == "user")
        hit = red_flag_floor(story, session.age_years)
        if hit and _rank(FRENCH_TO_PRIORITY[hit.level]) < _rank(priority):
            priority, level = FRENCH_TO_PRIORITY[hit.level], hit.level
            reason = f"{hit.name} (« {hit.excerpt} ») : {hit.motif}, tri {hit.level}"
            result.guards.append(Guard("drapeau_rouge", reason, hit.level))
        result.priority, result.french_level = priority, level
        return result

    def _handover(self, result: TriageResult, session: Session, why: str) -> TriageResult:
        """Relais à l'IOA, avec le plancher des constantes s'il y en a un."""
        result.status = "relais_ioa"
        result.turn = session.turns
        result.message = f"Évaluation à faire par l'infirmier ou l'infirmière d'accueil ({why})."
        floor = vital_floor(session.vitals, session.age_years)
        if floor:
            result.priority, result.french_level = FRENCH_TO_PRIORITY[floor.level], floor.level
            result.guards.append(Guard("constantes", floor.reason, floor.level))
        return result
