import pytest

from triage.data.schema import FRENCH_TO_PRIORITY, TriageLabel, Vitals
from triage.output import parse_assessment
from triage.rules import most_severe, vital_floor


def adult(**values) -> Vitals:
    base = dict(
        heart_rate=80,
        systolic_bp=125,
        diastolic_bp=75,
        respiratory_rate=16,
        spo2=97,
        temperature=37.0,
    )
    return Vitals(**{**base, **values})


def test_normal_adult_vitals_raise_no_alert():
    assert vital_floor(adult(), 40) is None


@pytest.mark.parametrize(
    ("values", "level"),
    [
        ({"spo2": 84}, "1"),
        ({"spo2": 88}, "2"),
        ({"respiratory_rate": 42}, "1"),
        ({"respiratory_rate": 32}, "2"),
        ({"systolic_bp": 68, "diastolic_bp": 40}, "1"),
        ({"systolic_bp": 95, "diastolic_bp": 60, "heart_rate": 110}, "2"),
        ({"heart_rate": 185}, "1"),
        ({"heart_rate": 38}, "1"),
        ({"temperature": 31.5}, "1"),
        ({"temperature": 40.2}, "2"),
        ({"gcs": 7}, "1"),
        ({"gcs": 12}, "2"),
        ({"systolic_bp": 225, "diastolic_bp": 120}, "2"),
    ],
)
def test_critical_vitals_set_a_floor(values, level):
    assert vital_floor(adult(**values), 50).level == level


def test_adult_thresholds_do_not_apply_to_infants():
    infant = Vitals(heart_rate=140, systolic_bp=85, respiratory_rate=36, spo2=98, temperature=37.0)
    assert vital_floor(infant, 0.5) is None
    assert vital_floor(infant.model_copy(update={"spo2": 84}), 0.5).level == "1"


def test_most_severe_and_priority_mapping():
    assert most_severe("4", "2", "3B") == "2"
    assert [FRENCH_TO_PRIORITY[lv] for lv in ("1", "3A", "5")] == [
        "maximale",
        "moderee",
        "differee",
    ]


def test_triage_label_rejects_inconsistent_priority():
    with pytest.raises(ValueError):
        TriageLabel(
            french_level="2", priority="differee", motif="x", category="y", deciding_criterion="z"
        )


def test_parse_assessment():
    parsed = parse_assessment("Niveau de priorité : MODÉRÉE (tri FRENCH 3B)\nMotif : ...")
    assert parsed.priority == "moderee" and parsed.french_level == "3B"
    assert parse_assessment("Niveau de priorité : différée").priority == "differee"
    assert parse_assessment("Je ne sais pas.") is None
    # Contradiction : on retient le plus grave.
    assert parse_assessment("Niveau de priorité : DIFFÉRÉE (tri FRENCH 2)").priority == "maximale"
