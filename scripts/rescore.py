"""Recalcule les métriques d'une évaluation à partir de ses réponses, sans GPU.

Usage : uv run --extra data python scripts/rescore.py outputs/eval/base/validation [...]

Sert quand la lecture des réponses ou les métriques changent : predictions.jsonl garde la réponse
brute de chaque question, inutile de la régénérer. Les questions sont relues dans
data/processed/sft/<split>.jsonl si le fichier existe (même contenu que le Hub, vérifié par son
empreinte), sinon sur le Hub. summary.json et summary.md sont réécrits ; la section « run »
d'origine est conservée.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

from triage.evaluation import dataset_file, load_items, score, to_markdown, write_json

LOCAL = Path("data/processed/sft")
BUILD_LOG = Path("data/processed/build_log.json")


def questions_file(split: str, dataset: dict) -> Path:
    local = LOCAL / f"{split}.jsonl"
    if local.exists() and BUILD_LOG.exists():
        log = json.loads(BUILD_LOG.read_text(encoding="utf-8"))
        expected = {o["file"]: o["sha256"] for o in log["outputs"]}.get(str(local))
        if expected == hashlib.sha256(local.read_bytes()).hexdigest():
            return local
    return dataset_file(dataset, split)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def rescore(run_dir: Path, dataset: dict) -> str:
    old = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    run = old["run"]
    with (run_dir / "predictions.jsonl").open(encoding="utf-8") as f:
        answers = {r["id"]: r["answer"] for r in map(json.loads, f)}
    items = [i for i in load_items(questions_file(run["split"], dataset)) if i.id in answers]
    if len(items) != len(answers):
        raise SystemExit(f"{run_dir} : {len(answers) - len(items)} réponses sans question")

    summary = score(items, answers)
    summary["run"] = run | {"rescored_at_commit": git_commit()}
    write_json(summary, run_dir / "summary.json")
    details = [run["split"]] + (["few-shot"] if run.get("few_shot") else [])
    details += ["essai limité"] if run.get("limit") else []
    markdown = to_markdown(summary, f"Évaluation `{run['name']}` ({', '.join(details)})")
    markdown += (
        f"\nRéponses coupées à la longueur maximale : {run['truncated_answers']}/{len(items)} ; "
        f"durée {run['seconds'] / 60:.1f} min, {run['tokens_per_second']} jetons/s "
        f"({run['dtype']}, {run['gpu']}). Notation recalculée sans régénérer les réponses.\n"
    )
    (run_dir / "summary.md").write_text(markdown, encoding="utf-8")
    return markdown


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dirs", nargs="+", type=Path, help="dossiers outputs/eval/<nom>/<split>"
    )
    parser.add_argument("--config", default="configs/sft.yaml")
    args = parser.parse_args()
    dataset = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["dataset"]
    for run_dir in args.run_dirs:
        print(rescore(run_dir, dataset))


if __name__ == "__main__":
    main()
