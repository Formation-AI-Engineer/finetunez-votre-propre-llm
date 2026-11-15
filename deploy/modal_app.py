"""Démonstration sur Modal : serveur vLLM (GPU L4, A10G en secours) et API FastAPI (CPU).

Préalables (une fois) :
  uv tool install modal==1.6.4 && modal token new
  modal secret create triage-chsa-hf HF_TOKEN=<jeton en lecture du dépôt privé>
  modal secret create triage-chsa-api API_KEY=<…> AUDIT_API_KEY=<…> VLLM_API_KEY=<…> \
      VLLM_BASE_URL=https://<espace>--triage-chsa-vllm.modal.run/v1
Déploiement : PYTHONPATH=src modal deploy deploy/modal_app.py
  (MODEL_REVISION pour une autre révision)

Coûts : le GPU s'éteint après 5 minutes sans requête (scaledown_window) ; aucun conteneur ne
tourne au repos. Le premier appel après l'arrêt attend le chargement du modèle (environ 1 à
2 minutes). Les sessions de questionnaire sont en mémoire : l'API tourne dans un seul conteneur.
Le journal d'audit est écrit dans un volume Modal persistant.

Changer de modèle = changer MODEL_REVISION et redéployer (révision fixée, jamais « main »).
"""

from __future__ import annotations

import os
import subprocess

import modal

MODEL_ID = os.environ.get("MODEL_ID", "lcamara/triage-chsa-qwen3-1.7b")
# Poids fusionnés publiés le 13/11/2026 (étape Kaggle `final`, docs/EVALUATION.md).
MODEL_REVISION = os.environ.get("MODEL_REVISION", "97e8679033fcfd24cdd28f9b4218127cbf9918f8")
VLLM_IMAGE = "vllm/vllm-openai:v0.32.0"
SERVED_NAME = "triage-chsa"
PORT = 8000

app = modal.App("triage-chsa")
hf_cache = modal.Volume.from_name("triage-chsa-hf-cache", create_if_missing=True)
audit_volume = modal.Volume.from_name("triage-chsa-audit", create_if_missing=True)

vllm_image = (
    modal.Image.from_registry(VLLM_IMAGE)
    .entrypoint([])
    # L'image n'a que `python3` ; Modal cherche `python` pour détecter la version.
    .run_commands("ln -sf /usr/bin/python3 /usr/bin/python")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "0", "MODEL_ID": MODEL_ID, "MODEL_REVISION": MODEL_REVISION})
)


@app.function(
    image=vllm_image,
    gpu=["L4", "A10G"],  # A10G si aucun L4 libre (24 Go, même ordre de coût)
    secrets=[modal.Secret.from_name("triage-chsa-hf"), modal.Secret.from_name("triage-chsa-api")],
    volumes={"/root/.cache/huggingface": hf_cache},
    scaledown_window=300,
    timeout=3600,
    max_containers=1,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=PORT, startup_timeout=600)
def vllm() -> None:
    revision = os.environ["MODEL_REVISION"]
    if not revision:
        raise RuntimeError("MODEL_REVISION manquante : la révision du modèle doit être fixée.")
    cmd = [
        "vllm",
        "serve",
        os.environ["MODEL_ID"],
        "--revision",
        revision,
        "--served-model-name",
        SERVED_NAME,
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
        "--api-key",
        os.environ["VLLM_API_KEY"],
        "--dtype",
        "bfloat16",
        "--max-model-len",
        "4096",
        "--gpu-memory-utilization",
        "0.90",
        # Réglages de génération fixés par le client (src/triage/llm.py), pas par le modèle.
        "--generation-config",
        "vllm",
    ]
    subprocess.Popen(cmd)


api_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject("pyproject.toml")
    .env({"APP_ENV": "prod", "AUDIT_LOG_PATH": "/audit/interactions.jsonl"})
    .workdir("/root")
    .add_local_dir("configs", "/root/configs")
    .add_local_python_source("triage")
)


@app.function(
    image=api_image,
    secrets=[modal.Secret.from_name("triage-chsa-api")],
    volumes={"/audit": audit_volume},
    scaledown_window=300,
    max_containers=1,  # sessions en mémoire
)
@modal.concurrent(max_inputs=32)
@modal.asgi_app()
def api():
    import asyncio

    from triage.api.main import app as fastapi_app

    # Journal persistant même si le conteneur s'arrête : commit du volume après chaque tour, mais
    # en arrière-plan et regroupé (un seul commit à la fois, relancé s'il reste des écritures).
    # Un commit synchrone dans le middleware bloquait la boucle d'événements (~5 s par requête,
    # requêtes sérialisées) : mesuré au test de charge du 15/11/2026.
    state = {"dirty": False, "task": None}

    async def commit_loop() -> None:
        while state["dirty"]:
            state["dirty"] = False
            await audit_volume.commit.aio()
        state["task"] = None

    @fastapi_app.middleware("http")
    async def commit_audit(request, call_next):
        response = await call_next(request)
        if request.url.path == "/api/v1/triage":
            state["dirty"] = True
            if state["task"] is None:
                state["task"] = asyncio.create_task(commit_loop())
        return response

    return fastapi_app
