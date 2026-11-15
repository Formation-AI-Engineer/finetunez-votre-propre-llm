"""Schéma des enregistrements SFT et DPO, et de leurs métadonnées.

Formats attendus par TRL :
- SFT conversationnel « prompt / completion » : listes de messages {role, content} ;
- DPO conversationnel « prompt / chosen / rejected ».
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Language = Literal["fr", "en"]
Task = Literal["qcm", "qa", "triage", "preference"]
Split = Literal["train", "validation", "test"]
FrenchLevel = Literal["1", "2", "3A", "3B", "4", "5"]
PriorityLevel = Literal["maximale", "moderee", "differee"]

# Niveau de confiance de la réponse attendue, du plus solide au plus fragile.
Confidence = Literal[
    "reference",  # corrigé officiel (examen, site institutionnel)
    "human_preference",  # préférence annotée par un humain
    "model_judged",  # préférence attribuée par un LLM juge (GPT-4 dans UltraMedical)
    "synthetic_rules",  # vignette générée par règles à partir du référentiel FRENCH
]

FRENCH_TO_PRIORITY: dict[str, PriorityLevel] = {
    "1": "maximale",
    "2": "maximale",
    "3A": "moderee",
    "3B": "moderee",
    "4": "differee",
    "5": "differee",
}


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class Vitals(BaseModel):
    """Constantes vitales ; une valeur absente n'a pas été mesurée."""

    model_config = ConfigDict(extra="forbid")

    heart_rate: int | None = Field(None, ge=20, le=250, description="FC, /min")
    systolic_bp: int | None = Field(None, ge=40, le=280, description="PAS, mmHg")
    diastolic_bp: int | None = Field(None, ge=20, le=160, description="PAD, mmHg")
    respiratory_rate: int | None = Field(None, ge=4, le=80, description="FR, /min")
    spo2: int | None = Field(None, ge=50, le=100, description="SpO2, %")
    temperature: float | None = Field(None, ge=25.0, le=43.0, description="T°, °C")
    gcs: int | None = Field(None, ge=3, le=15, description="score de Glasgow")
    glycemia: float | None = Field(None, ge=0.5, le=60.0, description="glycémie, mmol/l")


class ClinicalContext(BaseModel):
    """Éléments cliniques structurés, renseignés quand la source les fournit (vignettes)."""

    model_config = ConfigDict(extra="forbid")

    age_years: float | None = Field(None, ge=0, le=120)
    sex: Literal["F", "M"] | None = None
    chief_complaint: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    vitals: Vitals | None = None


class TriageLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    french_level: FrenchLevel
    priority: PriorityLevel
    motif: str
    category: str
    deciding_criterion: str

    @model_validator(mode="after")
    def _priority_matches_french(self) -> TriageLabel:
        expected = FRENCH_TO_PRIORITY[self.french_level]
        if self.priority != expected:
            raise ValueError(
                f"tri {self.french_level} correspond à {expected}, pas {self.priority}"
            )
        return self


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    source_id: str
    source_split: str | None = None
    license: str
    language: Language
    task: Task
    confidence: Confidence
    synthetic: bool = False
    anonymized: bool = False
    medical_subject: str | None = None
    clinical: ClinicalContext | None = None
    triage: TriageLabel | None = None
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistency(self) -> Metadata:
        if self.confidence == "synthetic_rules" and not self.synthetic:
            raise ValueError("une donnée générée par règles doit être marquée synthetic")
        if self.task == "triage" and self.triage is None:
            raise ValueError("une donnée de triage doit porter son niveau attendu")
        return self


def _check_roles(prompt: list[Message], answers: list[list[Message]]) -> None:
    if not prompt or prompt[-1].role != "user":
        raise ValueError("le prompt doit se terminer par un message utilisateur")
    for answer in answers:
        if [m.role for m in answer] != ["assistant"]:
            raise ValueError("une réponse doit contenir exactement un message assistant")


def record_id(source: str, source_id: str, variant: str = "") -> str:
    """Identifiant stable, indépendant de l'ordre de traitement."""
    key = f"{source}|{source_id}|{variant}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class SFTRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prompt: list[Message]
    completion: list[Message]
    metadata: Metadata

    @model_validator(mode="after")
    def _roles(self) -> SFTRecord:
        _check_roles(self.prompt, [self.completion])
        return self


class DPORecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prompt: list[Message]
    chosen: list[Message]
    rejected: list[Message]
    metadata: Metadata

    @model_validator(mode="after")
    def _roles(self) -> DPORecord:
        _check_roles(self.prompt, [self.chosen, self.rejected])
        if self.chosen[0].content.strip() == self.rejected[0].content.strip():
            raise ValueError("chosen et rejected sont identiques")
        return self
