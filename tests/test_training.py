import json

import pytest

from triage.training import apply_overrides, load_rows, sample_rows

CONFIG = {
    "model_id": "Qwen/Qwen3-1.7B-Base",
    "seed": 42,
    "lora": {"r": 16, "target_modules": ["q_proj"]},
    "training": {"learning_rate": 2.0e-4, "load_best_model_at_end": True},
}


def test_overrides_are_read_as_yaml_values():
    config = apply_overrides(
        CONFIG,
        [
            "training.learning_rate=1e-4",
            "training.load_best_model_at_end=false",
            "lora.r=32",
            "lora.target_modules=[q_proj, v_proj]",
            "training.max_steps=30",
            "training.eval_strategy=no",
        ],
    )
    assert config["training"]["eval_strategy"] == "no"
    assert config["training"]["learning_rate"] == pytest.approx(1e-4)
    assert config["training"]["load_best_model_at_end"] is False
    assert config["lora"] == {"r": 32, "target_modules": ["q_proj", "v_proj"]}
    assert config["training"]["max_steps"] == 30
    assert CONFIG["lora"]["r"] == 16  # la configuration d'origine n'est pas modifiée


@pytest.mark.parametrize("override", ["training.learning_rate", "=3", "optimizer.lr=1"])
def test_invalid_overrides_are_refused(override):
    with pytest.raises(ValueError):
        apply_overrides(CONFIG, [override])


def test_rows_keep_conversation_and_disable_thinking(tmp_path):
    record = {
        "prompt": [{"role": "user", "content": "Question"}],
        "completion": [{"role": "assistant", "content": "Bonne réponse : A"}],
        "metadata": {"source": "mediqal", "task": "qcm"},
    }
    path = tmp_path / "train.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    rows, sources = load_rows(path)
    assert rows == [
        {
            "prompt": record["prompt"],
            "completion": record["completion"],
            "chat_template_kwargs": {"enable_thinking": False},
        }
    ]
    assert sources == {"mediqal": 1}


def test_sample_is_reproducible_and_keeps_order():
    rows = [{"i": i} for i in range(50)]
    a = sample_rows(rows, 10, seed=1)
    assert a == sample_rows(rows, 10, seed=1)
    assert [r["i"] for r in a] == sorted(r["i"] for r in a)
    assert len(a) == 10
    assert sample_rows(rows, None, seed=1) is rows
