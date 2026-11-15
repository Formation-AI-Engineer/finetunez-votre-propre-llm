"""Contrôle qualité de l'anonymisation.

1. Liste les entités masquées dans un échantillon des sources brutes, pour relecture manuelle
   (faux positifs : termes médicaux masqués à tort).
2. Mesure le rappel et la précision sur un corpus de phrases annotées à la main
   (tests/fixtures/anonymization_gold.jsonl), qui mêle identifiants et pièges médicaux.

Usage : uv run --extra data python scripts/audit_anonymization.py [--sample 300]
Sortie : outputs/audit/anonymization_review.md
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from triage.data import sources
from triage.data.anonymize import analyze

GOLD = Path("tests/fixtures/anonymization_gold.jsonl")
OUT = Path("outputs/audit/anonymization_review.md")


def evaluate_gold() -> tuple[dict, list[str]]:
    """Rappel et précision au niveau des entités attendues (correspondance par recouvrement)."""
    tp = fp = fn = 0
    errors = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        text, lang, expected = item["text"], item["lang"], item["pii"]
        found = [text[r.start : r.end] for r in analyze(text, lang)]
        for value in expected:
            if any(value in f or f in value for f in found):
                tp += 1
            else:
                fn += 1
                errors.append(f"- Faux négatif ({lang}) : « {value} » dans « {text} »")
        for value in found:
            if not any(value in e or e in value for e in expected):
                fp += 1
                errors.append(f"- Faux positif ({lang}) : « {value} » dans « {text} »")
    metrics = {
        "entites_attendues": tp + fn,
        "rappel": round(tp / (tp + fn), 3) if tp + fn else None,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "faux_negatifs": fn,
        "faux_positifs": fp,
    }
    return metrics, errors


def review_sources(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    lines = []
    loaders = {
        "ultramedical (ChatDoctor)": lambda: (
            r
            for r in sources.load_ultramedical()
            if r.metadata.extra["prompt_source"] == "ChatDoctor"
        ),
        "mediqal": sources.load_mediqal,
        "medquad": sources.load_medquad,
    }
    for name, loader in loaders.items():
        records = list(loader())
        picked = rng.sample(records, min(n, len(records)))
        counts: Counter[str] = Counter()
        lines.append(f"\n## {name} : {len(picked)} prompts tirés au hasard\n")
        for record in picked:
            text = record.prompt[-1].content
            for r in analyze(text, record.metadata.language):
                counts[r.entity_type] += 1
                context = text[max(0, r.start - 40) : r.end + 40].replace("\n", " ")
                lines.append(f"- `{r.entity_type}` « {text[r.start : r.end]} » : …{context}…")
        lines.insert(len(lines) - sum(counts.values()), f"Entités : {dict(counts)}\n")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    metrics, errors = evaluate_gold()
    print("Corpus annoté :", metrics)
    report = ["# Revue de l'anonymisation", "", "## Corpus annoté", "", f"`{metrics}`", ""]
    report += errors or ["Aucune erreur."]
    report += review_sources(args.sample, args.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Revue à relire : {OUT}")


if __name__ == "__main__":
    main()
