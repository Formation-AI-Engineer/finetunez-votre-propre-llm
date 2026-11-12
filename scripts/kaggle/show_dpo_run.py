"""Résumé d'un run DPO (outputs/dpo/<nom>/run.json), affiché à la fin des étapes Kaggle."""

import json
import sys
from pathlib import Path


def ends(values: list[float]) -> str:
    return f"{values[0]:.3f} -> {values[-1]:.3f}" if values else "-"


for path in sys.argv[1:]:
    run_file = Path(path)
    if not run_file.exists():
        print(f"{run_file} absent : le run n'est pas allé au bout.")
        continue
    r = json.loads(run_file.read_text(encoding="utf-8"))
    print(
        f"---- {r['name']} : {r['steps']} pas en {r['minutes']} min, "
        f"{r['peak_gpu_memory_gib']} Gio, repris de {r['resumed_from']}"
    )
    print(f"fusion SFT : {r['merge_checks']}")
    print(f"{r['train_pairs']} paires ({r['train_dropped_too_long']} trop longues retirées)")
    train = r["train"]
    for key in ("loss", "rewards/accuracies", "rewards/margins", "logps/chosen", "logps/rejected"):
        print(f"  entraînement {key:20} {ends(train.get(key, []))}")
    for name, series in r["eval"].items():
        values = {k: [round(x, 3) for x in v] for k, v in series.items()}
        print(f"  validation {name} ({r['eval_pairs'].get(name)} paires) : {values}")
