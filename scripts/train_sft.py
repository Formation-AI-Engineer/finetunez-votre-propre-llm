"""Fine-tuning supervisé (SFT) avec LoRA de Qwen3-1.7B-Base, configuré par configs/sft.yaml.

Usage (sur GPU, une seule carte visible) :
  CUDA_VISIBLE_DEVICES=0 uv run --extra train python scripts/train_sft.py --name sft
  options : --set training.learning_rate=1e-4 (répétable), --limit 100 (petit run),
            --resume (reprend au dernier checkpoint de outputs/sft/<name>/)

Étapes : lecture du dataset sur le Hub (révision fixée), retrait des exemples plus longs que
`training.max_length` (au tokenizer exact, plutôt que de les tronquer), contrôle du rendu du chat
template et du jeton de fin, entraînement LoRA (perte sur la réponse seulement), puis écriture de
l'adaptateur retenu dans outputs/sft/<name>/best et du journal outputs/sft/<name>/run.json
(configuration, révision du dataset, commit, effectifs, pertes, durée, mémoire GPU).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import torch
import yaml
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.trainer_utils import get_last_checkpoint
from trl import SFTConfig, SFTTrainer

from triage.evaluation import dataset_file
from triage.training import apply_overrides, load_rows, sample_rows

END_OF_TURN = "<|im_end|>"  # fin de tour du chat template Qwen3, jeton de fin appris au SFT


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def length(tokenizer, row: dict) -> int:
    encoded = tokenizer.apply_chat_template(
        row["prompt"] + row["completion"],
        tokenize=True,
        return_dict=True,
        **row["chat_template_kwargs"],
    )
    return len(encoded["input_ids"])


def special_token_ids(tokenizer, tokens: list[str]) -> dict[str, int]:
    """Indices des jetons à entraîner ; erreur si l'un d'eux n'est pas un jeton unique du
    vocabulaire (il serait découpé, et c'est un autre jeton qui serait entraîné)."""
    ids = {t: tokenizer.convert_tokens_to_ids(t) for t in tokens}
    unknown = [t for t, i in ids.items() if i is None or i == tokenizer.unk_token_id]
    if unknown:
        raise SystemExit(f"jetons absents du vocabulaire : {unknown}")
    return ids


def drop_too_long(tokenizer, rows: list[dict], max_length: int) -> tuple[list[dict], int]:
    """Retire les exemples trop longs : tronqués, ils perdraient la fin de la réponse, et le
    modèle apprendrait à ne pas terminer."""
    kept = [r for r in rows if length(tokenizer, r) <= max_length]
    return kept, len(rows) - len(kept)


def check_template(trainer: SFTTrainer, tokenizer) -> dict:
    """Contrôle sur le premier exemple tokenisé : la perte porte sur la réponse, qui commence
    après le bloc <think></think> vide et se termine par <|im_end|>."""
    example = trainer.train_dataset[0]
    # TRL convertit le masque de la réponse en `labels` : -100 sur les jetons hors perte.
    ids, labels = example["input_ids"], example["labels"]
    learned = [t for t, label in zip(ids, labels, strict=True) if label != -100]
    prompt = tokenizer.decode([t for t, label in zip(ids, labels, strict=True) if label == -100])
    completion = tokenizer.decode(learned)
    end_id = tokenizer.convert_tokens_to_ids(END_OF_TURN)
    checks = {
        "prompt_ends_with_empty_think": prompt.endswith("<think>\n\n</think>\n\n"),
        "completion_ends_with_end_of_turn": end_id in learned[-2:],
        "single_end_of_turn_in_completion": learned.count(end_id) == 1,
        "learned_tokens": len(learned),
    }
    print("---- rendu du premier exemple (fin du prompt | réponse apprise) ----")
    print(repr(prompt[-200:]))
    print(repr(completion))
    print("---- contrôles :", checks)
    if not all(checks.values()):  # learned_tokens == 0 échoue aussi
        raise SystemExit("Rendu du chat template inattendu : entraînement arrêté.")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--name", required=True, help="nom du run : outputs/sft/<name>/")
    parser.add_argument("--config", default="configs/sft.yaml")
    parser.add_argument("--set", action="append", default=[], dest="overrides", metavar="CLE=VAL")
    parser.add_argument("--limit", type=int, help="au plus n exemples d'entraînement (petit run)")
    parser.add_argument("--resume", action="store_true", help="reprendre au dernier checkpoint")
    args = parser.parse_args()

    if torch.cuda.device_count() > 1 and "LOCAL_RANK" not in os.environ:
        # Sinon le Trainer répartit le lot sur les deux T4 (DataParallel), plus lent et instable.
        raise SystemExit("Plusieurs GPU visibles : fixer CUDA_VISIBLE_DEVICES=0 (ou 1).")

    base = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    config = apply_overrides(base, args.overrides)
    train_cfg = dict(config["training"])
    out_dir = Path("outputs/sft") / args.name
    start = time.time()

    # ------------------------------------------------------------------ données
    tokenizer = AutoTokenizer.from_pretrained(config["model_id"])
    max_length = train_cfg["max_length"]
    train_rows, train_sources = load_rows(dataset_file(config["dataset"], "train"))
    train_rows = sample_rows(train_rows, args.limit, config["seed"])
    train_rows, train_dropped = drop_too_long(tokenizer, train_rows, max_length)
    eval_rows, _ = load_rows(dataset_file(config["dataset"], "validation"))
    eval_rows, eval_dropped = drop_too_long(tokenizer, eval_rows, max_length)
    print(
        f"{len(train_rows)} exemples d'entraînement ({train_dropped} > {max_length} jetons "
        f"retirés), {len(eval_rows)} de validation ({eval_dropped} retirés)"
    )

    # ------------------------------------------------------------------ modèle
    # bf16 à partir d'Ampere (capacité 8) ; le T4 (Turing, 7.5) passe en fp16. Pas de
    # torch.cuda.is_bf16_supported() : il compte le bf16 émulé, très lent, et répond oui sur T4.
    # PEFT garde les poids LoRA en fp32.
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"], dtype=torch.bfloat16 if bf16 else torch.float16
    )
    lora = dict(config["lora"])
    token_ids = special_token_ids(tokenizer, lora.pop("trainable_tokens", []))
    peft_config = LoraConfig(
        task_type="CAUSAL_LM",
        bias="none",
        # Lignes de la table d'embeddings entraînées ; table partagée avec la sortie
        # (tie_word_embeddings), que PEFT met à jour en même temps.
        trainable_token_indices=list(token_ids.values()) or None,
        **lora,
    )

    report_to = "wandb" if os.environ.get("WANDB_API_KEY") else "none"
    no_eval = train_cfg.get("eval_strategy", "no") == "no"
    # Valeurs par défaut du projet ; celles de configs/sft.yaml (et de --set) l'emportent.
    settings = {
        "run_name": args.name,
        "seed": config["seed"],
        "data_seed": config["seed"],
        "bf16": bf16,
        "fp16": not bf16,
        "gradient_checkpointing": True,
        "completion_only_loss": True,  # perte sur la réponse seulement, pas sur la question
        "eos_token": END_OF_TURN,
        "report_to": report_to,
        "save_strategy": train_cfg.get("eval_strategy", "steps"),
        "save_steps": train_cfg.get("eval_steps", 500),
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
    } | train_cfg
    if no_eval:
        # Petit run sans validation : rien à comparer, seul l'adaptateur final est écrit.
        settings |= {"save_strategy": "no", "load_best_model_at_end": False}
    sft_config = SFTConfig(output_dir=str(out_dir), **settings)

    if report_to == "wandb":
        import wandb

        wandb.init(
            project=os.environ.get("WANDB_PROJECT", "triage-chsa"),
            name=args.name,
            job_type="sft",
            config={
                "config": config,
                "overrides": args.overrides,
                "git_commit": git_commit(),
                "limit": args.limit,
                "train_examples": len(train_rows),
            },
        )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=None if no_eval else Dataset.from_list(eval_rows),
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.model.print_trainable_parameters()
    template_checks = check_template(trainer, tokenizer)

    # ------------------------------------------------------------------ entraînement
    resume = get_last_checkpoint(str(out_dir)) if args.resume and out_dir.exists() else None
    if args.resume:
        print(f"Reprise : {resume or 'aucun checkpoint, départ de zéro'}")
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    result = trainer.train(resume_from_checkpoint=resume)

    best_dir = out_dir / "best"
    trainer.save_model(
        str(best_dir)
    )  # meilleur checkpoint si load_best_model_at_end, sinon le dernier
    tokenizer.save_pretrained(str(best_dir))

    history = trainer.state.log_history
    eval_losses = [h["eval_loss"] for h in history if "eval_loss" in h]
    train_losses = [h["loss"] for h in history if "loss" in h]
    run = {
        "name": args.name,
        "git_commit": git_commit(),
        "config": config,
        "overrides": args.overrides,
        "limit": args.limit,
        "resumed_from": resume,
        "train_examples": len(train_rows),
        "train_sources_before_limit": dict(train_sources),
        "train_dropped_too_long": train_dropped,
        "eval_examples": 0 if no_eval else len(eval_rows),
        "eval_dropped_too_long": eval_dropped,
        "template_checks": template_checks,
        "trainable_tokens": token_ids,
        "training_settings": {k: v for k, v in settings.items() if k != "report_to"},
        "precision": "bf16" if bf16 else "fp16",
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "peak_gpu_memory_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2)
        if torch.cuda.is_available()
        else None,
        "steps": trainer.state.global_step,
        "first_train_loss": train_losses[0] if train_losses else None,
        "last_train_loss": train_losses[-1] if train_losses else None,
        "train_metrics": result.metrics,
        "eval_losses": eval_losses,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "best_eval_loss": trainer.state.best_metric,
        "minutes": round((time.time() - start) / 60, 1),
        "adapter": str(best_dir),
    }
    (out_dir / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: run[k]
                for k in (
                    "steps",
                    "first_train_loss",
                    "last_train_loss",
                    "best_eval_loss",
                    "best_checkpoint",
                    "minutes",
                    "peak_gpu_memory_gib",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
