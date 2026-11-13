"""Client du serveur vLLM (API au format OpenAI, `vllm serve`).

Mêmes réglages de génération qu'à l'évaluation (scripts/evaluate.py) : décodage glouton, au plus
320 jetons, mode sans raisonnement (`enable_thinking=False`, bloc <think></think> vide comme à
l'entraînement).
"""

from __future__ import annotations

import httpx

from triage.service import ModelUnavailable

MAX_TOKENS = 320


class VLLMClient:
    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model_id = model_id
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport
        )

    def complete(self, messages: list[dict]) -> str:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = self._http.post("/chat/completions", json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
            raise ModelUnavailable(str(error)) from error

    def ready(self) -> bool:
        try:
            return self._http.get("/models", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False
