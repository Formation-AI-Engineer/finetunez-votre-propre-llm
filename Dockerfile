# API de pré-triage (CPU). Le modèle est servi à part par vLLM (docker-compose.yml).
FROM python:3.12.8-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
# Dépendances d'abord (couche en cache), sans les extras d'entraînement ni les outils de dev.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY configs/french_table.json ./configs/french_table.json
RUN uv sync --locked --no-dev
RUN useradd --create-home triage && mkdir -p outputs/audit && chown -R triage outputs
USER triage
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/healthcheck')"
CMD ["/app/.venv/bin/uvicorn", "triage.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
