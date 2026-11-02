# Agent de triage médical – POC pour le CHSA

POC d'un agent IA qui assiste le personnel soignant des urgences du Centre Hospitalier
Saint-Aurélien : il recueille les symptômes, propose un niveau de priorité
(maximale, modérée, différée) et explique son évaluation. La décision reste au soignant.

Projet réalisé dans le cadre du parcours *AI Engineer* d'OpenClassrooms (projet 14).

## Démarrage

```bash
cp .env.example .env
uv sync                  # API et outils de développement
uv run pytest
uv run ruff check .
uv run uvicorn triage.api.main:app --reload
```

Contrôle : <http://localhost:8000/api/v1/healthcheck>

Selon l'étape : `uv sync --extra data` (préparation des données) ou `uv sync --extra train`
(entraînement, sur une machine GPU).

Construire le dataset (voir [docs/DONNEES.md](docs/DONNEES.md)) :

```bash
uv run --extra data python scripts/download_data.py
uv run --extra data python scripts/build_dataset.py
uv run --extra data python scripts/audit_anonymization.py
```

## Organisation

| Dossier | Contenu |
|---|---|
| `src/triage/` | Code du projet (données, entraînement, API) |
| `configs/` | Hyperparamètres SFT et DPO, tableau FRENCH, vignettes, liste d'exclusion |
| `data/` | Données locales, non versionnées dans Git (dataset publié sur le Hub) |
| `scripts/`, `notebooks/` | Lancement des traitements, exploration |
| `tests/` | Tests pytest |
| `docs/` | Suivi, notions clés, points mentor, énoncé |
| `livrables/` | Archive à déposer (générée) |

## Documentation

- [Fiche de tâches par étape](docs/TACHES.md)
- [Notions clés à savoir](docs/NOTIONS_CLES.md)
- [Point mentor : écarts de l'énoncé et questions](docs/POINT_MENTOR.md)
- [Données : inventaire, schéma, construction](docs/DONNEES.md)
- [Données de santé et RGPD](docs/RGPD.md)
