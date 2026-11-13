"""Fusionne les adaptateurs retenus (SFT puis DPO) dans Qwen3-1.7B-Base : poids finaux à servir
avec vLLM, qui ne sait pas charger les lignes de jetons entraînées d'un adaptateur LoRA.

Usage (Kaggle, étape `final`) :
  uv run --extra train python scripts/merge_final.py --out outputs/final/triage-chsa-qwen3-1.7b \
      --adapter hf://…/sft-r16-lr2e-4@<révision> --adapter hf://…/dpo-b0.1-lr3e-5@<révision>

La fusion se fait en fp32 sur CPU (pas d'arrondi fp16 cumulé), puis les poids sont enregistrés en
bf16, le type du modèle de base. Contrôle ensuite, sur GPU en fp16 comme à l'évaluation : le
modèle fusionné relu depuis le disque prédit les mêmes jetons que les adaptateurs empilés, sur
des réponses de référence de la validation. Écrit aussi merge.json (adaptateurs, contrôles).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import torch
import yaml
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from triage.evaluation import dataset_file
from triage.training import resolve_adapter

MIN_SAME_TOKENS = 0.98
N_CHECK = 16


def stack(model, adapters: list[str], keep_last: bool):
    """Empile les adaptateurs ; chacun est fusionné avant le suivant, le dernier aussi sauf si
    `keep_last` (référence : comme scripts/evaluate.py)."""
    for i, adapter in enumerate(adapters):
        model = PeftModel.from_pretrained(model, resolve_adapter(adapter))
        if i < len(adapters) - 1 or not keep_last:
            model = model.merge_and_unload()
    return model.eval()


@torch.inference_mode()
def same_tokens(reference, merged, tokenizer, rows: list[dict], device: str) -> float:
    """Part des positions où les deux modèles prédisent le même jeton (lecture forcée de la
    conversation de référence)."""
    agree = total = 0
    for row in rows:
        text = tokenizer.apply_chat_template(
            row["prompt"] + row["completion"], tokenize=False, enable_thinking=False
        )
        ids = tokenizer(text, return_tensors="pt").input_ids.to(device)
        a = reference(input_ids=ids).logits.argmax(-1)
        b = merged(input_ids=ids).logits.argmax(-1)
        agree += (a == b).sum().item()
        total += a.numel()
    return round(agree / total, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--adapter", action="append", required=True, dest="adapters")
    parser.add_argument("--config", default="configs/sft.yaml")
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    model_id = config["model_id"]
    tokenizer = AutoTokenizer.from_pretrained(model_id)

    print(f"---- fusion fp32 sur CPU : {model_id} + {len(args.adapters)} adaptateurs")
    base = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32)
    merged = stack(base, args.adapters, keep_last=False)
    merged.to(torch.bfloat16).save_pretrained(args.out, safe_serialization=True)
    tokenizer.save_pretrained(args.out)
    del base, merged

    print("---- contrôle : modèle fusionné relu contre adaptateurs empilés (fp16)")
    rows = [
        json.loads(line)
        for line in dataset_file(config["dataset"], "validation").read_text().splitlines()[:N_CHECK]
    ]
    reloaded = AutoModelForCausalLM.from_pretrained(
        args.out, dtype=torch.float16, device_map=args.device
    ).eval()
    reference = stack(
        AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float16, device_map=args.device),
        args.adapters,
        keep_last=True,
    )
    embeddings = reloaded.get_input_embeddings().weight
    end_id, start_id = tokenizer.convert_tokens_to_ids(["<|im_end|>", "<|im_start|>"])
    checks = {
        "same_top1_tokens": same_tokens(reference, reloaded, tokenizer, rows, args.device),
        "end_vs_start_cosine": round(
            torch.cosine_similarity(
                embeddings[end_id].float(), embeddings[start_id].float(), dim=0
            ).item(),
            4,
        ),
        "tied_output_embeddings": reloaded.get_output_embeddings().weight.data_ptr()
        == embeddings.data_ptr(),
    }
    print("---- contrôles :", checks)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    (args.out / "merge.json").write_text(
        json.dumps(
            {
                "base_model": model_id,
                "adapters": args.adapters,
                "dtype": "bfloat16",
                "checks": checks,
                "git_commit": commit,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if (
        checks["same_top1_tokens"] < MIN_SAME_TOKENS
        or checks["end_vs_start_cosine"] > 0.99
        or not checks["tied_output_embeddings"]
    ):
        raise SystemExit("Fusion inattendue : poids finaux à ne pas utiliser.")
    print(f"Poids finaux : {args.out}")


if __name__ == "__main__":
    main()
