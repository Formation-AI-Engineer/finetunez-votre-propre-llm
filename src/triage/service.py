"""Service de pré-triage : conversation avec le modèle, puis garde-fous déterministes.

Le modèle (servi par vLLM, format OpenAI) répond soit par une question, soit par une évaluation
« Niveau de priorité : … ». Sur une évaluation, deux garde-fous peuvent relever le niveau, jamais
le baisser (docs/DECISIONS.md, point 7) :
1. les règles sur les constantes saisies par l'IOA (src/triage/rules.py) ;
2. la cohérence du critère FRENCH cité par le modèle (src/triage/consistency.py) ;
3. les drapeaux rouges sur le récit du patient (src/triage/red_flags.py).
Les constantes sont aussi contrôlées quand le modèle pose une question, ou s'il est indisponible :
une constante critique produit une alerte dans tous les cas ; un drapeau rouge dans le récit aussi.
Si le modèle pose une question alors qu'un signe de tri 1 ou 2 est déjà là (constante ou drapeau
rouge), le recueil s'arrête : évaluation MAXIMALE tout de suite (16/11/2026).

Robustesse (tests sur le déploiement du 15/11/2026) :
- quand un garde-fou relève le niveau, le message est réécrit à partir du niveau final (sinon le
  texte du modèle, par exemple obéissant à une injection, annoncerait un niveau plus bas) ; le
  texte du modèle reste dans le journal d'audit (`model_answer`) ;
- un message en anglais part à l'IOA sans appel au modèle (triage validé en français seulement) ;
- une réponse qui recopie le prompt système est remplacée par une demande de recentrage.

Démonstration (15/11/2026) :
- une évaluation hors du format attendu (« niveau de priorité maximal (tri FRENCH 2) ») est lue
  par `parse_loose`, réécrite au format standard, et passe par les garde-fous ; alerte à l'IOA ;
- après une évaluation, la session est close : le modèle, qui n'a jamais vu de suite à une
  évaluation à l'entraînement, inventait une réponse (« ok merci » → texte en anglais, faux numéro
  de dossier). Les messages suivants reçoivent une réponse fixe ; le niveau rendu est gardé, et
  ne peut que monter (nouvelles constantes, drapeau rouge dans le nouveau message).

Aggravation (16/11/2026) : un message marqué `aggravation` après l'évaluation est réévalué par le
modèle. Pour rester dans une forme apprise, le modèle reçoit la conversation d'origine sans son
évaluation, l'aggravation ajoutée à la dernière réponse du patient : un récit (un seul message)
ou un dialogue (question clé puis réponse). Envoyer le récit seul, sans la question déjà posée,
lui faisait reposer cette question (test sur le vrai modèle du 16/11).
Le niveau rendu ne peut que monter : un niveau plus bas que le précédent est ignoré
(garde-fou `niveau_precedent`). Si le modèle ne rend pas d'évaluation ou ne répond pas, ce sont
les règles seules (constantes, drapeaux rouges) qui s'appliquent, comme avant. Au plus
`MAX_REASSESSMENTS` réévaluations par session.
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
from triage.language import is_english
from triage.output import parse_assessment, parse_loose
from triage.prompts import SYSTEM_PROMPT
from triage.red_flags import red_flag_floor
from triage.rules import vital_alerts, vital_floor
from triage.wording import EXPLANATION, ORIENTATION, PRIORITY_LABEL

PRIORITIES: tuple[PriorityLevel, ...] = ("maximale", "moderee", "differee")
DISCLAIMER = (
    "Cet avis est une aide à la décision : l'infirmier ou l'infirmière d'accueil valide le "
    "niveau de tri."
)
MAX_TURNS = 8  # échanges patient-agent par session ; au-delà, l'IOA prend le relais
MAX_REASSESSMENTS = 3  # réévaluations par le modèle après un signalement d'aggravation
AGGRAVATION_LINK = "Depuis, mon état s'aggrave :"
SESSION_TTL_SECONDS = 3600
ENGLISH_HANDOVER = (
    "Un infirmier ou une infirmière d'accueil va évaluer votre situation directement. "
    "A triage nurse will assess you directly."
)
AFTER_EVALUATION = (
    "L'évaluation est terminée : l'infirmier ou l'infirmière d'accueil prend le relais. "
    "Signalez tout de suite à l'accueil si vos symptômes changent ou s'aggravent."
)
NON_STANDARD_FORMAT = "Évaluation au format non standard : niveau lu dans le texte du modèle"
REFOCUS = (
    "Je ne peux pas répondre à cette demande. Pouvez-vous me décrire ce qui vous amène aux "
    "urgences ?"
)
# Phrases du prompt système : une réponse qui en recopie une est une fuite.
_SYSTEM_SENTENCES = [s.strip() for s in SYSTEM_PROMPT.split(". ") if len(s.strip()) > 40]


def leaks_system_prompt(answer: str) -> bool:
    flat = " ".join(answer.split())
    return any(sentence in flat for sentence in _SYSTEM_SENTENCES)


def guarded_message(
    priority: str,
    level: str | None,
    guards: list[Guard],
    lead: str = "Niveau relevé par un contrôle de sécurité",
) -> str:
    """Message d'évaluation au format standard, réécrit quand un garde-fou a relevé le niveau du
    modèle ou quand le modèle n'a pas suivi le format."""
    header = f"Niveau de priorité : {PRIORITY_LABEL[priority]}"
    lines = [f"{header} (tri FRENCH {level})" if level else header]
    if guards:
        reasons = " ; ".join(g.reason for g in guards)
        lines.append(f"{lead} : {reasons}.")
    lines.append(f"Explication : {EXPLANATION[priority]}")
    if level:
        lines.append(f"Conduite proposée : {ORIENTATION[level]}")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


