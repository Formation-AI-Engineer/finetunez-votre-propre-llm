"""API de pré-triage du CHSA.

- `GET /` : page de démonstration (sans clé ; la clé d'API se saisit dans la page) ;
- `GET /api/v1/healthcheck` : vivacité de l'API (sans clé) ;
- `GET /api/v1/readiness` : le serveur du modèle répond-il ? (sans clé) ;
- `POST /api/v1/triage` : un tour de questionnaire (clé `X-API-Key`). Sans `session_id`, ouvre une
  session ; avec, la poursuit. La réponse est une question, une évaluation (niveau après
  garde-fous), ou un relais à l'IOA si le modèle est indisponible. Chaque tour est journalisé ;
- `GET /api/v1/audit` : consultation du journal (clé d'audit distincte `X-Audit-Key`).
"""

from __future__ import annotations

import secrets
from dataclasses import asdict
from functools import cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from triage import __version__
from triage.api.demo_page import DEMO_HTML
from triage.audit import AuditLog
from triage.config import settings
from triage.data.schema import Vitals
from triage.llm import VLLMClient
from triage.service import TriageService

MAX_MESSAGE_CHARS = 4000

app = FastAPI(title="Agent de triage CHSA", version=__version__)


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    session_id: str | None = Field(None, max_length=64)
    age_years: float | None = Field(None, ge=0, le=120)
    vitals: Vitals | None = None
    observation: str | None = Field(None, max_length=1000, description="observation de l'IOA")


class GuardOut(BaseModel):
    name: str
    reason: str
    french_level: str


class TriageResponse(BaseModel):
    session_id: str
    status: str
    message: str
    priority: str | None
    french_level: str | None
    model_priority: str | None
    guards: list[GuardOut]
    alerts: list[str]
    disclaimer: str
    turn: int
    model_id: str
    latency_ms: int


@cache
def get_audit() -> AuditLog:
    return AuditLog(settings.audit_log_path)


@cache
def get_service() -> TriageService:
    model = VLLMClient(settings.vllm_base_url, settings.served_model_id, settings.vllm_api_key)
    return TriageService(model)


def _check_key(given: str | None, expected: str, default: str) -> None:
    if settings.app_env != "dev" and expected == default:
        raise HTTPException(500, "Clé par défaut refusée hors développement.")
    if given is None or not secrets.compare_digest(given, expected):
        raise HTTPException(401, "Clé absente ou invalide.")


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    _check_key(x_api_key, settings.api_key, "change-me")


def require_audit_key(x_audit_key: Annotated[str | None, Header()] = None) -> None:
    _check_key(x_audit_key, settings.audit_api_key, "change-me-audit")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def demo() -> HTMLResponse:
    # Jamais en cache : une page périmée gardée par le navigateur a masqué un correctif.
    return HTMLResponse(DEMO_HTML, headers={"Cache-Control": "no-store"})


@app.get("/api/v1/healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "version": __version__, "model": settings.served_model_id}


@app.get("/api/v1/readiness")
def readiness(service: Annotated[TriageService, Depends(get_service)]) -> dict[str, bool]:
    ready = getattr(service.model, "ready", lambda: True)()
    if not ready:
        raise HTTPException(503, "Serveur du modèle indisponible.")
    return {"ready": True}


@app.post("/api/v1/triage", response_model=TriageResponse, dependencies=[Depends(require_api_key)])
def triage(
    request: TriageRequest,
    service: Annotated[TriageService, Depends(get_service)],
    audit: Annotated[AuditLog, Depends(get_audit)],
) -> TriageResponse:
    if not request.message.strip():
        raise HTTPException(422, "Message vide.")
    try:
        result = service.triage(
            request.message,
            session_id=request.session_id,
            age_years=request.age_years,
            vitals=request.vitals,
            observation=request.observation,
        )
    except KeyError:
        raise HTTPException(404, "Session inconnue ou expirée.") from None
    audit.record(result, request.model_dump(mode="json", exclude_none=True))
    return TriageResponse(**asdict(result))


@app.get("/api/v1/audit", dependencies=[Depends(require_audit_key)])
def read_audit(
    audit: Annotated[AuditLog, Depends(get_audit)],
    session_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict]:
    return audit.read(session_id, limit)
