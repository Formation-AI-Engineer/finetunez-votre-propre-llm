"""Assemble les livrables à déposer sur la plateforme, dans livrables/ (hors Git).

    uv run --no-project --with typst python scripts/build_livrables.py

Nommage de l'énoncé : Nom_Prenom_n°_nom_mmaaaa, le tout dans Titre_du_projet_nom_prenom.zip.
1. Dataset : fiche PDF + fichiers JSONL de data/processed (révision 7dffce7 du Hub).
2. Modèle : fiche PDF + adaptateurs SFT et DPO retenus (identiques au Hub, vérifié le 18/11/2026).
3. Rapport : rapport/rapport.typ compilé.
4. Endpoint : fiche PDF (URL, routes, performances ; aucune clé).
5. CI/CD : fiche PDF + .github/workflows/ci.yml.
6. Support de soutenance : livrables/CAMARA_Lamine_soutenance_102026.pptx, produit par
   rapport/soutenance_pptx.js (pptxgenjs), à générer avant ce script.
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
FICHES = ROOT / "rapport" / "livrables"
ADAPTERS = {
    "sft-r16-lr2e-4": ROOT / "outputs/sft/sft-r16-lr2e-4",
    "dpo-b0.1-lr3e-5": ROOT / "outputs/dpo/dpo-b0.1-lr3e-5",
}
PPTX = OUT / f"{PREFIX}_soutenance_{DATE}.pptx"


def name(n: int, label: str) -> str:
    return f"{PREFIX}_{n}_{label}_{DATE}"


def compile_typ(src: Path, dst: Path) -> None:
    typst.compile(str(src), output=str(dst), root=str(ROOT))


def main() -> None:
    if not PPTX.exists():
        raise SystemExit(f"Support absent : {PPTX} (lancer rapport/soutenance_pptx.js d'abord)")
    stage = OUT / ARCHIVE
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)

    # 1. Dataset
    d1 = stage / name(1, "Dataset")
    d1.mkdir()
    compile_typ(FICHES / "1_dataset.typ", d1 / f"{name(1, 'Dataset')}.pdf")
    data = d1 / "donnees"
    for f in ["README.md", "build_log.json", "sft/train.jsonl", "sft/validation.jsonl", "sft/test.jsonl",
              "dpo/train.jsonl", "dpo/validation.jsonl", "dpo/test.jsonl"]:
        (data / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "data/processed" / f, data / f)

    # 2. Modèle
    d2 = stage / name(2, "Modele")
    d2.mkdir()
    compile_typ(FICHES / "2_modele.typ", d2 / f"{name(2, 'Modele')}.pdf")
    for label, run in ADAPTERS.items():
        dst = d2 / "adaptateurs" / label
        shutil.copytree(run / "best", dst, ignore=shutil.ignore_patterns("training_args.bin"))
        shutil.copy2(run / "run.json", dst / "run.json")

    # 3. Rapport
    compile_typ(ROOT / "rapport/rapport.typ", stage / f"{name(3, 'Rapport')}.pdf")

    # 4. Endpoint
    compile_typ(FICHES / "4_endpoint.typ", stage / f"{name(4, 'Endpoint')}.pdf")

    # 5. CI/CD
    d5 = stage / name(5, "Pipeline_CICD")
    d5.mkdir()
    compile_typ(FICHES / "5_cicd.typ", d5 / f"{name(5, 'Pipeline_CICD')}.pdf")
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
