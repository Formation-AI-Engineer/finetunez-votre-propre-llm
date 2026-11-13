"""Alignement par préférences (DPO) du modèle SFT, configuré par configs/dpo.yaml.

Usage (sur GPU, une seule carte visible) :
  CUDA_VISIBLE_DEVICES=0 uv run --extra train python scripts/train_dpo.py --name dpo
  options : --set training.beta=0.2 (répétable), --limit 64 (petit run),
            --resume (reprend au dernier checkpoint de outputs/dpo/<name>/)

Étapes :
1. modèle de base + adaptateur SFT (`sft_adapter`, dossier local ou hf://…@révision), fusionné
   dans les poids après un contrôle (mêmes prédictions avant et après la fusion) ;
2. nouvel adaptateur LoRA, entraîné par DPO sur les paires « chosen / rejected ». La référence
   du DPO est le modèle sans ce nouvel adaptateur, c'est-à-dire le modèle SFT ;
3. validation sur deux jeux suivis à part : `triage` (paires françaises « bon niveau contre
   sous-triage ») et `medical` (paires UltraMedical, en anglais) ;
4. écriture de l'adaptateur DPO dans outputs/dpo/<name>/best et du journal run.json.

Pourquoi fusionner d'abord : l'adaptateur SFT entraîne aussi des lignes de jetons
(`trainable_token_indices`). Rechargé tel quel, TRL en ferait la copie de référence sans ces
lignes, et calculerait la perte sans elles (sortie fusionnée de TRL, qui lit `lm_head.weight`
directement). Une fois fusionnées, ce sont des poids ordinaires.

L'adaptateur DPO s'utilise donc par-dessus le modèle SFT fusionné :
  evaluate.py --adapter <sft> --adapter outputs/dpo/<name>/best
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
from peft import LoraConfig, PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer
from transformers.trainer_utils import get_last_checkpoint
from trl import DPOConfig, DPOTrainer

from triage.evaluation import dataset_file
from triage.training import (
    NO_THINKING,
    apply_overrides,
    load_preference_rows,
    resolve_adapter,
    sample_rows,
)

END_OF_TURN = "<|im_end|>"
START_OF_TURN = "<|im_start|>"
TRIAGE_SOURCE = "french_vignettes"
# Métriques de TRL gardées dans run.json, pour l'entraînement et pour chaque jeu de validation.
TRACKED = ("loss", "rewards/accuracies", "rewards/margins", "logps/chosen", "logps/rejected")


class NamedEvalDPOTrainer(DPOTrainer):
    """DPOTrainer dont les métriques de validation portent le nom de leur jeu.

    Avec plusieurs jeux de validation, TRL 1.17 range les métriques DPO de chacun sous le même
    nom (`eval_rewards/accuracies`), seule la perte étant préfixée (`eval_triage_loss`) : les
    courbes des deux jeux se mélangeraient dans W&B. Le préfixe est repris de la perte.
    """

    def log(self, logs: dict[str, float], start_time: float | None = None) -> None:
        prefix = next(
            (k.removesuffix("loss") for k in logs if k.startswith("eval_") and k.endswith("_loss")),
            None,
        )
        if self.model.training or prefix is None:
            super().log(logs, start_time)
            return
        metrics = self._metrics["eval"]
        logs.update({f"{prefix}{key}": sum(v) / len(v) for key, v in metrics.items() if v})
        metrics.clear()
        Trainer.log(self, logs, start_time)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def encode(tokenizer, messages: list[dict]) -> list[int]:
    return tokenizer.apply_chat_template(messages, tokenize=True, return_dict=True, **NO_THINKING)[
        "input_ids"
    ]


def drop_too_long(tokenizer, rows: list[dict], max_length: int) -> tuple[list[dict], int]:
    """Retire les paires dont l'une des deux réponses dépasse max_length avec le prompt :
    tronquée, elle perdrait sa fin (et son <|im_end|>), et la comparaison porterait sur des
    réponses incomplètes."""
    kept = [
        r
        for r in rows
        if max(len(encode(tokenizer, r["prompt"] + r[k])) for k in ("chosen", "rejected"))
        <= max_length
    ]
    return kept, len(rows) - len(kept)


@torch.no_grad()
def merge_sft(model, tokenizer, adapter_dir: str, row: dict):
    """Fusionne l'adaptateur SFT dans les poids et vérifie que le modèle n'a pas changé : mêmes
    jetons prédits avant et après la fusion (fp16 : quelques écarts d'arrondi tolérés), et
    lignes de <|im_end|> et <|im_start|> bien distinctes (lignes entraînées fusionnées)."""
    peft_model = PeftModel.from_pretrained(model, adapter_dir)
    peft_model.eval()
    ids = torch.tensor([encode(tokenizer, row["prompt"] + row["chosen"])], device=model.device)
    before = peft_model(input_ids=ids).logits.float()
    merged = peft_model.merge_and_unload()
    after = merged(input_ids=ids).logits.float()

    embeddings = merged.get_input_embeddings().weight
    end_id, start_id = tokenizer.convert_tokens_to_ids([END_OF_TURN, START_OF_TURN])
    checks = {
        "same_top1_tokens": round((before.argmax(-1) == after.argmax(-1)).float().mean().item(), 4),
        "max_logit_diff": round((before - after).abs().max().item(), 4),
        "end_vs_start_cosine": round(
            torch.cosine_similarity(embeddings[end_id], embeddings[start_id], dim=0).item(), 4
        ),
        # Table d'entrée et de sortie partagées (tie_word_embeddings) : une seule à fusionner.
        "tied_output_embeddings": merged.get_output_embeddings().weight.data_ptr()
        == embeddings.data_ptr(),
    }
    print("---- fusion de l'adaptateur SFT :", checks)
    if (
        checks["same_top1_tokens"] < 0.98
        or checks["end_vs_start_cosine"] > 0.99
        or not checks["tied_output_embeddings"]
    ):
        raise SystemExit("Fusion de l'adaptateur SFT inattendue : entraînement arrêté.")
    return merged, checks


def check_template(trainer: DPOTrainer, tokenizer) -> dict:
    """Contrôle sur la première paire tokenisée : le prompt finit par le bloc <think></think>
    vide, et chaque réponse se termine par un seul <|im_end|>."""
    example = trainer.train_dataset[0]
    prompt = tokenizer.decode(example["prompt_ids"])
    end_id = tokenizer.convert_tokens_to_ids(END_OF_TURN)
    checks = {"prompt_ends_with_empty_think": prompt.endswith("<think>\n\n</think>\n\n")}
    for side in ("chosen", "rejected"):
        ids = example[f"{side}_ids"]
        checks[f"{side}_ends_with_end_of_turn"] = end_id in ids[-2:]
        checks[f"single_end_of_turn_in_{side}"] = ids.count(end_id) == 1
        checks[f"{side}_tokens"] = len(ids)
    print("---- rendu de la première paire (fin du prompt | chosen | rejected) ----")
    print(repr(prompt[-200:]))
    print(repr(tokenizer.decode(example["chosen_ids"])[:300]))
    print(repr(tokenizer.decode(example["rejected_ids"])[:300]))
    print("---- contrôles :", checks)
    if not all(checks.values()):
        raise SystemExit("Rendu du chat template inattendu : entraînement arrêté.")
    return checks


def history(log_history: list[dict], prefix: str) -> dict[str, list[float]]:
    """Séries des métriques suivies : `prefix` vaut "" (entraînement) ou "eval_<jeu>_"."""
    series = {}
    for key in TRACKED:
        values = [round(h[prefix + key], 4) for h in log_history if prefix + key in h]
        if values:
            series[key] = values
    return series


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--name", required=True, help="nom du run : outputs/dpo/<name>/")
    parser.add_argument("--config", default="configs/dpo.yaml")
    parser.add_argument("--set", action="append", default=[], dest="overrides", metavar="CLE=VAL")
    parser.add_argument("--limit", type=int, help="au plus n paires d'entraînement (petit run)")
    parser.add_argument("--resume", action="store_true", help="reprendre au dernier checkpoint")
    args = parser.parse_args()

    if torch.cuda.device_count() > 1 and "LOCAL_RANK" not in os.environ:
        raise SystemExit("Plusieurs GPU visibles : fixer CUDA_VISIBLE_DEVICES=0 (ou 1).")
    if not torch.cuda.is_available():
        raise SystemExit("Pas de GPU : le DPO se lance sur Kaggle.")

    base = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    config = apply_overrides(base, args.overrides)
    train_cfg = dict(config["training"])
    out_dir = Path("outputs/dpo") / args.name
    start = time.time()

    # ------------------------------------------------------------------ données
    tokenizer = AutoTokenizer.from_pretrained(config["model_id"])
    max_length = train_cfg["max_length"]
    train_rows, train_sources = load_preference_rows(
        dataset_file(config["dataset"], "train", "dpo")
    )
    train_rows = sample_rows(train_rows, args.limit, config["seed"])
    train_rows, train_dropped = drop_too_long(tokenizer, train_rows, max_length)
    eval_rows, _ = load_preference_rows(dataset_file(config["dataset"], "validation", "dpo"))
    eval_rows, eval_dropped = drop_too_long(tokenizer, eval_rows, max_length)
    eval_sets = {
        "triage": [r for r in eval_rows if r["source"] == TRIAGE_SOURCE],
        "medical": [r for r in eval_rows if r["source"] != TRIAGE_SOURCE],
    }
    print(
        f"{len(train_rows)} paires d'entraînement ({train_dropped} > {max_length} jetons "
        f"retirées), validation : {len(eval_sets['triage'])} triage, "
        f"{len(eval_sets['medical'])} médicales ({eval_dropped} retirées)"
    )

    def to_dataset(rows: list[dict]) -> Dataset:
        # La source ne sert qu'au découpage ci-dessus ; TRL n'attend que la conversation.
        return Dataset.from_list([{k: v for k, v in r.items() if k != "source"} for r in rows])

    # ------------------------------------------------------------------ modèle
    bf16 = torch.cuda.get_device_capability(0)[0] >= 8  # voir scripts/train_sft.py
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"], dtype=torch.bfloat16 if bf16 else torch.float16
    ).to("cuda")
    sft_dir = resolve_adapter(config["sft_adapter"])
    model, merge_checks = merge_sft(model, tokenizer, sft_dir, train_rows[0])
    peft_config = LoraConfig(task_type="CAUSAL_LM", bias="none", **config["lora"])

    report_to = "wandb" if os.environ.get("WANDB_API_KEY") else "none"
    no_eval = train_cfg.get("eval_strategy", "no") == "no"
    # Valeurs par défaut du projet ; celles de configs/dpo.yaml (et de --set) l'emportent.
    settings = {
        "run_name": args.name,
        "seed": config["seed"],
        "data_seed": config["seed"],
        "bf16": bf16,
        "fp16": not bf16,
        "gradient_checkpointing": True,
        "report_to": report_to,
        "save_strategy": train_cfg.get("eval_strategy", "steps"),
        "save_steps": train_cfg.get("eval_steps", 500),
    } | train_cfg
    if no_eval:
        settings |= {"save_strategy": "no"}
    dpo_config = DPOConfig(output_dir=str(out_dir), **settings)

    if report_to == "wandb":
        import wandb

        wandb.init(
            project=os.environ.get("WANDB_PROJECT", "triage-chsa"),
            name=args.name,
            job_type="dpo",
            config={
                "config": config,
                "overrides": args.overrides,
                "git_commit": git_commit(),
                "limit": args.limit,
                "train_pairs": len(train_rows),
            },
        )

    trainer = NamedEvalDPOTrainer(
        model=model,
        args=dpo_config,
        train_dataset=to_dataset(train_rows),
        eval_dataset=None
        if no_eval
        else {name: to_dataset(rows) for name, rows in eval_sets.items() if rows},
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.model.print_trainable_parameters()
    template_checks = check_template(trainer, tokenizer)

    # ------------------------------------------------------------------ entraînement
    resume = get_last_checkpoint(str(out_dir)) if args.resume and out_dir.exists() else None
    if args.resume:
        print(f"Reprise : {resume or 'aucun checkpoint, départ de zéro'}")
    torch.cuda.reset_peak_memory_stats()
    result = trainer.train(resume_from_checkpoint=resume)

    best_dir = out_dir / "best"
    trainer.save_model(str(best_dir))  # meilleur checkpoint si load_best_model_at_end
    tokenizer.save_pretrained(str(best_dir))

    log = trainer.state.log_history
    run = {
        "name": args.name,
        "git_commit": git_commit(),
        "config": config,
        "overrides": args.overrides,
        "limit": args.limit,
        "resumed_from": resume,
        "sft_adapter": config["sft_adapter"],
        "merge_checks": merge_checks,
        "train_pairs": len(train_rows),
        "train_sources_before_limit": dict(train_sources),
        "train_dropped_too_long": train_dropped,
        "eval_pairs": {} if no_eval else {k: len(v) for k, v in eval_sets.items()},
        "eval_dropped_too_long": eval_dropped,
        "template_checks": template_checks,
        "training_settings": {k: v for k, v in settings.items() if k != "report_to"},
        "precision": "bf16" if bf16 else "fp16",
        "gpu": torch.cuda.get_device_name(0),
        "peak_gpu_memory_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
        "steps": trainer.state.global_step,
        "train_metrics": result.metrics,
        "train": history(log, ""),
        "eval": {name: history(log, f"eval_{name}_") for name in eval_sets},
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "minutes": round((time.time() - start) / 60, 1),
        "adapter": str(best_dir),
    }
    (out_dir / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: run[k] for k in ("steps", "minutes", "peak_gpu_memory_gib")}))


if __name__ == "__main__":
    main()
