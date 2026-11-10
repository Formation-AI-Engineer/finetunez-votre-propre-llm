"""
Ce script télécharge toutes les données brutes du projet dans data/raw/.
Chaque source est figée à une version précise, et le script écrit un fichier data/raw/MANIFEST.json qui note l'origine, la version,
la licence et l'empreinte SHA-256 de chaque fichier.

Le but est que n'importe qui, en relançant le script, récupère exactement les mêmes octets.
On le lance avec :
uv run --extra data python scripts/download_data.py (ajouter --force pour tout retélécharger).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import hf_hub_download

RAW_DIR = Path("data/raw").resolve()


@dataclass(frozen=True)
class HubSource:
    name: str
    repo_id: str
    revision: str
    files: tuple[str, ...]
    license: str


@dataclass(frozen=True)
class GitHubSource:
    name: str
    repo: str
    commit: str
    license: str


@dataclass(frozen=True)
class UrlSource:
    name: str
    url: str
    filename: str
    sha256: str
    license: str


HUB_SOURCES = (
    HubSource(
        name="mediqal",
        repo_id="ANR-MALADES/MediQAl",
        revision="5af34948a74c7b8807c476204a21149ffb00ea2c",
        files=tuple(
            f"{subset}/{split}.json"
            for subset in ("mcqu", "mcqm")
            for split in ("train", "validation", "test")
        )
        + ("oeq/test.json",),
        license="CC-BY-4.0",
    ),
    HubSource(
        name="frenchmedmcqa",
        repo_id="qanastek/frenchmedmcqa",
        revision="be9a03fde01d9f05107b14941af1ad99897691cf",
        files=("DEFT-2023-FULL.zip",),
        license="Apache-2.0",
    ),
    HubSource(
        name="ultramedical_preference",
        repo_id="TsinghuaC3I/UltraMedical-Preference",
        revision="761eb7935310ba662a96d93c5af342e5269d5759",
        files=("data/train.json", "data/dev.json", "data/test.json"),
        license="MIT",
    ),
)

# Dépôt d'origine plutôt que le miroir Hub (keivalya/MedQuad-MedicalQnADataset) : licence
# explicite, sous-corpus et URL d'origine conservés, réponses sous copyright MedlinePlus retirées.
GITHUB_SOURCES = (
    GitHubSource(
        name="medquad",
        repo="abachaa/MedQuAD",
        commit="577bd37b96c02d1833b2c9eed2de9f96964e96cb",
        license="CC-BY-4.0",
    ),
)


# Référentiel de tri FRENCH (SFMU) : fichier nommé V1.2, pied de page « V1.1 juin 2018 ».
URL_SOURCES = (
    UrlSource(
        name="french",
        url="https://www.sfmu.org/upload/referentielsSFMU/"
        "2019%2012%2006%20FRENCH%20pour%20PDF%20A4%20V1.2%20site.pdf",
        filename="french_v1.2.pdf",
        sha256="2212e100f5c258d0b3b432c7a540b6f428cbae3c4a3c995cb2b5a555d9544959",
        license="SFMU, usage pédagogique",
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_hub(source: HubSource, force: bool) -> list[dict]:
    target = RAW_DIR / source.name
    entries = []
    for filename in source.files:
        path = Path(
            hf_hub_download(
                repo_id=source.repo_id,
                filename=filename,
                revision=source.revision,
                repo_type="dataset",
                local_dir=target,
                force_download=force,
            )
        )
        entries.append({"file": str(path.relative_to(RAW_DIR)), "sha256": sha256(path)})
    return entries


def download_github(source: GitHubSource, force: bool) -> list[dict]:
    target = RAW_DIR / source.name
    if target.exists() and not force:
        print(f"{source.name} : déjà présent, ignoré (--force pour retélécharger)")
    else:
        shutil.rmtree(target, ignore_errors=True)
        url = f"https://codeload.github.com/{source.repo}/tar.gz/{source.commit}"
        with urllib.request.urlopen(url, timeout=120) as response:
            archive = io.BytesIO(response.read())
        with tarfile.open(fileobj=archive, mode="r:gz") as tar:
            tar.extractall(target, filter="data")
        # L'archive contient un dossier racine <dépôt>-<commit> : on le remonte d'un cran.
        (root,) = target.iterdir()
        for child in root.iterdir():
            child.rename(target / child.name)
        root.rmdir()
    files = sorted(p for p in target.rglob("*") if p.is_file())
    return [{"file": str(p.relative_to(RAW_DIR)), "sha256": sha256(p)} for p in files]


def download_url(source: UrlSource, force: bool) -> list[dict]:
    path = RAW_DIR / source.name / source.filename
    if force or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(source.url, path)
    digest = sha256(path)
    if digest != source.sha256:
        raise RuntimeError(f"{path} : empreinte inattendue {digest}, le fichier a changé en ligne")
    return [{"file": str(path.relative_to(RAW_DIR)), "sha256": digest}]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="retélécharger même si présent")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for source in HUB_SOURCES:
        print(f"{source.name} : {source.repo_id}@{source.revision[:7]}")
        manifest[source.name] = {
            "origin": f"https://huggingface.co/datasets/{source.repo_id}",
            "revision": source.revision,
            "license": source.license,
            "files": download_hub(source, args.force),
        }
    for source in GITHUB_SOURCES:
        print(f"{source.name} : {source.repo}@{source.commit[:7]}")
        manifest[source.name] = {
            "origin": f"https://github.com/{source.repo}",
            "revision": source.commit,
            "license": source.license,
            "files": download_github(source, args.force),
        }

    for source in URL_SOURCES:
        print(f"{source.name} : {source.url}")
        manifest[source.name] = {
            "origin": source.url,
            "revision": source.sha256,
            "license": source.license,
            "files": download_url(source, args.force),
        }

    manifest_path = RAW_DIR / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    for name, entry in manifest.items():
        print(f"  {name} : {len(entry['files'])} fichier(s)")
    print(f"Manifeste : {manifest_path}")


if __name__ == "__main__":
    main()
