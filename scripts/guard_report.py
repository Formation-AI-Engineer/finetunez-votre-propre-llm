"""Effet des garde-fous déterministes sur des prédictions déjà générées (sans GPU).

Pour chaque run de outputs/eval/<nom>/ :
- validation (ou test, avec --split test) : sous-triage des cas maximale, exactitude et
  sur-triage, pour le modèle seul, avec les règles sur les constantes (src/triage/rules.py),
  avec la cohérence du critère cité (src/triage/consistency.py), et avec les deux ;
- sécurité : réécrit safety/summary.json et summary.md avec les trois niveaux de garde-fous
  (les conditions du run d'origine sont conservées).

Usage : uv run python scripts/guard_report.py sft-r16-lr2e-4 dpo-b0.1-lr3e-5
        uv run python scripts/guard_report.py --split test <runs>   (jeu de test)
Écrit outputs/eval/guards.md (guards_test.md pour le test).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from triage import safety
from triage.consistency import consistency_floor
from triage.data.schema import FRENCH_TO_PRIORITY, Vitals
from triage.evaluation import dataset_file
from triage.metrics import triage_scores
from triage.output import Assessment, parse_assessment
from triage.rules import vital_floor

EVAL_DIR = Path("outputs/eval")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def vital_rules(clinical: dict, assessment: Assessment | None) -> Assessment | None:
    vitals = Vitals(**clinical["vitals"]) if clinical.get("vitals") else None
    floor = vital_floor(vitals, clinical.get("age_years"))
    if assessment is None or floor is None:
        return assessment
    ruled = FRENCH_TO_PRIORITY[floor.level]
    order = safety.PRIORITIES
    if order.index(ruled) < order.index(assessment.priority):
        return Assessment(priority=ruled, french_level=floor.level)
    return assessment


def triage_table(name: str, split: str, records: dict[str, dict]) -> list[str]:
    path = EVAL_DIR / name / split / "predictions.jsonl"
    if not path.exists():
        return [f"Pas de prédictions `{split}` pour `{name}`.", ""]
    preds = [p for p in read_jsonl(path) if p["task"] == "triage"]
    expected = [records[p["id"]]["metadata"]["triage"]["priority"] for p in preds]
    variants = {
        "Modèle seul": (False, False),
        "+ règles sur les constantes": (True, False),
        "+ cohérence du critère cité": (False, True),
        "+ les deux": (True, True),
    }
    lines = [
        f"### `{name}` : {split} ({len(preds)} vignettes)",
        "",
        "| Garde-fous | Maximale manqués | Exactitude | Sur-triage |",
        "|---|---|---|---|",
    ]
    for label, (rules, consistency) in variants.items():
        predicted = []
        for p in preds:
            assessment = parse_assessment(p["answer"])
            if rules:
                assessment = vital_rules(records[p["id"]]["metadata"]["clinical"], assessment)
            if consistency:
                assessment = consistency_floor(p["answer"], assessment)
            predicted.append(assessment)
        s = triage_scores(expected, predicted)
        lines.append(f"| {label} | {s.under_triage_maximale} | {s.accuracy} | {s.over_triage} |")
    return [*lines, ""]


def safety_table(name: str) -> list[str]:
    out_dir = EVAL_DIR / name / "safety"
    if not (out_dir / "predictions.jsonl").exists():
        return [f"Pas de prédictions de sécurité pour `{name}`.", ""]
    cases = safety.load_cases()
    answers = {p["id"]: p["answer"] for p in read_jsonl(out_dir / "predictions.jsonl")}
    old = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    summary = safety.summarize(cases, answers)
    summary["run"] = old.get("run", {})
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown = safety.to_markdown(summary, f"Sécurité `{name}`", cases, answers)
    (out_dir / "summary.md").write_text(markdown, encoding="utf-8")
    counts = " → ".join(f"{summary[key]['dangerous']}/{summary['n']}" for key in safety.GUARDS)
    return [
        f"Sécurité `{name}` (modèle seul → + constantes → + cohérence) : {counts} "
        "réponses dangereuses.",
        "",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="+", help="runs de outputs/eval/")
    parser.add_argument("--split", default="validation", choices=("validation", "test"))
    parser.add_argument("--config", default="configs/sft.yaml")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    records = {r["id"]: r for r in read_jsonl(dataset_file(config["dataset"], args.split))}
    lines = ["# Effet des garde-fous déterministes", ""]
    for name in args.names:
        lines += triage_table(name, args.split, records)
        if args.split == "validation":
            lines += safety_table(name)
    report = "\n".join(lines)
    suffix = "" if args.split == "validation" else f"_{args.split}"
    (EVAL_DIR / f"guards{suffix}.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
