"""API de démonstration : pour l'instant, le seul contrôle d'état."""

from fastapi import FastAPI

from triage import __version__
from triage.config import settings

app = FastAPI(title="Agent de triage CHSA", version=__version__)


@app.get("/api/v1/healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "version": __version__, "model": settings.served_model_id}
