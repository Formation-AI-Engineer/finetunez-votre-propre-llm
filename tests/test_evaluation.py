import pytest

from triage.data import vignettes
from triage.data.sources import _mcq_record
from triage.evaluation import load_items, pick_examples, score, to_markdown, with_examples


@pytest.fixture
def eval_file(tmp_path):
    records = vignettes.generate_sft(12, "validation", 2, question_rate=0)
    records.append(
        _mcq_record(
            source="mediqal",
            source_id="q1",
            split="validation",
            license="CC-BY-4.0",
            context=None,
            question="Quels signes évoquent une méningite ?",
            options={"a": "Raideur de nuque", "b": "Prurit", "c": "Fièvre"},
            correct=["a", "c"],
            subject=None,
            extra={},
        )
    )
    path = tmp_path / "validation.jsonl"
    path.write_text("".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8")
    return path, records


def test_load_items_reads_expected_answers(eval_file):
    path, records = eval_file
    items = load_items(path)
    assert len(items) == len(records)
    qcm = [i for i in items if i.task == "qcm"]
    assert qcm[0].expected == ("A", "C")
    triage = [i for i in items if i.task == "triage"]
    assert {i.expected for i in triage} <= {"maximale", "moderee", "differee"}
    # Le prompt s'arrête avant la réponse attendue.
    assert all(i.messages[-1]["role"] == "user" for i in items)


def test_reference_answers_score_perfectly(eval_file):
    path, records = eval_file
    items = load_items(path)
    answers = {r.id: r.completion[0].content for r in records}
    summary = score(items, answers)
    assert summary["triage"]["accuracy"]["value"] == 1
    assert summary["triage"]["format_ok"]["value"] == 1
    assert summary["qcm"]["mediqal"]["exact_match"]["value"] == 1
    assert "Triage (12 vignettes)" in to_markdown(summary, "test")


def test_missing_or_unreadable_answers_count_as_errors(eval_file):
    path, _ = eval_file
    items = load_items(path)
    summary = score(items, {i.id: "Je ne sais pas." for i in items[:3]})
    assert summary["triage"]["format_ok"]["k"] == 0
    assert summary["triage"]["accuracy"]["k"] == 0
    assert summary["qcm"]["mediqal"]["format_ok"]["k"] == 0
    assert summary["unreadable_examples"]["qcm"][0]["answer"] in ("", "Je ne sais pas.")
    assert "Exemples de réponses illisibles (triage)" in to_markdown(summary, "test")


def test_limit_keeps_at_most_n_per_task(eval_file):
    path, _ = eval_file
    items = load_items(path, limit=5, seed=1)
    assert sum(i.task == "triage" for i in items) == 5
    assert sum(i.task == "qcm" for i in items) == 1
    assert [i.id for i in items] == [i.id for i in load_items(path, limit=5, seed=1)]


def test_few_shot_examples_come_before_the_question(tmp_path, eval_file):
    eval_path, _ = eval_file
    train = vignettes.generate_sft(90, "train", 1, question_rate=0)
    for i, correct in enumerate((["b"], ["a", "c"])):
        train.append(
            _mcq_record(
                source="mediqal",
                source_id=f"t{i}",
                split="train",
                license="CC-BY-4.0",
                context=None,
                question=f"Question {i}",
                options={"a": "x", "b": "y", "c": "z"},
                correct=correct,
                subject=None,
                extra={},
            )
        )
    path = tmp_path / "train.jsonl"
    path.write_text("".join(r.model_dump_json() + "\n" for r in train), encoding="utf-8")

    examples = pick_examples(path)
    priorities = [r.metadata.triage.priority for r in examples["triage"]]
    assert priorities == ["maximale", "moderee", "differee"]
    assert len(examples["qcm"]) == 2

    item = load_items(eval_path)[0]
    shot = with_examples(item, examples[item.task])
    assert shot.messages[0]["role"] == "system"
    assert shot.messages[-1] == item.messages[-1]  # la question évaluée reste en dernier
    assert sum(m["role"] == "system" for m in shot.messages) == 1
    assert shot.expected == item.expected
