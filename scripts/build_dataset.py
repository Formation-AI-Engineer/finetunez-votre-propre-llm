"""Construit le dataset SFT / DPO anonymisé dans data/processed/, avec son journal.

Usage : uv run --extra data python scripts/build_dataset.py [--seed 42] [--skip-anonymization]

Étapes : chargement des sources -> filtrage -> dédoublonnage -> sélection selon la composition
cible -> retrait des questions présentes dans les jeux de validation et de test -> anonymisation
-> écriture et journal (comptages, empreintes, révisions des sources).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

from triage.data import sources, vignettes
from triage.data.dedup import Record, drop_duplicates, drop_overlap, overlap, question_key
from triage.data.schema import DPORecord, SFTRecord

OUT_DIR = Path("data/processed")

# Composition cible (docs/TACHES.md, étape 1).
SFT_TARGETS = {
    "mediqal": {"train": 1800, "validation": 150, "test": 400},
    "frenchmedmcqa": {"train": 500, "validation": 50, "test": 200},
    "medquad": {"train": 1200, "validation": 100, "test": 150},
    "french_vignettes": {"train": 1500, "validation": 150, "test": 200},
}
DPO_TARGETS = {
    "ultramedical_preference": {"train": 2000, "validation": 100},  # test : les 777 officiels
    "french_vignettes": {"train": 300, "validation": 50, "test": 100},
}
VIGNETTE_SEEDS = {"train": 1, "validation": 2, "test": 3}
DPO_VIGNETTE_SEEDS = {"train": 11, "validation": 12, "test": 13}

# Longueurs maximales en caractères (environ 900 jetons ; le filtrage exact au tokenizer
# est refait à l'étape 2 avec max_length = 1024).
MAX_SFT_CHARS = 3200
MAX_DPO_CHARS = 3600


class Log:
    def __init__(self) -> None:
        self.steps: list[dict] = []

    def add(self, step: str, **counts: object) -> None:
        print(f"- {step} : {counts}")
        self.steps.append({"step": step, **counts})


def sft_length(r: SFTRecord) -> int:
    return sum(len(m.content) for m in r.prompt[1:]) + len(r.completion[0].content)


def dpo_length(r: DPORecord) -> int:
    longest = max(len(r.chosen[0].content), len(r.rejected[0].content))
    return sum(len(m.content) for m in r.prompt[1:]) + longest


def sample(records: list[Record], n: int, rng: random.Random, key: Callable | None = None):
    """Tirage sans remise, stratifié par `key` (parts égales) si fournie."""
    if n >= len(records):
        return list(records)
    if key is None:
        return rng.sample(records, n)
    groups: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        groups[key(r)].append(r)
    chosen: list[Record] = []
    remaining = n
    for i, name in enumerate(sorted(groups)):
        share = remaining // (len(groups) - i)
        picked = rng.sample(groups[name], min(share, len(groups[name])))
        chosen.extend(picked)
        remaining -= len(picked)
    return chosen


def by_split(records: list[Record]) -> dict[str, list[Record]]:
    out: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        out[r.metadata.source_split].append(r)
    return out


def split_medquad(records: list[SFTRecord], rng: random.Random) -> dict[str, list[SFTRecord]]:
    """MedQuAD n'a pas de découpage officiel : on découpe par document, pour qu'une même
    maladie ne se retrouve pas à la fois en entraînement et en test."""
    documents = sorted({r.metadata.extra["document_id"] for r in records})
    rng.shuffle(documents)
    n = len(documents)
    split_of = {d: "test" for d in documents[: n // 10]}
    split_of.update({d: "validation" for d in documents[n // 10 : n // 5]})
    out: dict[str, list[SFTRecord]] = defaultdict(list)
    for r in records:
        split = split_of.get(r.metadata.extra["document_id"], "train")
        r.metadata.source_split = split
        out[split].append(r)
    return out


def anonymize_records(records: list[Record], log: Log, name: str) -> list[Record]:
    from triage.data.anonymize import anonymize

    entities: Counter[str] = Counter()
    touched = 0
    start = time.time()
    out = []
    for record in records:
        if record.metadata.synthetic:
            out.append(record)
            continue
        lang = record.metadata.language
        record = record.model_copy(deep=True)
        changed = False
        answers = (
            [record.completion]
            if isinstance(record, SFTRecord)
            else [record.chosen, record.rejected]
        )
        for message in [m for m in record.prompt if m.role != "system"] + [a[0] for a in answers]:
            text, findings = anonymize(message.content, lang)
            if findings:
                message.content = text
                entities.update(f.entity for f in findings)
                changed = True
        record.metadata.anonymized = True
        touched += changed
        out.append(record)
    log.add(
        f"anonymisation {name}",
        records=len(records),
        records_modifies=touched,
        entites=dict(entities),
        secondes=round(time.time() - start),
    )
    return out


def write_jsonl(records: list[Record], path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(r.model_dump_json(exclude_none=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"file": str(path), "records": len(records), "sha256": digest}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "inconnu"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-anonymization", action="store_true")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    log = Log()

    # 1. Sources -------------------------------------------------------------------------
    raw: dict[str, list[Record]] = {
        "mediqal": list(sources.load_mediqal()),
        "frenchmedmcqa": list(sources.load_frenchmedmcqa()),
        "medquad": list(sources.load_medquad()),
        "ultramedical_preference": list(sources.load_ultramedical()),
    }
    for name, records in raw.items():
        log.add(f"chargement {name}", records=len(records))

    # 2. Filtrage et dédoublonnage interne -----------------------------------------------
    for name in ("mediqal", "frenchmedmcqa", "medquad"):
        before = len(raw[name])
        raw[name] = [r for r in raw[name] if sft_length(r) <= MAX_SFT_CHARS]
        raw[name], dups = drop_duplicates(raw[name])
        log.add(f"filtrage {name}", trop_longs=before - len(raw[name]) - dups, doublons=dups)
    ultra_test = [r for r in raw["ultramedical_preference"] if r.metadata.source_split == "test"]
    before = len(raw["ultramedical_preference"])
    raw["ultramedical_preference"] = [
        r for r in raw["ultramedical_preference"] if dpo_length(r) <= MAX_DPO_CHARS
    ]
    log.add(
        "filtrage ultramedical_preference",
        trop_longs=before - len(raw["ultramedical_preference"]),
    )

    # 3. Découpage : splits officiels, sauf MedQuAD (par document) -------------------------
    pools = {name: by_split(raw[name]) for name in ("mediqal", "frenchmedmcqa")}
    pools["medquad"] = split_medquad(raw["medquad"], rng)
    ultra = by_split(raw["ultramedical_preference"])

    # 4. Jeux d'évaluation d'abord, puis retrait de leurs questions des autres jeux --------
    sft: dict[str, list[SFTRecord]] = defaultdict(list)
    dpo: dict[str, list[DPORecord]] = defaultdict(list)
    subset = lambda r: r.metadata.extra.get("subset", "")  # noqa: E731
    label_type = lambda r: r.metadata.extra["label_type"]  # noqa: E731

    for split in ("test", "validation"):
        for name in ("mediqal", "frenchmedmcqa", "medquad"):
            key = subset if name == "mediqal" else None
            sft[split] += sample(pools[name][split], SFT_TARGETS[name][split], rng, key)
        # Les tours « question seule » ont des prompts peu variés : réservés à l'entraînement.
        sft[split] += vignettes.generate_sft(
            SFT_TARGETS["french_vignettes"][split], split, VIGNETTE_SEEDS[split], question_rate=0
        )
        dpo[split] += vignettes.generate_dpo(
            DPO_TARGETS["french_vignettes"][split], split, DPO_VIGNETTE_SEEDS[split]
        )
        if split == "test":
            dpo[split] += ultra_test  # jeu de test officiel complet, sans filtre de longueur
        else:
            dpo[split] += sample(
                ultra["validation"],
                DPO_TARGETS["ultramedical_preference"]["validation"],
                rng,
                label_type,
            )
            test_keys = {question_key(r) for r in sft["test"] + dpo["test"]}
            sft[split], removed_sft = drop_overlap(sft[split], test_keys)
            dpo[split], removed_dpo = drop_overlap(dpo[split], test_keys)
            log.add("fuite retirée validation", sft=removed_sft, dpo=removed_dpo)

    held_out = {
        question_key(r) for split in ("validation", "test") for r in sft[split] + dpo[split]
    }

    train_sft_pool: list[SFTRecord] = []
    for name in ("mediqal", "frenchmedmcqa", "medquad"):
        pool, removed = drop_overlap(pools[name]["train"], held_out)
        log.add(f"fuite retirée {name} train", retires=removed)
        key = subset if name == "mediqal" else None
        train_sft_pool += sample(pool, SFT_TARGETS[name]["train"], rng, key)
    vignettes_train = vignettes.generate_sft(
        SFT_TARGETS["french_vignettes"]["train"], "train", VIGNETTE_SEEDS["train"]
    )
    vignettes_train, duplicates = drop_duplicates(vignettes_train)
    vignettes_train, removed = drop_overlap(vignettes_train, held_out)
    log.add("vignettes train", doublons=duplicates, fuite_retiree=removed)
    sft["train"] = train_sft_pool + vignettes_train

    ultra_train, removed = drop_overlap(ultra["train"], held_out)
    log.add("fuite retirée ultramedical train", retires=removed)
    dpo_vignettes, removed = drop_overlap(
        vignettes.generate_dpo(
            DPO_TARGETS["french_vignettes"]["train"], "train", DPO_VIGNETTE_SEEDS["train"]
        ),
        held_out,
    )
    log.add("fuite retirée vignettes DPO train", retires=removed)
    dpo["train"] = (
        sample(ultra_train, DPO_TARGETS["ultramedical_preference"]["train"], rng, label_type)
        + dpo_vignettes
    )

    # 5. Contrôle : aucune question partagée entre jeux ------------------------------------
    for kind, sets in (("sft", sft), ("dpo", dpo)):
        for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
            n = overlap(sets[a], sets[b])
            if n:
                raise RuntimeError(f"{kind} : {n} questions communes entre {a} et {b}")
    ids = Counter(r.id for sets in (sft, dpo) for records in sets.values() for r in records)
    duplicated = [i for i, n in ids.items() if n > 1]
    if duplicated:
        raise RuntimeError(f"{len(duplicated)} identifiants en double, par exemple {duplicated[0]}")
    log.add(
        "contrôle de fuite",
        sft_train_vs_eval=overlap(sft["train"], sft["validation"] + sft["test"]),
        dpo_train_vs_eval=overlap(dpo["train"], dpo["validation"] + dpo["test"]),
        sft_train_vs_dpo_eval=overlap(sft["train"], dpo["validation"] + dpo["test"]),
    )

    # 6. Anonymisation -------------------------------------------------------------------
    if not args.skip_anonymization:
        for split in ("train", "validation", "test"):
            sft[split] = anonymize_records(sft[split], log, f"sft {split}")
            dpo[split] = anonymize_records(dpo[split], log, f"dpo {split}")

    # 7. Écriture ------------------------------------------------------------------------
    outputs = []
    for kind, sets in (("sft", sft), ("dpo", dpo)):
        for split in ("train", "validation", "test"):
            records = sorted(sets[split], key=lambda r: r.id)
            random.Random(args.seed).shuffle(records)
            outputs.append(write_jsonl(records, OUT_DIR / kind / f"{split}.jsonl"))
            composition = Counter(r.metadata.source for r in records)
            log.add(f"écriture {kind} {split}", records=len(records), sources=dict(composition))

    manifest = json.loads(Path("data/raw/MANIFEST.json").read_text(encoding="utf-8"))
    report = {
        "seed": args.seed,
        "git_commit": git_commit(),
        "anonymized": not args.skip_anonymization,
        "sources": {
            k: {"revision": v["revision"], "license": v["license"]} for k, v in manifest.items()
        },
        "steps": log.steps,
        "outputs": outputs,
    }
    (OUT_DIR / "build_log.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Journal : {OUT_DIR / 'build_log.json'}")


if __name__ == "__main__":
    main()
