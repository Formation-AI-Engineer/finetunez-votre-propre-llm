import math

import pytest

from triage.metrics import (
    INVALID,
    Rate,
    check_acceptance,
    format_confusion,
    mcq_scores,
    parse_mcq,
    parse_mcq_lenient,
    triage_scores,
    wilson_interval,
)
from triage.output import Assessment


def a(priority: str) -> Assessment:
    return Assessment(priority=priority, french_level=None)


# -------------------------------------------------------------------------- intervalles


def test_wilson_interval_contains_rate_and_stays_in_bounds():
    low, high = wilson_interval(2, 67)
    assert 0 < low < 2 / 67 < high < 0.15
    assert wilson_interval(0, 50)[0] == 0.0
    assert wilson_interval(50, 50)[1] == 1.0


def test_wilson_interval_of_empty_sample_is_undefined():
    assert all(math.isnan(x) for x in wilson_interval(0, 0))
    assert math.isnan(Rate(0, 0).value)


# ------------------------------------------------------------------------------- triage


def test_perfect_triage():
    expected = ["maximale", "moderee", "differee"]
    scores = triage_scores(expected, [a(p) for p in expected])
    assert scores.accuracy.value == 1
    assert scores.under_triage_maximale.value == 0
    assert scores.under_triage.value == scores.over_triage.value == 0
    assert check_acceptance(scores) == {"under_triage_maximale": True, "accuracy": True}


def test_under_and_over_triage_are_separated():
    expected = ["maximale", "moderee", "differee", "differee"]
    predicted = [a("moderee"), a("maximale"), a("differee"), a("moderee")]
    scores = triage_scores(expected, predicted)
    assert scores.under_triage_maximale.k == 1 and scores.under_triage_maximale.n == 1
    assert scores.under_triage.k == 1  # maximale -> modérée
    assert scores.over_triage.k == 2  # modérée -> maximale, différée -> modérée
    assert scores.accuracy.k == 1


def test_unreadable_answer_counts_as_error_and_under_triage():
    expected = ["maximale", "moderee", "differee"]
    scores = triage_scores(expected, [None, None, None])
    assert scores.accuracy.k == 0
    assert scores.format_ok.k == 0
    assert scores.under_triage_maximale.k == 1
    # Une priorité différée ne peut pas être sous-triée, même sans réponse lisible.
    assert scores.under_triage.k == 2
    assert scores.over_triage.k == 0
    assert scores.confusion["maximale"][INVALID] == 1


def test_acceptance_thresholds():
    expected = ["maximale"] * 20 + ["differee"] * 4
    # 1 cas maximal manqué sur 20 = 5 % : à la limite, accepté ; exactitude 23/24.
    predicted = [a("maximale")] * 19 + [a("moderee")] + [a("differee")] * 4
    assert check_acceptance(triage_scores(expected, predicted)) == {
        "under_triage_maximale": True,
        "accuracy": True,
    }
    predicted[0] = a("moderee")  # 2/20 = 10 %
    assert not check_acceptance(triage_scores(expected, predicted))["under_triage_maximale"]


def test_lengths_must_match():
    with pytest.raises(ValueError):
        triage_scores(["maximale"], [])


def test_confusion_table_lists_every_column():
    scores = triage_scores(["moderee"], [a("moderee")])
    table = format_confusion(scores.confusion)
    assert table.splitlines()[0].count("|") == 6
    assert "| moderee | 0 | 1 | 0 | 0 |" in table


# ---------------------------------------------------------------------------------- QCM


@pytest.mark.parametrize(
    ("text", "letters"),
    [
        ("Bonne réponse : A\n- A. La diminution de l'incidence", {"A"}),
        ("Bonnes réponses : A, C, E\n- A. ...", {"A", "C", "E"}),
        ("Je pense que… Bonnes réponses : B et D", {"B", "D"}),
        ("bonne réponse: c", None),  # lettre en minuscule : format non suivi
        ("La réponse est A", None),
        ("Bonne réponse : Aucune", None),
    ],
)
def test_parse_mcq(text, letters):
    expected = frozenset(letters) if letters is not None else None
    assert parse_mcq(text) == expected


def test_mcq_scores_exact_match_and_hamming():
    expected = [frozenset("A"), frozenset("AC"), frozenset("BD")]
    predicted = [frozenset("A"), frozenset("A"), None]
    scores = mcq_scores(expected, predicted)
    assert scores.exact_match.k == 1
    assert scores.format_ok.k == 2
    # Hamming : 1 + 1/2 + 0 (réponse illisible) sur 3 questions.
    assert scores.hamming == pytest.approx(0.5)


def test_acceptance_is_undefined_without_maximale_cases():
    scores = triage_scores(["differee"], [a("differee")])
    assert check_acceptance(scores) == {"under_triage_maximale": None, "accuracy": True}


@pytest.mark.parametrize(
    ("text", "letters"),
    [
        # Réponses réelles de Qwen3-1.7B-Base (mesure de référence).
        ("La réponse correcte est : **B. Erythromycine**.", {"B"}),
        ("E. ...\n\nRéponse : A, B, C, D, E\n\nA. ...", {"A", "B", "C", "D", "E"}),
        ("Réponses : a, d", {"A", "D"}),
        ("Réponse : a et c", {"A", "C"}),
        ("Bonne réponse : C\n- C. x", {"C"}),
        ("Réponse : La réponse fausse est E. Survient 24 heures après", {"E"}),
        ("La réponse la plus urgente est **B. Recherche de BK**.", {"B"}),
        # Pas de lettre isolée : rien n'est lu plutôt que deviner.
        ("La réponse est a priori fausse.", None),
        ("La réponse est Aucune", None),
        ("Réponse : Aucune", None),
        ("Répondez en donnant la ou les bonnes propositions.", None),
    ],
)
def test_parse_mcq_lenient(text, letters):
    expected = frozenset(letters) if letters is not None else None
    assert parse_mcq_lenient(text) == expected