class ModelUnavailable(RuntimeError):
    """Le serveur du modèle ne répond pas, ou répond une erreur."""


class ChatModel(Protocol):
    model_id: str

    def complete(self, messages: list[dict]) -> str: ...


@dataclass
class Guard:
    name: Literal["constantes", "coherence", "drapeau_rouge", "niveau_precedent"]
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
    model_answer: str | None = None  # texte brut du modèle, s'il diffère du message (audit)


@dataclass
class Session:
    messages: list[dict]
    created: float
    age_years: float | None = None
    vitals: Vitals | None = None
    turns: int = 0
    final: tuple[PriorityLevel, str | None] | None = None  # niveau rendu : session close
    story: list[str] = field(default_factory=list)  # messages du patient, bruts
    reassessments: int = 0


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


_FRENCH_LEVELS = ("1", "2", "3A", "3B", "4", "5")


def _severity(priority: str, level: str | None) -> tuple[int, int]:
    """Ordre de gravité, priorité puis tri FRENCH (un tri absent compte comme le moins grave)."""
    return _rank(priority), _FRENCH_LEVELS.index(level) if level else len(_FRENCH_LEVELS)


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
        aggravation: bool = False,
    ) -> TriageResult:
        sid, session = self._session(session_id)
        session.age_years = age_years if age_years is not None else session.age_years
        session.vitals = vitals if vitals is not None else session.vitals
        alerts = [a.reason for a in vital_alerts(session.vitals, session.age_years)]
        result = TriageResult(sid, "question", "", alerts=alerts, model_id=self.model.model_id)

        if session.final is not None:
            if aggravation and session.reassessments < MAX_REASSESSMENTS and not is_english(text):
                return self._reassess(result, session, text, observation)
            return self._after_evaluation(result, session, text)
        if session.turns >= MAX_TURNS:
            return self._handover(result, session, "nombre maximal d'échanges atteint", text)
        if is_english(text):
            self._handover(result, session, "message en anglais")
            result.message = ENGLISH_HANDOVER
            return result
        session.messages.append(
            {"role": "user", "content": render_turn(text, age_years, vitals, observation)}
        )
        start = self.clock()
        try:
            answer = self.model.complete(session.messages)
        except ModelUnavailable:
            session.messages.pop()
            return self._handover(result, session, "modèle indisponible", text)
        result.latency_ms = round((self.clock() - start) * 1000)
        session.story.append(text.strip())
        session.messages.append({"role": "assistant", "content": answer})
        session.turns += 1
        result.turn = session.turns
        result.message = answer.strip()
        story = " ".join(m["content"] for m in session.messages if m["role"] == "user")

        if leaks_system_prompt(answer):
            result.model_answer, result.message = result.message, REFOCUS
            return result
        assessment = parse_assessment(answer)
        # Format attendu : l'évaluation commence par « Niveau de priorité ». Un en-tête trouvé au
        # milieu d'un texte inventé (démonstration du 15/11 : au 812e caractère, après des
        # « ## Age : 32 ans ») ne rend pas ce texte présentable : message réécrit, comme sans
        # en-tête.
        non_standard = assessment is not None and not answer.lstrip().lower().startswith(
            "niveau de priorité"
        )
        if assessment is None and (assessment := parse_loose(answer)) is not None:
            non_standard = True
        if non_standard:
            result.alerts.append(NON_STANDARD_FORMAT)
        if assessment is None:
            # Question de recueil. Un signe de gravité (tri 1 ou 2) dans le récit ou les
            # constantes arrête le recueil : évaluation MAXIMALE tout de suite, sans autre
            # question (démonstration du 16/11 : douleur thoracique typique, 5 questions avant
            # de conclure). Les 24 drapeaux actuels sont tous de tri 1 ou 2 ; un drapeau moins
            # grave ajouté plus tard resterait une alerte pour l'IOA.
            if self._stop_on_severe_sign(result, session, answer, story):
                return result
            if hit := red_flag_floor(story, session.age_years):
                result.alerts.append(
                    f"Drapeau rouge : {hit.name} (« {hit.excerpt} »), {hit.motif}, tri {hit.level}"
                )
            return result
        self._evaluate(result, session, answer, assessment, story, non_standard)
        return result

    def _evaluate(
        self,
        result: TriageResult,
        session: Session,
        answer: str,
        assessment,
        story: str,
        non_standard: bool,
        previous: tuple[PriorityLevel, str | None] | None = None,
    ) -> None:
        """Niveau final d'une évaluation du modèle : garde-fous, puis niveau déjà rendu (qui ne
        peut pas baisser), puis message réécrit si le niveau ou le format a changé."""
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
        hit = red_flag_floor(story, session.age_years)
        if hit and _rank(FRENCH_TO_PRIORITY[hit.level]) < _rank(priority):
            priority, level = FRENCH_TO_PRIORITY[hit.level], hit.level
            reason = f"{hit.name} (« {hit.excerpt} ») : {hit.motif}, tri {hit.level}"
            result.guards.append(Guard("drapeau_rouge", reason, hit.level))
        if previous and _severity(*previous) < _severity(priority, level):
            priority, level = previous
            reason = f"niveau déjà rendu, {PRIORITY_LABEL[priority]}" + (
                f" (tri {level})" if level else ""
            )
            result.guards.append(
                Guard("niveau_precedent", reason + ", qui ne peut pas baisser", level or "")
            )
        result.priority, result.french_level = priority, level
        session.final = (priority, level)
        if result.guards or non_standard:
            result.model_answer = result.message
            result.message = guarded_message(priority, level, result.guards)

    def _stop_on_severe_sign(
        self, result: TriageResult, session: Session, answer: str, story: str
    ) -> bool:
        """Le modèle pose une question alors qu'un signe de gravité est déjà là : évaluation
        MAXIMALE au niveau du signe le plus grave, message réécrit, question gardée pour l'audit."""
        guards = []
        if (floor := vital_floor(session.vitals, session.age_years)) and FRENCH_TO_PRIORITY[
            floor.level
        ] == "maximale":
            guards.append(Guard("constantes", floor.reason, floor.level))
        hit = red_flag_floor(story, session.age_years)
        if hit and FRENCH_TO_PRIORITY[hit.level] == "maximale":
            reason = f"{hit.name} (« {hit.excerpt} ») : {hit.motif}, tri {hit.level}"
            guards.append(Guard("drapeau_rouge", reason, hit.level))
        if not guards:
            return False
        level = min((g.french_level for g in guards), key=_FRENCH_LEVELS.index)
        result.status = "evaluation"
        result.priority, result.french_level = "maximale", level
        result.guards = guards
        result.model_answer = answer.strip()
        result.message = guarded_message(
            "maximale", level, guards, lead="Signe de gravité repéré, pas d'autre question"
        )
        session.final = ("maximale", level)
        return True

    def _reassess(
        self, result: TriageResult, session: Session, text: str, observation: str | None
    ) -> TriageResult:
        """Aggravation signalée après l'évaluation : le modèle réévalue la conversation, sans son
        évaluation, l'aggravation ajoutée à la dernière réponse du patient. Repli sur les règles
        seules si le modèle ne répond pas ou ne rend pas d'évaluation."""
        last = f"{session.story[-1]} {AGGRAVATION_LINK} {text.strip()}"
        user = render_turn(last, session.age_years, session.vitals, observation)
        messages = [*session.messages[:-2], {"role": "user", "content": user}]
        story = " ".join([*session.story[:-1], last])
        start = self.clock()
        try:
            answer = self.model.complete(messages)
        except ModelUnavailable:
            return self._after_evaluation(result, session, text)
        result.latency_ms = round((self.clock() - start) * 1000)
        session.reassessments += 1
        session.turns += 1
        result.turn = session.turns
        assessment = parse_assessment(answer)
        non_standard = assessment is not None and not answer.lstrip().lower().startswith(
            "niveau de priorité"
        )
        if assessment is None and (assessment := parse_loose(answer)) is not None:
            non_standard = True
        if assessment is None or leaks_system_prompt(answer):
            fallback = self._after_evaluation(result, session, text)
            fallback.model_answer = answer.strip()
            fallback.alerts.append("Réévaluation sans niveau lisible : règles seules appliquées")
            return fallback
        session.story[-1] = last
        session.messages = [*messages, {"role": "assistant", "content": answer}]
        if non_standard:
            result.alerts.append(NON_STANDARD_FORMAT)
        result.message = answer.strip()
        self._evaluate(result, session, answer, assessment, story, non_standard, session.final)
        return result

    def _after_evaluation(self, result: TriageResult, session: Session, text: str) -> TriageResult:
        """Message après l'évaluation : pas d'appel au modèle ; le niveau rendu est gardé et ne
        peut que monter (constantes, drapeau rouge dans le nouveau message)."""
        result.status = "relais_ioa"
        result.turn = session.turns
        result.message = AFTER_EVALUATION
        priority, level = session.final
        floor = vital_floor(session.vitals, session.age_years)
        if floor and _rank(FRENCH_TO_PRIORITY[floor.level]) < _rank(priority):
            priority, level = FRENCH_TO_PRIORITY[floor.level], floor.level
            result.guards.append(Guard("constantes", floor.reason, floor.level))
        hit = red_flag_floor(text, session.age_years)
        if hit and _rank(FRENCH_TO_PRIORITY[hit.level]) < _rank(priority):
            priority, level = FRENCH_TO_PRIORITY[hit.level], hit.level
            reason = f"{hit.name} (« {hit.excerpt} ») : {hit.motif}, tri {hit.level}"
            result.guards.append(Guard("drapeau_rouge", reason, hit.level))
        session.final = (priority, level)
        result.priority, result.french_level = priority, level
        return result

    def _handover(
        self, result: TriageResult, session: Session, why: str, text: str = ""
    ) -> TriageResult:
        """Relais à l'IOA, avec le plancher des constantes et des drapeaux rouges du récit (y
        compris le message en cours) : ni l'un ni l'autre ne passe par le modèle. Vérification
        de la v12 (16/11/2026) : douleur thoracique typique pendant un démarrage à froid →
        relais sans aucun niveau."""
        result.status = "relais_ioa"
        result.turn = session.turns
        result.message = f"Évaluation à faire par l'infirmier ou l'infirmière d'accueil ({why})."
        priority, level = None, None
        floor = vital_floor(session.vitals, session.age_years)
        if floor:
            priority, level = FRENCH_TO_PRIORITY[floor.level], floor.level
            result.guards.append(Guard("constantes", floor.reason, floor.level))
        story = " ".join([*session.story, text.strip()])
        hit = red_flag_floor(story, session.age_years)
        if hit and (
            priority is None
            or _severity(FRENCH_TO_PRIORITY[hit.level], hit.level) < _severity(priority, level)
        ):
            priority, level = FRENCH_TO_PRIORITY[hit.level], hit.level
            reason = f"{hit.name} (« {hit.excerpt} ») : {hit.motif}, tri {hit.level}"
            result.guards.append(Guard("drapeau_rouge", reason, hit.level))
        if priority is not None:
            result.priority, result.french_level = priority, level
            label = f"{PRIORITY_LABEL[priority]} (tri FRENCH {level})"
            reasons = " ; ".join(g.reason for g in result.guards)
            result.message += f"\nNiveau minimal : {label}, {reasons}."
        return result
