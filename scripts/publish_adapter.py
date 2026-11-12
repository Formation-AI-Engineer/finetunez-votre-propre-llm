"""Publie un adaptateur entraîné dans un dépôt de modèle PRIVÉ du Hub, un dossier par run.

Usage : uv run --extra data python scripts/publish_adapter.py --run outputs/sft/sft-r16-lr2e-4 \
            --repo <utilisateur>/triage-chsa-adapters
Publie <run>/best/ (adaptateur, tokenizer) et <run>/run.json dans le dossier <nom du run>/, puis
affiche la référence à reporter dans la configuration : hf://<dépôt>/<nom>@<révision>.
Le jeton est lu dans la variable HF_TOKEN (fichier .env), jamais affiché.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, help="dossier outputs/<étape>/<nom>")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    best, run_file = args.run / "best", args.run / "run.json"
    for path in (best / "adapter_config.json", best / "adapter_model.safetensors", run_file):
        if not path.exists():
            raise SystemExit(f"Fichier manquant : {path}")
    run = json.loads(run_file.read_text(encoding="utf-8"))
    name = run["name"]

    load_dotenv()
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(args.repo, repo_type="model", private=True, exist_ok=True)
    if not api.repo_info(args.repo, repo_type="model").private:
        raise SystemExit(f"Refus : le dépôt {args.repo} existe déjà et il est public.")

    message = f"{name} (commit {run['git_commit'][:7]})"
    api.upload_folder(
        repo_id=args.repo,
        folder_path=best,
        path_in_repo=name,
        # Pas training_args.bin : un pickle, inutile pour charger l'adaptateur.
        allow_patterns=["*.json", "*.safetensors", "*.jinja", "README.md"],
        commit_message=message,
    )
    commit = api.upload_file(
        repo_id=args.repo,
        path_or_fileobj=run_file,
        path_in_repo=f"{name}/run.json",
        commit_message=f"{message} : journal du run",
    )
    print(f"Publié en privé : {commit.commit_url}")
    print(f"Référence : hf://{args.repo}/{name}@{commit.oid}")


if __name__ == "__main__":
    main()
