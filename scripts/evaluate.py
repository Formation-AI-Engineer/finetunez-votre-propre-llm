"""Évalue un modèle (de base, ou avec un adaptateur LoRA) sur les vignettes de triage et les QCM.

Usage (sur GPU) :
  uv run --extra train python scripts/evaluate.py --name base                 # modèle de base
  uv run --extra train python scripts/evaluate.py --name base-fewshot --few-shot --batch-size 8
  uv run --extra train python scripts/evaluate.py --name sft --adapter outputs/sft/<nom>/best
  uv run --extra train python scripts/evaluate.py --name dpo \
      --adapter hf://<utilisateur>/triage-chsa-adapters/<sft>@<révision> \
      --adapter outputs/dpo/<nom>/best
  options : --split validation|test, --limit 20 (essai rapide), --batch-size 16

Écrit dans outputs/eval/<name>/<split>/ : predictions.jsonl (réponse brute de chaque question),
summary.json et summary.md (métriques, intervalles de confiance, seuils, conditions du run).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

from triage.evaluation import (
    EvalItem,
    dataset_file,
    load_items,
    pick_examples,
    score,
    to_markdown,
    with_examples,
    write_json,
)
from triage.training import resolve_adapter

# Longueur maximale de la réponse. Corrigés de validation (tokenizer Qwen3) : au plus 217 jetons
# pour une vignette, 112 pour un QCM. Marge d'environ 1,5 ; au-delà on coupe, ce qui ne gêne pas
# la lecture puisque le niveau et les lettres sont en tête de réponse.
MAX_NEW_TOKENS = {"triage": 320, "qcm": 160}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def pick_dtype(name: str, device: str) -> torch.dtype:
    if name == "auto":
        if not device.startswith("cuda"):
            return torch.float32
        # bf16 seulement à partir d'Ampere ; le T4 (capacité 7.5) passe en fp16.
        major = torch.cuda.get_device_capability(device)[0]
        return torch.bfloat16 if major >= 8 else torch.float16
    return {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[name]


def load_model(model_id: str, adapters: list[str], dtype: torch.dtype, device: str):
    """Modèle de base et adaptateurs empilés dans l'ordre : chacun, sauf le dernier, est fusionné
    dans les poids avant de charger le suivant. L'adaptateur DPO a été entraîné sur le modèle
    SFT fusionné (scripts/train_dpo.py) : il se charge après l'adaptateur SFT."""
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenizer.padding_side = "left"  # en génération, le texte doit finir au même endroit
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype, device_map=device)
    if adapters:
        from peft import PeftModel

        for i, adapter in enumerate(adapters):
            model = PeftModel.from_pretrained(model, resolve_adapter(adapter))
            if i < len(adapters) - 1:
                model = model.merge_and_unload()
    model.eval()
    return tokenizer, model


def render(tokenizer, item: EvalItem) -> str:
    # Même mise en forme qu'à l'entraînement : modèle de conversation Qwen3, sans raisonnement.
    return tokenizer.apply_chat_template(
        item.messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )


