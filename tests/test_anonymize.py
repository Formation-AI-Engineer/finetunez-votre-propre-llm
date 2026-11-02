import pytest

pytest.importorskip("presidio_analyzer")

from triage.data.anonymize import anonymize, is_eponym  # noqa: E402


def test_masks_direct_identifiers_in_french():
    text = (
        "Monsieur Jean Dupont, né le 12/03/1957, joignable au 06 12 34 56 78 ou "
        "jean.dupont@mail.fr, NIR 1 57 03 75 123 456 78."
    )
    out, findings = anonymize(text, "fr")
    for secret in ("Jean Dupont", "12/03/1957", "06 12 34 56 78", "jean.dupont@mail.fr"):
        assert secret not in out
    assert {"PERSON", "EXPLICIT_DATE", "PHONE_NUMBER", "EMAIL_ADDRESS", "FR_NIR"} <= {
        f.entity for f in findings
    }


def test_masks_names_in_english():
    out, _ = anonymize("Hi doctor, my name is John Miller, call me at (415) 555-0134.", "en")
    assert "John Miller" not in out and "555-0134" not in out


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Patient atteint de la maladie de Parkinson et d'un syndrome de Guillain-Barré.", "fr"),
        ("Antécédent de maladie de Crohn, score de Glasgow à 14.", "fr"),
        ("Wolff-Parkinson-White syndrome and Cushing disease, positive Gram stain.", "en"),
    ],
)
def test_keeps_medical_eponyms(text, lang):
    out, _ = anonymize(text, lang)
    assert out == text


def test_keeps_clinical_values_places_and_durations():
    text = "Fièvre depuis 3 jours après un séjour au Gabon. PA 130/80 mmHg, 12,5 mg, SpO2 94 %."
    out, _ = anonymize(text, "fr")
    assert out == text


def test_eponym_context_rule():
    text = "syndrome de Dubois"
    assert is_eponym(text, text.index("Dubois"), len(text))


def test_masks_signatures_at_the_end_of_a_message():
    out, _ = anonymize("My son has a fever since yesterday. Many thanks, Linda Grishman", "en")
    assert "Linda Grishman" not in out


def test_ignores_qcm_letters_and_template_words():
    text = "Bonne réponse : D\n- D. Splénomégalie\n- E. Leucopénie"
    out, _ = anonymize(text, "fr")
    assert out == text
