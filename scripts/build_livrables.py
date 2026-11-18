"""Assemble les livrables à déposer sur la plateforme, dans livrables/ (hors Git).

    uv run --no-project --with typst python scripts/build_livrables.py

Nommage de l'énoncé : Nom_Prenom_n°_nom_mmaaaa, le tout dans Titre_du_projet_nom_prenom.zip.
1. Dataset : liens + fichiers JSONL de data/processed (révision 7dffce7 du Hub).
2. Modèle : liens + adaptateurs SFT et DPO retenus (identiques au Hub, vérifié le 18/11/2026).
3. Rapport : rapport/rapport.typ compilé.
4. Endpoint : liens (aucune clé).
5. CI/CD : liens + .github/workflows/ci.yml.
6. Support de soutenance : livrables/CAMARA_Lamine_soutenance_102026.pptx, produit par
   rapport/soutenance_pptx.js (pptxgenjs), à générer avant ce script.
Le détail est dans le rapport : les fichiers de liens ne font que pointer vers les ressources.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import typst

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "livrables"
PREFIX = "CAMARA_Lamine"
DATE = "102026"  # mois de démarrage du projet
ARCHIVE = "Finetunez_votre_propre_LLM_CAMARA_Lamine"
REPO = "https://github.com/Formation-AI-Engineer/finetunez-votre-propre-llm"
HF = "https://huggingface.co"
API = "https://camaralam--triage-chsa-api.us-east.modal.run"
ACCESS = "Dépôts Hugging Face privés : accès sur demande."
PUBLIC = "Dépôt GitHub public le temps de la soutenance."
LINKS = {
    1: f"""# Dataset médical bilingue (Hugging Face Datasets / JSONL)

- Dépôt : [{HF}/datasets/lcamara/triage-chsa]({HF}/datasets/lcamara/triage-chsa)
- Révision : `7dffce7d0494094a0197f67a3085d8823fdb6d9f`
- Copie des fichiers : dossier `donnees/` (configurations `sft` et `dpo`, splits train,
  validation, test)
- Construction (dépôt GitHub public) :
  [scripts/build_dataset.py]({REPO}/blob/main/scripts/build_dataset.py)

{ACCESS} Données désidentifiées, remises pour la seule évaluation du projet : ne pas diffuser.
""",
    2: f"""# Modèle Qwen3-1.7B-Base spécialisé : SFT avec LoRA, puis DPO

- Poids finaux (fusionnés, servis par l'endpoint) :
  [{HF}/lcamara/triage-chsa-qwen3-1.7b]({HF}/lcamara/triage-chsa-qwen3-1.7b),
  révision `97e8679033fcfd24cdd28f9b4218127cbf9918f8`
- Adaptateurs : [{HF}/lcamara/triage-chsa-adapters]({HF}/lcamara/triage-chsa-adapters)
  - SFT `sft-r16-lr2e-4`, révision `8f0cbc488afe2dce1c12bb8952cd2507e3f38cae`
  - DPO `dpo-b0.1-lr3e-5`, révision `eb4703b855fb29f4f5a4699e4e81acd6fb2bc7d6`
- Copie des adaptateurs : dossier `adaptateurs/` (fusionner SFT puis DPO sur
  `Qwen/Qwen3-1.7B-Base`)

{ACCESS}
""",
    4: f"""# Endpoint de démonstration (Modal, vLLM)

- Page de démonstration : [{API}/]({API}/)
- Documentation de l'API : [{API}/docs]({API}/docs)
- Clés d'API et d'audit : transmises séparément.

Le modèle s'éteint après 5 minutes sans requête : bouton « Réveiller le modèle », 2 à 3 minutes.
""",
    5: f"""# Pipeline CI/CD (GitHub Actions)

- Dépôt : [{REPO}]({REPO})
- Workflow : [.github/workflows/ci.yml]({REPO}/blob/main/.github/workflows/ci.yml)
  (copie : `ci.yml`)
- Exécutions : [{REPO}/actions]({REPO}/actions)

{PUBLIC}
""",
}
ADAPTERS = {
    "sft-r16-lr2e-4": ROOT / "outputs/sft/sft-r16-lr2e-4",
    "dpo-b0.1-lr3e-5": ROOT / "outputs/dpo/dpo-b0.1-lr3e-5",
}
PPTX = OUT / f"{PREFIX}_soutenance_{DATE}.pptx"


def name(n: int, label: str) -> str:
    return f"{PREFIX}_{n}_{label}_{DATE}"


def links(n: int, label: str, folder: Path) -> None:
    (folder / f"{name(n, label)}.md").write_text(LINKS[n], encoding="utf-8")


def main() -> None:
    if not PPTX.exists():
        raise SystemExit(f"Support absent : {PPTX} (lancer rapport/soutenance_pptx.js d'abord)")
    stage = OUT / ARCHIVE
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)

    # 1. Dataset
    d1 = stage / name(1, "Dataset")
    d1.mkdir()
    links(1, "Dataset", d1)
    data = d1 / "donnees"
    for f in [
        "README.md",
        "build_log.json",
        "sft/train.jsonl",
        "sft/validation.jsonl",
        "sft/test.jsonl",
        "dpo/train.jsonl",
        "dpo/validation.jsonl",
        "dpo/test.jsonl",
    ]:
        (data / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "data/processed" / f, data / f)

    # 2. Modèle
    d2 = stage / name(2, "Modele")
    d2.mkdir()
    links(2, "Modele", d2)
    for label, run in ADAPTERS.items():
        dst = d2 / "adaptateurs" / label
        shutil.copytree(run / "best", dst, ignore=shutil.ignore_patterns("training_args.bin"))
        shutil.copy2(run / "run.json", dst / "run.json")

    # 3. Rapport
    typst.compile(
        str(ROOT / "rapport/rapport.typ"), output=str(stage / f"{name(3, 'Rapport')}.pdf")
    )

    # 4. Endpoint
    links(4, "Endpoint", stage)

    # 5. CI/CD
    d5 = stage / name(5, "Pipeline_CICD")
    d5.mkdir()
    links(5, "Pipeline_CICD", d5)
    shutil.copy2(ROOT / ".github/workflows/ci.yml", d5 / "ci.yml")

    # 6. Support de soutenance
    shutil.copy2(PPTX, stage / f"{name(6, 'Soutenance')}.pptx")

    archive = OUT / f"{ARCHIVE}.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(OUT))
    size = archive.stat().st_size / 1e6
    print(f"{archive.relative_to(ROOT)} : {size:.1f} Mo")
    for path in sorted(stage.iterdir()):
        print("  ", path.name)


if __name__ == "__main__":
    main()
