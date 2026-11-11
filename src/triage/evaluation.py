"""Préparation et notation des évaluations, sans GPU (la génération est dans scripts/evaluate.py).

Les mêmes fonctions servent pour le modèle de base, le SFT et le SFT + DPO : seules les réponses
changent. Définitions des métriques : docs/EVALUATION.md.
"""

from __future__ import annotations

import json
import random
import re
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
    parse_mcq_lenient,
    triage_scores,
)
from triage.output import parse_assessment

EVAL_TASKS = ("triage", "qcm")
UNREADABLE_SHOWN = 3  # réponses illisibles recopiées dans le résumé, par tâche
UNREADABLE_CHARS = 500


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


def dataset_file(dataset: dict, split: str) -> Path:
    """Fichier SFT du dataset privé, à la révision fixée dans configs/sft.yaml (jeton HF_TOKEN)."""
    import os

    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            dataset["repo_id"],
            f"sft/{split}.jsonl",
            repo_type="dataset",
            revision=dataset["revision"],
            token=os.environ.get("HF_TOKEN"),
        )
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


def _normalize_line(line: str) -> str:
    return re.sub(r"[\W_]+", " ", line).strip().lower()


_OPTION_LINE = re.compile(r"\s*[A-E][.)]\s")


def strip_echo(answer: str, item: EvalItem) -> str:
    """Retire de la réponse les lignes de l'énoncé recopiées de la question, que le modèle de base
    répète souvent avant de répondre : « (cochez la réponse fausse) … : » serait sinon lu comme
    l'annonce de la réponse. Comparaison sans casse ni ponctuation. Les propositions (« A. … »)
    restent : « La réponse correcte est :\n\n**D. …** » cite la proposition telle quelle, et sans
    l'énoncé une proposition recopiée n'est précédée d'aucun « réponse … : »."""
    question = {
        _normalize_line(line)
        for m in item.messages
        if m["role"] == "user"
        for line in m["content"].splitlines()
        if not _OPTION_LINE.match(line)
    }
    question.discard("")
    kept = [line for line in answer.splitlines() if _normalize_line(line) not in question]
    return "\n".join(kept)


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
            expected = [frozenset(i.expected) for i in group]
            strict = mcq_scores(expected, [parse_mcq(answers.get(i.id, "")) for i in group])
            lenient = mcq_scores(
                expected,
                [parse_mcq_lenient(strip_echo(answers.get(i.id, ""), i)) for i in group],
            )
            summary["qcm"][source] = {
                "n": len(group),
                "exact_match": _rate(strict.exact_match),
                "hamming": strict.hamming,
                "format_ok": _rate(strict.format_ok),
                # Lecture tolérante : connaissances, même sans le format appris.
                "exact_match_lenient": _rate(lenient.exact_match),
                "hamming_lenient": lenient.hamming,
                "readable_lenient": _rate(lenient.format_ok),
            }

    # Quelques réponses illisibles par tâche (même en lecture tolérante pour les QCM), pour voir
    # tout de suite ce que le modèle écrit.
    readers = {
        "triage": lambda i: parse_assessment(answers.get(i.id, "")),
        "qcm": lambda i: parse_mcq_lenient(strip_echo(answers.get(i.id, ""), i)),
    }
    summary["unreadable_examples"] = {
        task: [
            {"id": i.id, "answer": answers.get(i.id, "")[:UNREADABLE_CHARS]}
            for i in items
            if i.task == task and readers[task](i) is None
        ][:UNREADABLE_SHOWN]
        for task in EVAL_TASKS
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
        lines += [
            "## QCM",
            "",
            "Lecture stricte (format « Bonne réponse : X » appris) :",
            "",
            "| Source | n | Exact match [IC 95 %] | Hamming | Format lisible |",
            "|---|---|---|---|---|",
        ]
        for source, q in summary["qcm"].items():
            lines.append(
                f"| {source} | {q['n']} | {_pct(q['exact_match'])} | {q['hamming']:.3f} "
                f"| {q['format_ok']['value']:.1%} |"
            )
        lines += [
            "",
            "Lecture tolérante (« Réponse : c », « La réponse correcte est : B… ») :",
            "",
            "| Source | n | Exact match [IC 95 %] | Hamming | Lisible |",
            "|---|---|---|---|---|",
        ]
        for source, q in summary["qcm"].items():
            lines.append(
                f"| {source} | {q['n']} | {_pct(q['exact_match_lenient'])} "
                f"| {q['hamming_lenient']:.3f} | {q['readable_lenient']['value']:.1%} |"
            )
        lines.append("")
    for task, examples in summary.get("unreadable_examples", {}).items():
        if examples:
            lines += [f"## Exemples de réponses illisibles ({task})", ""]
            for example in examples:
                lines += [f"`{example['id']}` :", "", "```text", example["answer"], "```", ""]
    return "\n".join(lines)


def write_json(data: object, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