@torch.inference_mode()
def generate(
    tokenizer, model, items: list[EvalItem], batch_size: int, out_path: Path
) -> tuple[dict[str, str], dict]:
    """Réponses par identifiant, et statistiques (jetons générés, réponses coupées)."""
    # Le modèle de base termine par <|endoftext|>, le modèle affiné par <|im_end|> : on s'arrête
    # au premier des deux.
    stop_ids = [tokenizer.convert_tokens_to_ids("<|im_end|>"), tokenizer.eos_token_id]
    prompts = {i.id: render(tokenizer, i) for i in items}
    answers: dict[str, str] = {}
    stats = {"generated_tokens": 0, "truncated": 0}
    with out_path.open("w", encoding="utf-8") as out:
        for task in sorted({i.task for i in items}):
            # Prompts de longueur voisine dans le même lot : moins de remplissage, plus rapide.
            group = sorted((i for i in items if i.task == task), key=lambda i: len(prompts[i.id]))
            for start in range(0, len(group), batch_size):
                batch = group[start : start + batch_size]
                enc = tokenizer(
                    [prompts[i.id] for i in batch], return_tensors="pt", padding=True
                ).to(model.device)
                output = model.generate(
                    **enc,
                    max_new_tokens=MAX_NEW_TOKENS[task],
                    do_sample=False,
                    eos_token_id=stop_ids,
                    pad_token_id=tokenizer.pad_token_id,
                )
                new_tokens = output[:, enc["input_ids"].shape[1] :]
                for item, tokens in zip(batch, new_tokens, strict=True):
                    ended = any(t in stop_ids for t in tokens.tolist())
                    n = int((tokens != tokenizer.pad_token_id).sum())
                    text = tokenizer.decode(tokens, skip_special_tokens=True).strip()
                    answers[item.id] = text
                    stats["generated_tokens"] += n
                    stats["truncated"] += not ended
                    record = {
                        "id": item.id,
                        "task": item.task,
                        "source": item.source,
                        "style": item.style,
                        "expected": item.expected,
                        "answer": text,
                        "tokens": n,
                        "truncated": not ended,
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                done = start + len(batch)
                print(f"  {task} : {done}/{len(group)}", flush=True)
    return answers, stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--name", required=True, help="nom du run (base, sft, dpo…)")
    parser.add_argument("--config", default="configs/sft.yaml")
    parser.add_argument(
        "--adapter",
        action="append",
        default=[],
        dest="adapters",
        help="adaptateur LoRA (dossier ou hf://…@révision) ; répétable : SFT puis DPO",
    )
    parser.add_argument("--split", default="validation", choices=("validation", "test"))
    parser.add_argument("--limit", type=int, help="au plus n questions par tâche (essai)")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cuda:0", help="cuda:0, cuda:1, ou cpu (essai)")
    parser.add_argument("--dtype", default="auto", choices=("auto", "fp16", "bf16", "fp32"))
    parser.add_argument(
        "--few-shot",
        action="store_true",
        help="vignettes seulement, précédées de 3 exemples résolus du jeu d'entraînement",
    )
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    dataset = config["dataset"]
    data_path = dataset_file(dataset, args.split)
    items = load_items(data_path, limit=args.limit)
    if args.few_shot:
        # Vignettes seulement : en few-shot, le modèle de base recopie les QCM d'exemple au lieu
        # de répondre (vérifié en fp16 et en fp32, docs/EVALUATION.md).
        examples = pick_examples(dataset_file(dataset, "train"))
        items = [with_examples(i, examples["triage"]) for i in items if i.task == "triage"]
    out_dir = Path("outputs/eval") / args.name / args.split
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{len(items)} questions ({data_path.name}) -> {out_dir}")

    dtype = pick_dtype(args.dtype, args.device)
    tokenizer, model = load_model(config["model_id"], args.adapters, dtype, args.device)
    start = time.time()
    answers, stats = generate(
        tokenizer, model, items, args.batch_size, out_dir / "predictions.jsonl"
    )
    seconds = time.time() - start

    summary = score(items, answers)
    summary["run"] = {
        "name": args.name,
        "model_id": config["model_id"],
        "adapters": args.adapters,
        "split": args.split,
        "limit": args.limit,
        "few_shot": args.few_shot,
        "dataset": dataset,
        "git_commit": git_commit(),
        "dtype": str(dtype).removeprefix("torch."),
        "gpu": torch.cuda.get_device_name(args.device) if args.device.startswith("cuda") else "cpu",
        "batch_size": args.batch_size,
        "max_new_tokens": MAX_NEW_TOKENS,
        "seconds": round(seconds),
        "generated_tokens": stats["generated_tokens"],
        "tokens_per_second": round(stats["generated_tokens"] / seconds, 1),
        "truncated_answers": stats["truncated"],
    }
    write_json(summary, out_dir / "summary.json")
    details = (
        [args.split]
        + (["few-shot"] if args.few_shot else [])
        + (["essai limité"] if args.limit else [])
    )
    title = f"Évaluation `{args.name}` ({', '.join(details)})"
    markdown = to_markdown(summary, title)
    markdown += (
        f"\nRéponses coupées à la longueur maximale : {stats['truncated']}/{len(items)} ; "
        f"durée {seconds / 60:.1f} min, {summary['run']['tokens_per_second']} jetons/s "
        f"({summary['run']['dtype']}, {summary['run']['gpu']}).\n"
    )
    (out_dir / "summary.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
