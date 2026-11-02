"""Extraction du tableau de tri FRENCH (SFMU) depuis le PDF épinglé dans data/raw/french/.

Chaque ligne du tableau donne un motif de recours, son niveau par défaut (« Tri M ») et, par
colonne, les critères qui fixent un autre niveau. L'attribution aux colonnes a été vérifiée par la
position horizontale du texte dans le PDF.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

LEVELS = ("1", "2", "3A", "3B", "4", "5")
PDF_PATH = Path("data/raw/french/french_v1.2.pdf")
PDF_SHA256 = "2212e100f5c258d0b3b432c7a540b6f428cbae3c4a3c995cb2b5a555d9544959"
# Copie structurée du tableau, versionnée pour que la CI puisse tester sans le PDF.
TABLE_PATH = Path("configs/french_table.json")


@dataclass
class Motif:
    category: str
    name: str
    default_level: str
    criteria: dict[str, str] = field(default_factory=dict)
    page: int = 0


def _cell(value: str | None) -> str:
    return " ".join((value or "").split())


def extract_table(pdf_path: Path = PDF_PATH) -> list[Motif]:
    import pdfplumber

    motifs: list[Motif] = []
    category = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for row in table:
                    cells = [_cell(c) for c in row]
                    if len(cells) != 8 or cells[0] in ("", "motif de recours", "FRENCH triage"):
                        continue
                    name, default, *by_level = cells
                    if not default:
                        category = name
                        continue
                    motifs.append(
                        Motif(
                            category=category,
                            name=name,
                            default_level=default,
                            criteria={lv: c for lv, c in zip(LEVELS, by_level, strict=True) if c},
                            page=page_number,
                        )
                    )
    return motifs


def save_table(motifs: list[Motif], path: Path = TABLE_PATH) -> None:
    payload = {
        "source": "Référentiel FRENCH, SFMU, V1.1 juin 2018 (fichier « V1.2 »)",
        "pdf_sha256": PDF_SHA256,
        "motifs": [asdict(m) for m in motifs],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_table(path: Path = TABLE_PATH) -> dict[str, Motif]:
    """Tableau versionné, indexé par nom de motif (régénéré par scripts/extract_french.py)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["name"]: Motif(**row) for row in payload["motifs"]}
