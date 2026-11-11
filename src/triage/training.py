"""Préparation de l'entraînement, sans dépendance GPU (testée en local).

- surcharges de configuration en ligne de commande : `--set training.learning_rate=1e-4` ;
- lignes d'entraînement au format conversationnel « prompt / completion » de TRL ;
- sous-échantillon reproductible pour les petits runs.
"""

from __future__ import annotations

import contextlib
import copy
import json
import random
from collections import Counter
from pathlib import Path

import yaml

# Sections de configs/sft.yaml qu'une surcharge peut modifier.
SECTIONS = ("model_id", "seed", "dataset", "lora", "training")


def apply_overrides(config: dict, overrides: list[str]) -> dict:
    """Copie de `config` où chaque `chemin.de.cle=valeur` remplace la valeur (lue en YAML :
    `1e-4` reste un nombre, `false` un booléen, `[q_proj, v_proj]` une liste)."""
    config = copy.deepcopy(config)
    for override in overrides:
        path, sep, raw = override.partition("=")
        if not sep or not path:
            raise ValueError(f"surcharge invalide, attendu cle=valeur : {override!r}")
        keys = path.split(".")
        if keys[0] not in SECTIONS:
            raise ValueError(f"section inconnue {keys[0]!r} (attendu : {', '.join(SECTIONS)})")
        node = config
        for key in keys[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                raise ValueError(f"{path} : {key!r} n'est pas une section")
        # YAML 1.1 lit « no » comme False : `eval_strategy=no` doit rester le texte « no ».
        value = raw if raw.lower() in {"yes", "no", "on", "off"} else yaml.safe_load(raw)
        # « 1e-4 » est lu comme une chaîne en YAML 1.1 : on le convertit en nombre.
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                value = float(value)
        node[keys[-1]] = value
    return config


def load_rows(path: Path) -> tuple[list[dict], Counter]:
    """Lignes « prompt / completion » de sft/<split>.jsonl, et leur nombre par source.

    Le mode sans raisonnement de Qwen3 (`enable_thinking=False`) passe par la colonne
    `chat_template_kwargs`, que TRL transmet au chat template pour chaque exemple : le prompt se
    termine alors par un bloc `<think></think>` vide, comme à l'évaluation. Les métadonnées ne
    sont pas gardées : seul le texte sert à l'entraînement.
    """
    rows, sources = [], Counter()
    with path.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            rows.append(
                {
                    "prompt": record["prompt"],
                    "completion": record["completion"],
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            )
            sources[record["metadata"]["source"]] += 1
    return rows, sources


def sample_rows(rows: list[dict], n: int | None, seed: int) -> list[dict]:
    """Au plus n lignes tirées au hasard (graine fixe), dans l'ordre d'origine."""
    if n is None or n >= len(rows):
        return rows
    keep = sorted(random.Random(seed).sample(range(len(rows)), n))
    return [rows[i] for i in keep]
