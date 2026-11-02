"""Publie data/processed/ sur Hugging Face, dans un dépôt de dataset PRIVÉ.

Usage : uv run --extra data python scripts/publish_dataset.py --repo <utilisateur>/triage-chsa
Le jeton est lu dans la variable HF_TOKEN (fichier .env), jamais affiché.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

PROCESSED = Path("data/processed")
CARD = Path("scripts/dataset_card.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    log = json.loads((PROCESSED / "build_log.json").read_text(encoding="utf-8"))
    if not log["anonymized"]:
        raise SystemExit("Refus : le dataset a été construit sans anonymisation.")

    load_dotenv()
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(args.repo, repo_type="dataset", private=True, exist_ok=True)
    if not api.repo_info(args.repo, repo_type="dataset").private:
        raise SystemExit(f"Refus : le dépôt {args.repo} existe déjà et il est public.")

    shutil.copy(CARD, PROCESSED / "README.md")
    commit = api.upload_folder(
        repo_id=args.repo,
        repo_type="dataset",
        folder_path=PROCESSED,
        allow_patterns=["README.md", "build_log.json", "sft/*.jsonl", "dpo/*.jsonl"],
        commit_message=f"Dataset construit depuis le commit {log['git_commit'][:7]}",
    )
    print(f"Publié en privé : {commit.commit_url}")


if __name__ == "__main__":
    main()
