"""Comparaison vLLM / Transformers seul, même GPU (A10G), mêmes requêtes, mêmes réglages.

Requêtes : prompt système + premier message patient de 60 vignettes du jeu de test (comme
`scripts/load_test.py`). Réglages identiques à la production : bf16, décodage glouton, 320 jetons
au plus, arrêt sur <|im_end|> ou <|endoftext|>, mode sans raisonnement.

- Transformers (fonction Modal éphémère sur A10G) : séquentiel (latence par requête, temps au
  premier jeton mesuré par une génération d'un seul jeton), puis lots statiques de 4, 8 et 16
  requêtes (chaque requête attend la fin de son lot).
- vLLM (serveur déployé, appelé en direct sans l'API) : séquentiel, puis 4, 8 et 16 requêtes
  simultanées.
- Concordance : textes identiques et niveau de priorité identique entre les deux moteurs.

Usage :
  set -a; . ~/.config/triage-chsa/api.env; set +a
  PYTHONPATH=src modal run deploy/bench_engines.py --vllm https://…-vllm.us-east.modal.run
Résultat : outputs/bench_engines.json.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import time
from pathlib import Path

import modal

MODEL_ID = "lcamara/triage-chsa-qwen3-1.7b"
MODEL_REVISION = "97e8679033fcfd24cdd28f9b4218127cbf9918f8"
MAX_TOKENS = 320
STOP_TOKEN_IDS = [151645, 151643]  # <|im_end|>, <|endoftext|>
BATCH_SIZES = [4, 8, 16]
ROOT = Path(__file__).resolve().parents[1]

app = modal.App("triage-chsa-bench")
hf_cache = modal.Volume.from_name("triage-chsa-hf-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    # Versions du lockfile (évaluation) ; torch cu126 fonctionne sur l'A10G (sm_86).
    .pip_install(
        "torch==2.14.1",
        index_url="https://download.pytorch.org/whl/cu126",
    )
    .pip_install("transformers==5.22.1", "accelerate==1.15.0")
)


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, round(q / 100 * (len(ordered) - 1))))]


def summary(values: list[float]) -> dict:
    return {
        "p50": round(pct(values, 50)),
        "p95": round(pct(values, 95)),
        "max": round(max(values)),
        "mean": round(statistics.mean(values)),
    }


@app.function(
    image=image,
    gpu="A10G",
    secrets=[modal.Secret.from_name("triage-chsa-hf")],
    volumes={"/root/.cache/huggingface": hf_cache},
    timeout=1800,
)
def bench_transformers(conversations: list[list[dict]]) -> dict:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, dtype=torch.bfloat16, device_map="cuda"
    ).eval()
    prompts = [
        tokenizer.apply_chat_template(
            c, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        for c in conversations
    ]

    @torch.inference_mode()
    def generate(batch: list[str], max_new_tokens: int) -> tuple[list[str], list[int], float]:
        enc = tokenizer(batch, return_tensors="pt", padding=True).to("cuda")
        torch.cuda.synchronize()
        start = time.perf_counter()
        out = model.generate(
            **enc,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=STOP_TOKEN_IDS,
            pad_token_id=tokenizer.pad_token_id,
        )
        torch.cuda.synchronize()
        elapsed = (time.perf_counter() - start) * 1000
        new = out[:, enc["input_ids"].shape[1] :]
        texts, counts = [], []
        for tokens in new.tolist():
            n = next((i + 1 for i, t in enumerate(tokens) if t in STOP_TOKEN_IDS), len(tokens))
            counts.append(n)
            texts.append(tokenizer.decode(tokens[:n], skip_special_tokens=True).strip())
        return texts, counts, elapsed

    generate(prompts[:2], 16)  # échauffement (noyaux CUDA), non compté

    seq_ms, ttft_ms, texts, tokens = [], [], [], []
    for p in prompts:
        ttft_ms.append(generate([p], 1)[2])
        t, n, ms = generate([p], MAX_TOKENS)
        texts += t
        tokens += n
        seq_ms.append(ms)
    report = {
        "gpu": torch.cuda.get_device_name(0),
        "sequential": {
            "latency_ms": summary(seq_ms),
            "ttft_ms": summary(ttft_ms),
            "throughput_rps": round(len(prompts) / (sum(seq_ms) / 1000), 2),
            "tokens_per_s": round(sum(tokens) / (sum(seq_ms) / 1000), 1),
        },
        "texts": texts,
        "batched": [],
    }
    for size in BATCH_SIZES:
        latency, total = [], 0.0
        for start in range(0, len(prompts), size):
            batch = prompts[start : start + size]
            _, _, ms = generate(batch, MAX_TOKENS)
            latency += [ms] * len(batch)  # chaque requête attend la fin de son lot
            total += ms
        report["batched"].append(
            {
                "batch_size": size,
                "latency_ms": summary(latency),
                "throughput_rps": round(len(prompts) / (total / 1000), 2),
            }
        )
    report["gpu_memory_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 1)
    return report


async def bench_vllm(base_url: str, key: str, conversations: list[list[dict]]) -> dict:
    import httpx

    def payload(messages: list[dict], max_tokens: int, stream: bool = False) -> dict:
        return {
            "model": "triage-chsa",
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "stop_token_ids": STOP_TOKEN_IDS,
            "stream": stream,
        }

    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/") + "/v1",
        headers={"Authorization": f"Bearer {key}"},
        timeout=600,
    ) as client:

        async def one(messages: list[dict]) -> tuple[str, int, float, float]:
            start = time.perf_counter()
            first = None
            text = ""
            usage = 0
            body = payload(messages, MAX_TOKENS, stream=True)
            body["stream_options"] = {"include_usage": True}
            async with client.stream("POST", "/chat/completions", json=body) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    chunk = json.loads(line[6:])
                    if chunk.get("usage"):
                        usage = chunk["usage"]["completion_tokens"]
                    for choice in chunk.get("choices", []):
                        delta = choice["delta"].get("content")
                        if delta:
                            if first is None:
                                first = (time.perf_counter() - start) * 1000
                            text += delta
            total = (time.perf_counter() - start) * 1000
            return text.strip(), usage, total, first if first is not None else total

        # Échauffement : réveille le serveur (démarrage à froid possible), non compté.
        await client.post("/chat/completions", json=payload(conversations[0], 16))

        seq = [await one(c) for c in conversations]
        report = {
            "sequential": {
                "latency_ms": summary([s[2] for s in seq]),
                "ttft_ms": summary([s[3] for s in seq]),
                "throughput_rps": round(len(seq) / (sum(s[2] for s in seq) / 1000), 2),
                "tokens_per_s": round(sum(s[1] for s in seq) / (sum(s[2] for s in seq) / 1000), 1),
            },
            "texts": [s[0] for s in seq],
            "concurrent": [],
        }
        for size in BATCH_SIZES:
            sem = asyncio.Semaphore(size)

            async def limited(
                c: list[dict], sem: asyncio.Semaphore = sem
            ) -> tuple[str, int, float, float]:
                async with sem:
                    return await one(c)

            start = time.perf_counter()
            results = await asyncio.gather(*(limited(c) for c in conversations))
            wall = time.perf_counter() - start
            report["concurrent"].append(
                {
                    "concurrency": size,
                    "latency_ms": summary([r[2] for r in results]),
                    "throughput_rps": round(len(results) / wall, 2),
                }
            )
    return report


LEVEL = re.compile(r"Niveau de priorité\s*:\s*([A-ZÉÈ]+)")


def level(text: str) -> str:
    match = LEVEL.search(text)
    return match.group(1) if match else "question"


@app.local_entrypoint()
def main(vllm: str, n: int = 60) -> None:
    rows = [json.loads(line) for line in (ROOT / "data/processed/sft/test.jsonl").open()]
    rows = [r for r in rows if r["metadata"]["source"] == "french_vignettes"][:n]
    conversations = [
        [
            next(m for m in r["prompt"] if m["role"] == "system"),
            next(m for m in r["prompt"] if m["role"] == "user"),
        ]
        for r in rows
    ]

    tf = bench_transformers.remote(conversations)
    print("Transformers :", json.dumps({k: v for k, v in tf.items() if k != "texts"}))
    vl = asyncio.run(bench_vllm(vllm, os.environ["VLLM_API_KEY"], conversations))
    print("vLLM :", json.dumps({k: v for k, v in vl.items() if k != "texts"}))

    pairs = list(zip(tf["texts"], vl["texts"], strict=True))
    agreement = {
        "identical_text": sum(a == b for a, b in pairs),
        "same_level": sum(level(a) == level(b) for a, b in pairs),
        "n": len(pairs),
        "differences": [
            {"transformers": level(a), "vllm": level(b)} for a, b in pairs if level(a) != level(b)
        ],
    }
    print("Concordance :", json.dumps(agreement, ensure_ascii=False))
    out = ROOT / "outputs/bench_engines.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "date": time.strftime("%Y-%m-%d %H:%M"),
                "transformers": tf,
                "vllm": vl,
                "agreement": agreement,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
