"""Préparation et notation des évaluations, sans GPU (la génération est dans scripts/evaluate.py).

Les mêmes fonctions servent pour le modèle de base, le SFT et le SFT + DPO : seules les réponses
changent. Définitions des métriques : docs/EVALUATION.md.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from triage.data.schema import SFTRecord
from triage.metrics import (
    ACCEPTANCE,
    Rate,
    check_acceptance,
    format_confusion,
    mcq_scores,
    parse_mcq,
    triage_scores,
)
from triage.output import parse_assessment

EVAL_TASKS = ("triage", "qcm")


@dataclass(frozen=True)
class EvalItem:
    id: str
    task: str
    source: str
    messages: list[dict]
    expected: str | tuple[str, ...]  # priorité attendue (triage) ou lettres correctes (QCM)
    style: str | None = None  # note, patient ou dialogue (vignettes)


def to_item(record: SFTRecord) -> EvalItem | None:
    """Question à évaluer, ou None si l'enregistrement n'a pas de métrique automatique."""
    meta = record.metadata
    if meta.task not in EVAL_TASKS or meta.extra.get("turn") == "question":
        return None
    if meta.task == "triage":
        expected: str | tuple[str, ...] = meta.triage.priority
    else:
        letters = parse_mcq(record.completion[0].content)
        if letters is None:
            raise ValueError(f"{record.id} : corrigé de QCM illisible")
        expected = tuple(sorted(letters))
    return EvalItem(
        id=record.id,
        task=meta.task,
        source=meta.source,
        messages=[m.model_dump() for m in record.prompt],
        expected=expected,
        style=meta.extra.get("style"),
    )


def load_items(path: Path, limit: int | None = None, seed: int = 0) -> list[EvalItem]:
    """Questions évaluables d'un fichier SFT. `limit` garde au plus n questions par tâche, tirées
    au hasard avec `seed` : utile pour un essai rapide, jamais pour un chiffre rapporté."""
    items = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            item = to_item(SFTRecord.model_validate_json(line))
            if item is not None:
                items.append(item)
    if limit is not None:
        rng = random.Random(seed)
        by_task: dict[str, list[EvalItem]] = defaultdict(list)
        for item in items:
            by_task[item.task].append(item)
        items = [
            i
            for task in EVAL_TASKS
            for i in rng.sample(by_task[task], min(limit, len(by_task[task])))
        ]
    return items


# ---------------------------------------------------------------------------- few-shot


def pick_examples(path: Path) -> dict[str, list[SFTRecord]]:
    """Exemples résolus pour le few-shot, tirés du jeu d'entraînement (jamais évalué) : une
    vignette par priorité, dans les styles note, patient et dialogue, et deux QCM (une et
    plusieurs bonnes réponses). Choix déterministe : le plus petit identifiant de chaque groupe."""
    wanted_triage = {
        ("maximale", "note"): None,
        ("moderee", "patient"): None,
        ("differee", "dialogue"): None,
    }
    wanted_qcm = {1: None, 2: None}  # nombre de bonnes réponses (2 = plusieurs)
    with path.open(encoding="utf-8") as f:
        records = sorted((SFTRecord.model_validate_json(line) for line in f), key=lambda r: r.id)
    for r in records:
        if to_item(r) is None:
            continue
        meta = r.metadata
        if meta.task == "triage":
            key = (meta.triage.priority, meta.extra.get("style"))
            if key in wanted_triage and wanted_triage[key] is None:
                wanted_triage[key] = r
        elif meta.source == "mediqal":
            key = min(len(parse_mcq(r.completion[0].content)), 2)
            if wanted_qcm[key] is None:
                wanted_qcm[key] = r
    examples = {"triage": list(wanted_triage.values()), "qcm": list(wanted_qcm.values())}
    if any(r is None for group in examples.values() for r in group):
        raise ValueError(f"exemples few-shot introuvables dans {path}")
    return examples


def with_examples(item: EvalItem, examples: list[SFTRecord]) -> EvalItem:
    """Insère les exemples comme échanges précédents, entre le message système et la question."""
    system, *question = item.messages
    shots = []
    for r in examples:
        shots += [m.model_dump() for m in r.prompt if m.role != "system"]
        shots.append(r.completion[0].model_dump())
    return replace(item, messages=[system, *shots, *question])


# ----------------------------------------------------------------------------- notation


def _rate(r: Rate) -> dict:
    low, high = r.interval
    return {"k": r.k, "n": r.n, "value": r.value, "low": low, "high": high}


def score(items: Iterable[EvalItem], answers: Mapping[str, str]) -> dict:
    """Résumé JSON des métriques. Une question sans réponse compte comme une réponse illisible."""
    items = list(items)
    summary: dict = {}

    triage = [i for i in items if i.task == "triage"]
    if triage:
        predicted = [parse_assessment(answers.get(i.id, "")) for i in triage]
        scores = triage_scores([i.expected for i in triage], predicted)
        summary["triage"] = {
            "n": len(triage),
            "accuracy": _rate(scores.accuracy),
            "under_triage_maximale": _rate(scores.under_triage_maximale),
            "under_triage": _rate(scores.under_triage),
            "over_triage": _rate(scores.over_triage),
            "format_ok": _rate(scores.format_ok),
            "confusion": scores.confusion,
            "acceptance": check_acceptance(scores),
            "accuracy_by_style": {
                style: _rate(
                    triage_scores(
                        [i.expected for i in triage if i.style == style],
                        [p for i, p in zip(triage, predicted, strict=True) if i.style == style],
                    ).accuracy
                )
                for style in sorted({i.style for i in triage if i.style})
            },
        }

    qcm = [i for i in items if i.task == "qcm"]
    if qcm:
        summary["qcm"] = {}
        for source in sorted({i.source for i in qcm}):
            group = [i for i in qcm if i.source == source]
            s = mcq_scores(
                [frozenset(i.expected) for i in group],
                [parse_mcq(answers.get(i.id, "")) for i in group],
            )
            summary["qcm"][source] = {
                "n": len(group),
                "exact_match": _rate(s.exact_match),
                "hamming": s.hamming,
                "format_ok": _rate(s.format_ok),
            }
    return summary


def _pct(r: dict) -> str:
    if not r["n"]:
        return "non mesuré (aucun cas)"
    return f"{r['value']:.1%} [{r['low']:.1%} ; {r['high']:.1%}] ({r['k']}/{r['n']})"


def to_markdown(summary: dict, title: str) -> str:
    lines = [f"# {title}", ""]
    if "triage" in summary:
        t = summary["triage"]
        lines += [
            f"## Triage ({t['n']} vignettes)",
            "",
            "| Métrique | Valeur [IC 95 %] |",
            "|---|---|",
        ]
        for key in (
            "under_triage_maximale",
            "accuracy",
            "under_triage",
            "over_triage",
            "format_ok",
        ):
            lines.append(f"| `{key}` | {_pct(t[key])} |")
        lines += ["", "Seuils d'acceptation :", ""]
        for threshold in ACCEPTANCE:
            passed = t["acceptance"][threshold.metric]
            verdict = {True: "atteint", False: "**non atteint**", None: "non mesuré"}[passed]
            sign = "≥" if threshold.higher_is_better else "≤"
            lines.append(f"- {threshold.description} {sign} {threshold.limit:.0%} : {verdict}")
        lines += ["", "Exactitude par style de vignette :", ""]
        lines += [f"- {style} : {_pct(r)}" for style, r in t["accuracy_by_style"].items()]
        lines += ["", "Matrice de confusion :", "", format_confusion(t["confusion"]), ""]
    if "qcm" in summary:
        lines += ["## QCM", "", "| Source | n | Exact match [IC 95 %] | Hamming | Format lisible |"]
        lines.append("|---|---|---|---|---|")
        for source, q in summary["qcm"].items():
            lines.append(
                f"| {source} | {q['n']} | {_pct(q['exact_match'])} | {q['hamming']:.3f} "
                f"| {q['format_ok']['value']:.1%} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_json(data: object, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
