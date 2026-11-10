#!/usr/bin/env bash
# Installe l'environnement d'entraînement sur Kaggle ou Colab, puis vérifie le GPU.
#
# Lancé par notebooks/kaggle.ipynb, une fois le dépôt cloné, depuis la racine du projet :
#   bash scripts/kaggle/setup.sh
#
# Kaggle fournit Python 3.13 et le projet exige 3.12 : uv trouve ou télécharge Python 3.12 et
# installe les versions exactes de uv.lock dans .venv. Les étapes (scripts/kaggle/<étape>.sh)
# lancent ensuite leurs scripts avec `uv run`, quel que soit le Python du noyau du notebook.
# Relancer ce script est rapide : uv n'installe que ce qui a changé dans uv.lock.
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

if ! command -v uv >/dev/null; then
    pip install --quiet uv
fi
uv --version

# --frozen : échoue plutôt que de résoudre d'autres versions que celles de uv.lock.
uv sync --frozen --extra train --no-dev
uv run --frozen --no-dev python scripts/check_gpu.py
