"""Extrait le tableau FRENCH du PDF (data/raw/french/) vers configs/french_table.json.

Usage : uv run --extra data python scripts/extract_french.py
"""

from collections import Counter

from triage.data.french_table import TABLE_PATH, extract_table, save_table


def main() -> None:
    motifs = extract_table()
    save_table(motifs)
    print(f"{len(motifs)} motifs écrits dans {TABLE_PATH}")
    for category, count in Counter(m.category for m in motifs).items():
        print(f"  {category} : {count}")


if __name__ == "__main__":
    main()
