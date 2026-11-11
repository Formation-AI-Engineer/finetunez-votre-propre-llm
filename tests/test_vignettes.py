import re

import pytest

pytest.importorskip("yaml")

from triage.data.french_table import load_table  # noqa: E402
from triage.data.schema import FRENCH_TO_PRIORITY  # noqa: E402
from triage.data.vignettes import generate_dpo, generate_sft, load_specs  # noqa: E402
from triage.output import parse_assessment  # noqa: E402
from triage.rules import most_severe, severity, vital_floor  # noqa: E402


@pytest.fixture(scope="module")
def sft_records():
    return generate_sft(300, "train", seed=123)


def test_table_matches_known_criteria():
    table = load_table()
    assert len(table) == 115
    dyspnea = table["Dyspnée / insuffisance respiratoire"]
    assert dyspnea.default_level == "3B"
    assert "SpO2 < 86%" in dyspnea.criteria["1"]
    assert "dyspnée à la parole" in dyspnea.criteria["2"]


def test_every_configured_level_exists_in_the_table():
    specs, _ = load_specs()  # lève une erreur si un niveau n'est pas dans le tableau
    assert len(specs) >= 50
    assert all(spec.alternatives for spec in specs)


def test_generation_is_deterministic():
    a = generate_sft(20, "train", seed=7)
    b = generate_sft(20, "train", seed=7)
    assert [r.model_dump() for r in a] == [r.model_dump() for r in b]


def test_labels_respect_vital_sign_rules(sft_records):
    for record in sft_records:
        meta = record.metadata
        clinical = meta.clinical
        alert = vital_floor(clinical.vitals, clinical.age_years)
        if alert:
            assert severity(meta.triage.french_level) <= severity(alert.level), record.id
        if meta.extra["escalation"]:
            assert alert and meta.triage.french_level == most_severe(alert.level, "5")


def test_completion_announces_the_expected_level(sft_records):
    for record in sft_records:
        if record.metadata.extra.get("turn") == "question":
            assert parse_assessment(record.completion[0].content) is None
            continue
        parsed = parse_assessment(record.completion[0].content)
        assert parsed.french_level == record.metadata.triage.french_level
        assert parsed.priority == record.metadata.triage.priority


def test_all_vignettes_are_flagged_synthetic(sft_records):
    assert all(
        r.metadata.synthetic and r.metadata.confidence == "synthetic_rules" for r in sft_records
    )


def test_priorities_are_balanced(sft_records):
    triage = [r for r in sft_records if r.metadata.extra.get("turn") != "question"]
    counts = {
        p: sum(r.metadata.triage.priority == p for r in triage) for p in FRENCH_TO_PRIORITY.values()
    }
    assert min(counts.values()) / len(triage) > 0.2


def test_dpo_rejected_is_an_under_triage():
    for record in generate_dpo(50, "train", seed=5):
        chosen = parse_assessment(record.chosen[0].content)
        rejected = parse_assessment(record.rejected[0].content)
        assert severity(rejected.french_level) > severity(chosen.french_level)
        assert rejected.priority != chosen.priority


def test_lines_said_by_a_relative_are_marked_tiers():
    # « Mon mari… », « Ma mère… » : sans le marquage, le récit ajouterait « J'ai 68 ans ».
    relative = re.compile(
        r"\b(mari|femme|épouse|conjoint|ami|amie|père|mère|fils|fille|frère|sœur|voisin|voisine)\b"
    )
    specs, _ = load_specs()
    for spec in specs:
        for line in spec.patient:
            if spec.age[0] >= 18 and relative.search(line.split(",")[0]):
                assert line in spec.proxy, line


def test_relative_gives_age_and_history_in_third_person():
    specs, _ = load_specs()
    proxy = {line for spec in specs for line in spec.proxy}
    seen = 0
    for record in generate_sft(1500, "train", seed=3):
        if record.metadata.extra.get("style") != "patient":
            continue
        text = record.prompt[-1].content
        if any(text.startswith(line.replace("{e}", "")) for line in proxy):
            seen += 1
            assert "J'ai" not in text and "Mes antécédents" not in text, text
            assert " a " in text.split("\n")[0]
    assert seen, "aucune vignette racontée par un proche dans l'échantillon"
