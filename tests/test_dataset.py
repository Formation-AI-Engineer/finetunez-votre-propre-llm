"""Contrôles du dataset construit (ignorés si data/processed/ n'a pas été généré)."""

import json
from pathlib import Path

import pytest

from triage.data.dedup import drop_overlap, normalize, question_key
from triage.data.schema import DPORecord, SFTRecord

PROCESSED = Path("data/processed")
SPLITS = ("train", "validation", "test")


def test_normalize_ignores_case_accents_and_punctuation():
    assert normalize("Quelle  est la DOSE ? Été") == normalize("quelle est la dose ete")


def load(kind: str, split: str):
    path = PROCESSED / kind / f"{split}.jsonl"
    model = SFTRecord if kind == "sft" else DPORecord
    with path.open(encoding="utf-8") as f:
        return [model.model_validate(json.loads(line)) for line in f]


@pytest.fixture(scope="module")
def dataset():
    if not (PROCESSED / "build_log.json").exists():
        pytest.skip("dataset non construit (scripts/build_dataset.py)")
    return {(k, s): load(k, s) for k in ("sft", "dpo") for s in SPLITS}


def test_drop_overlap(dataset):
    records = dataset[("sft", "validation")]
    kept, removed = drop_overlap(records, {question_key(records[0])})
    assert removed >= 1 and records[0] not in kept


def test_ids_are_unique(dataset):
    ids = [r.id for records in dataset.values() for r in records]
    assert len(ids) == len(set(ids))


def test_no_question_shared_between_training_and_evaluation(dataset):
    train = {question_key(r) for k in ("sft", "dpo") for r in dataset[(k, "train")]}
    for kind in ("sft", "dpo"):
        for split in ("validation", "test"):
            assert not train & {question_key(r) for r in dataset[(kind, split)]}
    validation = {question_key(r) for k in ("sft", "dpo") for r in dataset[(k, "validation")]}
    test = {question_key(r) for k in ("sft", "dpo") for r in dataset[(k, "test")]}
    assert not validation & test


def test_every_record_is_anonymized_or_synthetic(dataset):
    log = json.loads((PROCESSED / "build_log.json").read_text(encoding="utf-8"))
    if not log["anonymized"]:
        pytest.skip("dataset construit sans anonymisation")
    for records in dataset.values():
        assert all(r.metadata.anonymized for r in records)


def test_composition_matches_targets(dataset):
    train = dataset[("sft", "train")]
    assert 4500 <= len(train) <= 5500
    sources = {r.metadata.source for r in train}
    assert sources == {"mediqal", "frenchmedmcqa", "medquad", "french_vignettes"}
    assert len(dataset[("dpo", "test")]) >= 777
