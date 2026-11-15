"""Publie les poids finaux fusionnés (scripts/merge_final.py) dans un dépôt de modèle PRIVÉ.

Usage : uv run python scripts/publish_model.py --dir outputs/final/triage-chsa-qwen3-1.7b \
            --repo <utilisateur>/triage-chsa-qwen3-1.7b
Refuse si les contrôles de fusion ont échoué, ou si le dépôt existe déjà en public. Les poids
restent privés : ils dérivent d'un dataset privé (messages de patients réels désidentifiés, pas
anonymes : docs/RGPD.md). Le jeton est lu dans HF_TOKEN, jamais affiché.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

CARD = """---
base_model: Qwen/Qwen3-1.7B-Base
language: [fr, en]
library_name: transformers
tags: [medical, triage, lora, dpo, poc]
---

# Assistant de pré-triage CHSA (preuve de concept)

Qwen3-1.7B-Base affiné par LoRA (SFT puis DPO), adaptateurs fusionnés dans les poids. Projet de
formation : un assistant de pré-triage des urgences pour un hôpital fictif, le Centre
Hospitalier Saint-Aurélien, selon le référentiel FRENCH (SFMU).

**Ce n'est pas un dispositif médical.** L'avis est une aide à la décision : l'infirmier ou
l'infirmière d'accueil décide. Les vignettes d'entraînement sont synthétiques et non validées
cliniquement ; les scores ne garantissent rien en conditions réelles. Le modèle doit être servi
avec les garde-fous déterministes du projet (règles sur les constantes, cohérence du critère
cité). Seul, il échoue sur des cas formulés hors des gabarits d'entraînement.

Fusion : {adapters}. Contrôles : {checks}.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    merge = json.loads((args.dir / "merge.json").read_text(encoding="utf-8"))
    checks = merge["checks"]
    if checks["same_top1_tokens"] < 0.98 or not checks["tied_output_embeddings"]:
        raise SystemExit(f"Refus : contrôles de fusion en échec {checks}")
    (args.dir / "README.md").write_text(
        CARD.format(adapters=", ".join(merge["adapters"]), checks=checks), encoding="utf-8"
    )

    load_dotenv()
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(args.repo, repo_type="model", private=True, exist_ok=True)
    if not api.repo_info(args.repo, repo_type="model").private:
        raise SystemExit(f"Refus : le dépôt {args.repo} existe déjà et il est public.")
    commit = api.upload_folder(
        repo_id=args.repo,
        folder_path=args.dir,
        allow_patterns=["*.json", "*.safetensors", "*.jinja", "*.txt", "README.md"],
        commit_message=f"Poids fusionnés (commit {merge['git_commit'][:7]})",
    )
    print(f"Publié en privé : {commit.commit_url}")
    print(f"Référence : {args.repo}@{commit.oid}")


if __name__ == "__main__":
    main()
