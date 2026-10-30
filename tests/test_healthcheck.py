from fastapi.testclient import TestClient

from triage import __version__
from triage.api.main import app


def test_healthcheck() -> None:
    response = TestClient(app).get("/api/v1/healthcheck")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == __version__
