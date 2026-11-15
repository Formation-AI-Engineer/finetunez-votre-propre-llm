"""Les scripts ne sont pas importés par les autres tests (ils exigent un GPU ou le réseau) : on
vérifie au moins qu'ils compilent, pour ne pas découvrir une erreur de syntaxe sur Kaggle."""

import py_compile
from pathlib import Path

import pytest

SCRIPTS = sorted(Path(__file__).resolve().parents[1].glob("scripts/**/*.py"))


def test_scripts_are_found():
    assert any(p.name == "train_dpo.py" for p in SCRIPTS)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_script_compiles(path):
    py_compile.compile(str(path), doraise=True, cfile=None)
