"""Vérifie l'environnement d'entraînement : versions, GPU visibles, calcul réel sur chaque carte.

Usage : uv run --extra train python scripts/check_gpu.py

Sort en erreur si aucun GPU CUDA n'est utilisable. Indique aussi la précision à employer : le
T4 de Kaggle (architecture Turing, capacité 7.5) ne gère pas le bf16, il faut donc du fp16.
"""

from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys

import torch

PACKAGES = ("torch", "transformers", "peft", "trl", "accelerate", "datasets", "wandb")


def driver_version() -> str:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], text=True
        )
        return out.splitlines()[0].strip()
    except (OSError, subprocess.CalledProcessError, IndexError):
        return "inconnu (nvidia-smi absent)"


def main() -> None:
    print(f"Python {platform.python_version()} ({sys.executable})")
    for name in PACKAGES:
        try:
            print(f"  {name:<13}{importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            print(f"  {name:<13}absent")
    print(f"CUDA de torch : {torch.version.cuda} ; pilote NVIDIA : {driver_version()}")

    if not torch.cuda.is_available():
        sys.exit(
            "ERREUR : aucun GPU CUDA utilisable. Sur Kaggle : Settings > Accelerator > GPU T4 x2."
        )

    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        a = torch.randn(1024, 1024, device=f"cuda:{i}", dtype=torch.float16)
        ok = torch.isfinite(a @ a).all().item()
        print(
            f"GPU {i} : {props.name}, {props.total_memory / 2**30:.1f} Gio, "
            f"capacité {props.major}.{props.minor}, calcul fp16 {'OK' if ok else 'EN ÉCHEC'}"
        )
        if not ok:
            sys.exit(f"ERREUR : calcul incorrect sur le GPU {i}")

    # bf16 natif à partir de l'architecture Ampere (capacité 8.0). is_bf16_supported() répond
    # « oui » sur un T4 parce qu'il compte l'émulation logicielle, beaucoup plus lente.
    gpus = range(torch.cuda.device_count())
    bf16 = all(torch.cuda.get_device_capability(i)[0] >= 8 for i in gpus)
    print(f"Précision conseillée : {'bf16' if bf16 else 'fp16 (pas de bf16 sur ce GPU)'}")


if __name__ == "__main__":
    main()
