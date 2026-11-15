"""Surveillance après déploiement : indicateurs calculés sur le journal d'audit.

Chaque indicateur a un seuil d'alerte (point de départ, à revoir avec les premières semaines
d'usage réel, docs/GO_NO_GO.md). Le script lit le journal par l'API (clé d'audit lue dans
l'environnement, jamais en argument) ou un fichier local.

Usage :
  set -a; . ~/.config/triage-chsa/api.env; set +a
  uv run python scripts/monitor_audit.py --api https://…-api.us-east.modal.run [--since 2026-11-15]
  uv run python scripts/monitor_audit.py --file outputs/audit/interactions.jsonl
Code de sortie 1 si un seuil est franchi (utilisable dans une tâche planifiée).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx

UNAVAILABLE = "modèle indisponible"
ENGLISH = "triage nurse will assess you"
NON_STANDARD = "format non standard"

# (indicateur, seuil, sens) : alerte si la valeur dépasse le seuil.
THRESHOLDS = {
    "relais_modele_indisponible_pct": 2.0,  # disponibilité : démarrages à froid, pannes
    "latence_p95_ms": 3000,  # seuil d'acceptation
    "evaluations_hors_format_pct": 10.0,  # 21/211 vus le 15/11 avant correction
    "niveau_releve_par_garde_fou_pct": 15.0,  # dérive du modèle ou de la population
    "maximale_pct": 40.0,  # sur-triage massif
    "messages_en_anglais_pct": 5.0,  # public non francophone à prendre en charge autrement
}


def load(args: argparse.Namespace) -> list[dict]:
    if args.file:
        return [json.loads(line) for line in Path(args.file).open(encoding="utf-8") if line.strip()]
    response = httpx.get(
        args.api.rstrip("/") + "/api/v1/audit",
        params={"limit": 1000},
        headers={"X-Audit-Key": os.environ["AUDIT_API_KEY"]},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def pct(part: int, total: int) -> float:
    return round(100 * part / total, 1) if total else 0.0


def p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, round(0.95 * (len(ordered) - 1)))] if ordered else 0


def indicators(rows: list[dict]) -> dict:
    answers = [r.get("answer") or "" for r in rows]
    evaluations = [r for r in rows if r["status"] == "evaluation"]
    raised = [r for r in evaluations if r.get("guards")]
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    guards = Counter(g["name"] for r in rows for g in r.get("guards") or [])
    return {
        "entrees": len(rows),
        "sessions": len({r["session_id"] for r in rows}),
        "statuts": dict(Counter(r["status"] for r in rows)),
        "niveaux_finaux": dict(Counter(r["priority"] for r in evaluations)),
        "garde_fous": dict(guards),
        "relais_modele_indisponible_pct": pct(sum(UNAVAILABLE in a for a in answers), len(rows)),
        "messages_en_anglais_pct": pct(sum(ENGLISH in a for a in answers), len(rows)),
        "latence_p95_ms": p95(latencies),
        "evaluations_hors_format_pct": pct(
            sum(any(NON_STANDARD in x for x in r.get("alerts") or []) for r in evaluations),
            len(evaluations),
        ),
        "niveau_releve_par_garde_fou_pct": pct(len(raised), len(evaluations)),
        "maximale_pct": pct(
            sum(r["priority"] == "maximale" for r in evaluations), len(evaluations)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--api")
    source.add_argument("--file")
    parser.add_argument("--since", help="date ISO : seulement les entrées à partir de cette date")
    args = parser.parse_args()

    rows = load(args)
    if args.since:
        rows = [r for r in rows if r["timestamp"] >= args.since]
    found = indicators(rows)
    print(json.dumps({k: v for k, v in found.items() if k not in THRESHOLDS}, ensure_ascii=False))
    breaches = 0
    for name, limit in THRESHOLDS.items():
        value = found[name]
        alert = value > limit
        breaches += alert
        print(f"{'ALERTE' if alert else 'ok    '} {name} = {value} (seuil {limit})")
    sys.exit(1 if breaches else 0)


if __name__ == "__main__":
    main()
