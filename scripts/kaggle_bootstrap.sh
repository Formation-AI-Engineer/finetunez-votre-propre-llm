#!/usr/bin/env bash
# Installe l'environnement d'entraînement sur Kaggle ou Colab, puis vérifie le GPU.
#
# Lancé par notebooks/kaggle_setup.ipynb, une fois le dépôt cloné, depuis la racine du projet :
#   bash scripts/kaggle_bootstrap.sh
#
# Kaggle fournit Python 3.13 et le projet exige 3.12 : uv télécharge lui-même Python 3.12 et
# installe les versions exactes de uv.lock dans .venv. Le notebook lance ensuite les scripts avec
# `uv run`, quel que soit le Python de son propre noyau.
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

if ! command -v uv >/dev/null; then
    pip install --quiet uv
fi
uv --version

# --frozen : échoue plutôt que de résoudre d'autres versions que celles de uv.lock.
uv sync --frozen --extra train --no-dev
uv run --frozen --no-dev python scripts/check_gpu.py
