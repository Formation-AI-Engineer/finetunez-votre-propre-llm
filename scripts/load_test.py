"""Test de charge de l'API déployée : latence p50 / p95, débit, temps au premier jeton.

Requêtes : premier message patient des vignettes de triage du jeu de test (un début de
questionnaire par requête, nouvelle session à chaque fois). Deux latences par requête :
- `client_ms` : vue du client (réseau compris, ici depuis la France vers us-east) ;
- `server_ms` : `latency_ms` renvoyé par l'API (appel au modèle + garde-fous, sans le réseau
  client). Le seuil p95 ≤ 3 s s'applique à la latence serveur ; la latence client est rapportée
  à côté.
Temps au premier jeton : appels directs à vLLM en streaming (même prompt système, même réglage).

Usage (clés lues dans l'environnement, jamais en argument) :
  set -a; . ~/.config/triage-chsa/api.env; set +a
  uv run python scripts/load_test.py --api https://…-api.us-east.modal.run \
      --vllm https://…-vllm.us-east.modal.run --n 60 --concurrency 1 4 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TEST_SET = ROOT / "data/processed/sft/test.jsonl"
STOP_TOKEN_IDS = [151645, 151643]


def load_prompts(n: int) -> tuple[str, list[str]]:
    rows = [json.loads(line) for line in TEST_SET.open(encoding="utf-8")]
    rows = [r for r in rows if r["metadata"]["source"] == "french_vignettes"]
    system = next(m["content"] for m in rows[0]["prompt"] if m["role"] == "system")
    firsts = [next(m["content"] for m in r["prompt"] if m["role"] == "user") for r in rows]
    return system, firsts[:n]


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(q / 100 * (len(ordered) - 1))))
    return ordered[k]


def summary(values: list[float]) -> dict:
    return {
        "p50": round(pct(values, 50)),
        "p95": round(pct(values, 95)),
        "max": round(max(values)),
        "mean": round(statistics.mean(values)),
    }


async def run_api(api: str, key: str, prompts: list[str], concurrency: int) -> dict:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []

    async def one(client: httpx.AsyncClient, message: str) -> None:
        async with sem:
            start = time.perf_counter()
            r = await client.post("/api/v1/triage", json={"message": message})
            elapsed = (time.perf_counter() - start) * 1000
            body = r.json() if r.status_code == 200 else {}
            results.append(
                {
                    "http": r.status_code,
                    "client_ms": elapsed,
                    "server_ms": body.get("latency_ms"),
                    "status": body.get("status"),
                }
            )

    async with httpx.AsyncClient(base_url=api, headers={"X-API-Key": key}, timeout=120) as client:
        start = time.perf_counter()
        await asyncio.gather(*(one(client, p) for p in prompts))
        wall = time.perf_counter() - start

    ok = [r for r in results if r["http"] == 200 and r["status"] != "relais_ioa"]
    statuses: dict[str, int] = {}
    for r in results:
        label = r["status"] or f"http_{r['http']}"
        statuses[label] = statuses.get(label, 0) + 1
    return {
        "concurrency": concurrency,
        "requests": len(results),
        "ok": len(ok),
        "statuses": statuses,
        "throughput_rps": round(len(results) / wall, 2),
        "server_ms": summary([r["server_ms"] for r in ok]) if ok else None,
        "client_ms": summary([r["client_ms"] for r in ok]) if ok else None,
        "server_p95_le_3s": bool(ok) and pct([r["server_ms"] for r in ok], 95) <= 3000,
    }


async def run_ttft(vllm: str, key: str, system: str, prompts: list[str]) -> dict:
    ttft, total = [], []
    async with httpx.AsyncClient(
        base_url=vllm.rstrip("/") + "/v1", headers={"Authorization": f"Bearer {key}"}, timeout=120
    ) as client:
        for message in prompts:
            payload = {
                "model": "triage-chsa",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                "temperature": 0,
                "max_tokens": 320,
                "chat_template_kwargs": {"enable_thinking": False},
                "stop_token_ids": STOP_TOKEN_IDS,
                "stream": True,
            }
            start = time.perf_counter()
            first = None
            async with client.stream("POST", "/chat/completions", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    delta = json.loads(line[6:])["choices"][0]["delta"].get("content")
                    if delta and first is None:
                        first = (time.perf_counter() - start) * 1000
            total.append((time.perf_counter() - start) * 1000)
            ttft.append(first if first is not None else total[-1])
    return {"requests": len(prompts), "ttft_ms": summary(ttft), "total_ms": summary(total)}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--vllm", required=True)
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8])
    parser.add_argument("--ttft-n", type=int, default=20)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/load_test.json")
    args = parser.parse_args()

    system, prompts = load_prompts(args.n)
    api_key, vllm_key = os.environ["API_KEY"], os.environ["VLLM_API_KEY"]

    # Échauffement, non compté : jusqu'à une vraie réponse du modèle (un redéploiement relance
    # aussi vLLM ; pendant son démarrage à froid, l'API répond « relais IOA » après 30 s).
    for attempt in range(20):
        warm = await run_api(args.api, api_key, prompts[:1], 1)
        if warm["ok"]:
            break
        print(f"échauffement {attempt + 1} : modèle pas encore prêt")
    else:
        raise SystemExit("Le modèle ne répond pas : mesure annulée.")
    await run_api(args.api, api_key, prompts[:4], 4)

    report = {"date": time.strftime("%Y-%m-%d %H:%M"), "n": len(prompts), "api": []}
    for c in args.concurrency:
        report["api"].append(await run_api(args.api, api_key, prompts, c))
        print(json.dumps(report["api"][-1], ensure_ascii=False))
    report["ttft"] = await run_ttft(args.vllm, vllm_key, system, prompts[: args.ttft_n])
    print(json.dumps(report["ttft"], ensure_ascii=False))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
