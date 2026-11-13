import pytest

from triage.red_flags import FLAGS, red_flag_floor, red_flags
from triage.safety import CASES_FILES, load_cases, render


@pytest.mark.parametrize(
    "text,name",
    [
        ("J'ai une douleur qui serre la poitrine avec des sueurs.", "douleur thoracique typique"),
        ("Ma bouche est de travers et je trouve plus mes mots.", "déficit neurologique brutal"),
        ("J'ai envie d'en finir.", "idées suicidaires"),
        ("Mal de tête d'un coup, le pire de ma vie.", "céphalée brutale"),
        ("Les contractions sont toutes les 2 minutes.", "accouchement imminent"),
        ("Ses lèvres gonflent et il a du mal à respirer.", "risque d'obstruction allergique"),
    ],
)
def test_flags_fire_on_lay_wording(text, name):
    assert name in [h.name for h in red_flags(text)]


@pytest.mark.parametrize(
    "text",
    [
        "Anxiété modérée, sans idée suicidaire.",
        "Règles plus abondantes, pas de grossesse possible, un peu de douleur.",
        "Saignement abondant, arrêté à l'arrivée.",
        "J'ai la main gauche engourdie et du mal à parler depuis trois jours.",
        "J'ai mal à la gorge depuis hier.",
        "Je viens pour une entorse de la cheville.",
    ],
)
def test_negations_and_lesser_criteria_do_not_fire(text):
    assert red_flags(text) == []


def test_infant_fever_needs_the_age():
    assert red_flag_floor("Il a de la fièvre.", 0.1).level == "2"
    assert red_flag_floor("Il a de la fièvre.", 2) is None


def test_flags_point_to_french_lines_of_level_1_or_2():
    assert all(f.level in ("1", "2") and f.motif for f in FLAGS)


def test_false_friends_of_the_second_set_are_not_flagged():
    for case in load_cases(CASES_FILES["safety_v2"]):
        if case.category == "faux_ami":
            text = " ".join(m["content"] for m in render(case) if m["role"] == "user")
            assert red_flags(text, case.age) == [], case.id
