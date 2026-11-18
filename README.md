# Agent de triage médical – POC pour le CHSA

POC d'un agent IA qui assiste le personnel soignant des urgences du Centre Hospitalier
Saint-Aurélien : il recueille les symptômes par un questionnaire adaptatif, propose un niveau de
priorité (maximale, modérée, différée) selon l'échelle FRENCH et explique son évaluation.
**La décision reste à l'infirmier ou l'infirmière d'accueil (IOA).**

Le modèle est Qwen3-1.7B-Base, fine-tuné par SFT avec LoRA puis aligné par DPO. vLLM le sert
derrière une API FastAPI. Trois garde-fous peuvent relever le niveau proposé, jamais le baisser :
les constantes vitales, la cohérence du critère cité et les drapeaux rouges.

Projet réalisé dans le cadre du parcours *AI Engineer* d'OpenClassrooms (projet 14).

> **Statut** : démonstration et expérimentation encadrée seulement, sur des cas fictifs. Aucun
> usage avec de vrais patients ([go / no-go](docs/GO_NO_GO.md)).

## Sommaire

1. [Prérequis](#prérequis)
2. [Démarrage rapide, sans GPU](#1-démarrage-rapide-sans-gpu)
3. [Utiliser la démonstration en ligne](#2-utiliser-la-démonstration-en-ligne)
4. [Appeler l'API](#3-appeler-lapi)
5. [Lancer le vrai modèle sur sa machine (GPU)](#4-lancer-le-vrai-modèle-sur-sa-machine-gpu)
6. [Reproduire les données, l'entraînement et l'évaluation](#5-reproduire-les-données-lentraînement-et-lévaluation)
7. [Déployer sur Modal](#6-déployer-sur-modal)
8. [Tester le déploiement et le surveiller](#7-tester-le-déploiement-et-le-surveiller)
9. [Configuration](#configuration)
10. [Organisation du dépôt](#organisation-du-dépôt) et [documentation](#documentation)

## Prérequis

| Outil | Pour quoi | Installation |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | toutes les commandes Python | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python 3.12 | | aucune : uv le télécharge si besoin |
| Docker (facultatif) | image de l'API, vrai modèle en local | <https://docs.docker.com/get-docker/> |
| GPU NVIDIA (facultatif) | vrai modèle en local, entraînement | 24 Go conseillés pour vLLM ; 2 × T4 sur Kaggle pour l'entraînement |

**Accès aux artefacts.** Le dataset (`lcamara/triage-chsa`), les adaptateurs
(`lcamara/triage-chsa-adapters`) et les poids fusionnés (`lcamara/triage-chsa-qwen3-1.7b`) sont
dans des dépôts **privés** du Hub Hugging Face. Le dataset contient des messages de patients
désidentifiés ([décision 8](docs/DECISIONS.md)). L'accès est donné sur demande. Sans cet accès,
on peut quand même lancer les tests, l'API et la page de démonstration (section 1), et
reconstruire le dataset à partir des sources publiques (section 5).

## 1. Démarrage rapide, sans GPU

Un faux serveur vLLM (`scripts/fake_vllm.py`, bibliothèque standard seulement) remplace le
modèle. Il répond toujours « DIFFÉRÉE », ce qui permet de voir les garde-fous relever le niveau.

```bash
git clone git@github.com:Formation-AI-Engineer/finetunez-votre-propre-llm.git
cd finetunez-votre-propre-llm
uv sync                      # API et outils de développement
uv run pytest                # 182 tests, sans GPU ni réseau
uv run ruff check .

cp .env.example .env
# Dans .env : choisir API_KEY et AUDIT_API_KEY, et mettre VLLM_API_KEY=local-vllm
```

Dans un premier terminal, le faux modèle (port 8001, celui de `VLLM_BASE_URL` par défaut) :

```bash
python3 scripts/fake_vllm.py 8001 local-vllm
```

Dans un second terminal, l'API :

```bash
uv run uvicorn triage.api.main:app --reload
```

- Page de démonstration : <http://localhost:8000/>. Saisir la clé d'API dans le panneau
  « Accès », en bas à droite.
- Documentation interactive de l'API : <http://localhost:8000/docs>.
- Contrôle : <http://localhost:8000/api/v1/healthcheck>. `/api/v1/readiness` indique si le
  modèle répond.

Sans aucun serveur de modèle, l'API reste utilisable : elle répond « relais IOA » et applique
seulement le plancher des constantes vitales (mode dégradé).

## 2. Utiliser la démonstration en ligne

Le service déployé est sur <https://camaralam--triage-chsa-api.us-east.modal.run/>. Il faut la
clé d'API, donnée sur demande.

Le GPU s'éteint après 5 minutes sans requête. Cliquer sur **« Réveiller le modèle »**, puis
attendre 2 à 3 minutes. Pendant ce temps, l'API répond « relais IOA ». Les cas saisis doivent
être **fictifs**.

## 3. Appeler l'API

| Méthode | Chemin | Clé | Rôle |
|---|---|---|---|
| GET | `/` | aucune | page de démonstration (elle ne contient aucune clé) |
| GET | `/api/v1/healthcheck` | aucune | l'API tourne |
| GET | `/api/v1/readiness` | aucune | le modèle répond |
| POST | `/api/v1/triage` | `X-API-Key` | un tour du questionnaire : question suivante ou évaluation |
| POST | `/api/v1/ioa` | `X-API-Key` | saisie de l'IOA seule (âge, constantes, observation), sans appel au modèle |
| GET | `/api/v1/audit` | `X-Audit-Key` | journal d'audit (clé distincte, 1 000 entrées au plus) |

```bash
curl -s -X POST http://localhost:8000/api/v1/triage \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"message": "J ai une douleur qui serre la poitrine depuis une heure.",
       "age_years": 58, "vitals": {"heart_rate": 112, "spo2": 95}}'
```

Pour poursuivre le même questionnaire, renvoyer le `session_id` reçu. Les autres champs sont
facultatifs : `age_years`, `vitals` (`heart_rate`, `systolic_bp`, `diastolic_bp`,
`respiratory_rate`, `spo2`, `temperature`, `gcs`, `glycemia`) et `observation` (texte de
l'IOA). La réponse donne le niveau retenu (`priority`), celui du modèle (`model_priority`), les
garde-fous déclenchés (`guards`) et les alertes pour l'IOA (`alerts`).

Après l'évaluation, la session est close. Un message envoyé avec `"aggravation": true` est
réévalué par le modèle, et le niveau rendu ne peut que monter. Sans ce drapeau, un message ne
peut relever le niveau que par les règles (constantes, drapeaux rouges).

L'IOA peut aussi transmettre sa saisie seule, sans attendre un message du patient
(`POST /api/v1/ioa`, mêmes champs `session_id`, `age_years`, `vitals`, `observation`). Sans
`session_id`, une session s'ouvre. Les règles s'appliquent aussitôt, sans appel au modèle :
pendant le questionnaire, un signe de tri 1 ou 2 donne une évaluation MAXIMALE ; après
l'évaluation, le niveau peut monter, jamais baisser. Sinon la réponse a le statut `saisie_ioa`
et la saisie est jointe au prochain message envoyé au modèle. Dans la page, c'est le bouton
« Transmettre » du panneau « Saisie de l'IOA ».

## 4. Lancer le vrai modèle sur sa machine (GPU)

Ce mode demande un GPU NVIDIA avec le NVIDIA Container Toolkit, et l'accès au dépôt privé des
poids. `docker-compose.yml` démarre vLLM (`vllm/vllm-openai:v0.32.0`, révision du modèle fixée)
et l'API.

```bash
cp .env.example .env    # renseigner HF_TOKEN, API_KEY, AUDIT_API_KEY, VLLM_API_KEY
docker compose up --build
```

L'API attend que vLLM soit prêt, ce qui prend quelques minutes au premier lancement (le temps
de télécharger les poids, 3,4 Go). Elle répond ensuite sur <http://localhost:8000/>.

## 5. Reproduire les données, l'entraînement et l'évaluation

### Données (CPU)

Les sources sont publiques et figées à une révision précise. Le manifeste
`data/raw/MANIFEST.json` note leur empreinte SHA-256. Détail dans
[docs/DONNEES.md](docs/DONNEES.md) et [docs/RGPD.md](docs/RGPD.md).

```bash
uv sync --extra data
uv run --extra data python scripts/download_data.py        # -> data/raw/
uv run --extra data python scripts/build_dataset.py        # -> data/processed/ (sft, dpo)
uv run --extra data python scripts/audit_anonymization.py  # contrôle de l'anonymisation
uv run --extra data python scripts/publish_dataset.py --repo <utilisateur>/triage-chsa  # dépôt privé
```

Pour entraîner sur son propre dataset, remplacer `lcamara/triage-chsa` dans `configs/sft.yaml`
et `configs/dpo.yaml` par son dépôt et sa révision.

### Entraînement et évaluation (GPU, Kaggle)

L'entraînement a été fait sur Kaggle (2 × T4). `notebooks/kaggle.ipynb` est importé une seule
fois. Il clone le dépôt, installe les versions exactes de `uv.lock`
(`scripts/kaggle/setup.sh`) et lance une étape `scripts/kaggle/<étape>.sh`.

À régler une fois dans le panneau du notebook : accélérateur **GPU T4 x2**, Internet activé, et
les secrets `HF_TOKEN`, `WANDB_API_KEY` et `GITHUB_TOKEN` (jeton *fine-grained* en lecture seule
sur le dépôt). Ensuite, changer `STEP` dans la dernière cellule et faire *Run All*. Les étapes,
dans l'ordre suivi :

| Étape | Rôle | Durée |
|---|---|---|
| `baseline` | mesure de référence du modèle de base (zero-shot et few-shot) | 10 min |
| `dtype_check` | fp16 ou fp32 sur T4 | |
| `sft_smoke` | contrôles du script SFT (sur-apprentissage volontaire, reprise) | 15 min |
| `sft` | deux runs SFT LoRA, puis évaluation sur la validation | |
| `dpo_smoke` | contrôles du script DPO | 20 min |
| `dpo` | runs DPO (référence = SFT), puis évaluation | |
| `safety` | premier jeu de sécurité (40 cas rédigés à la main) | |
| `final` | fusion des adaptateurs, **évaluation unique sur le test**, publication privée | 1 h |
| `safety_v2` | second jeu de sécurité (29 cas neufs) | |

Sur une autre machine GPU, les mêmes scripts se lancent directement, par exemple :

```bash
uv sync --extra train
CUDA_VISIBLE_DEVICES=0 uv run --extra train python scripts/train_sft.py --name sft
# sft_adapter dans configs/dpo.yaml : l'adaptateur SFT de départ (dossier local ou hf://…@révision)
CUDA_VISIBLE_DEVICES=0 uv run --extra train python scripts/train_dpo.py --name dpo
uv run --extra train python scripts/evaluate.py --name dpo --split validation \
    --adapter outputs/sft/sft/best --adapter outputs/dpo/dpo/best
```

Les options sont décrites en tête de chaque script. Les résultats sont écrits dans
`outputs/eval/<nom>/<split>/summary.md`. Les métriques, les seuils et tous les résultats sont
dans [docs/EVALUATION.md](docs/EVALUATION.md).

## 6. Déployer sur Modal

### Par la CI (voie normale)

`.github/workflows/ci.yml` s'exécute à chaque push et à chaque PR :

1. **qualité** : `ruff check`, `ruff format --check`, `pytest` ;
2. **image** : construction de l'image de l'API, test de fumée sans vLLM (relais IOA attendu),
   puis test avec le faux vLLM (garde-fou, message réécrit, audit, page servie) ;
3. **sur `main` seulement** : publication de l'image sur GHCR, déploiement sur Modal, puis
   vérification de l'API déployée.

Le lancement manuel du workflow (*Run workflow*) accepte une autre révision du modèle
(`model_revision`, 40 caractères hexadécimaux). C'est ainsi qu'on change de modèle, ou qu'on
revient à une révision précédente.

À configurer dans le dépôt GitHub (*Settings → Secrets and variables → Actions*) : les secrets
`MODAL_TOKEN_ID` et `MODAL_TOKEN_SECRET`, la variable `MODAL_API_URL` (adresse de l'API), et un
environnement `production`.

### À la main

```bash
uv tool install modal==1.6.4 --with python-dotenv
modal token new
modal secret create triage-chsa-hf HF_TOKEN=<jeton en lecture du dépôt des poids>
modal secret create triage-chsa-api API_KEY=<…> AUDIT_API_KEY=<…> VLLM_API_KEY=<…> \
    VLLM_BASE_URL=https://<espace>--triage-chsa-vllm.us-east.modal.run/v1
PYTHONPATH=src modal deploy deploy/modal_app.py
modal app history triage-chsa      # versions déployées et leur commit
```

Le GPU (L4, ou A10G en secours) s'éteint après 5 minutes sans requête : au repos, rien n'est
facturé. Ne pas lancer `modal app stop`, qui désactive l'URL : il faudrait redéployer. Le cache
du modèle et le journal d'audit sont dans deux volumes Modal persistants.

## 7. Tester le déploiement et le surveiller

Les clés sont lues dans l'environnement, jamais passées en argument. Par exemple, avec un
fichier `api.env` hors du dépôt : `set -a; . ./api.env; set +a`.

```bash
API=https://camaralam--triage-chsa-api.us-east.modal.run
uv run python scripts/load_test.py --api $API --vllm <url vLLM> --n 60 --concurrency 1 4 8 16
uv run python scripts/robustness_test.py --api $API     # 20 cas, critères écrits avant
uv run python scripts/monitor_audit.py --api $API --since 2026-11-15
PYTHONPATH=src modal run deploy/bench_engines.py --vllm <url vLLM>  # vLLM contre Transformers
```

`monitor_audit.py` calcule six indicateurs sur le journal d'audit et sort avec le code 1 si un
seuil est franchi : on peut donc le lancer dans une tâche planifiée. Les seuils et les limites
d'usage sont dans [docs/GO_NO_GO.md](docs/GO_NO_GO.md).

## Configuration

Les variables sont lues dans `.env` (copie de `.env.example`, jamais versionné) ou dans
l'environnement.

| Variable | Rôle | Par défaut |
|---|---|---|
| `API_KEY` | clé exigée par `POST /api/v1/triage` et `POST /api/v1/ioa` | `change-me` |
| `AUDIT_API_KEY` | clé distincte pour `GET /api/v1/audit` | `change-me-audit` |
| `VLLM_BASE_URL` | adresse du serveur vLLM (format OpenAI) | `http://localhost:8001/v1` |
| `VLLM_API_KEY` | clé du serveur vLLM | vide |
| `SERVED_MODEL_ID` | nom du modèle exposé par vLLM | `triage-chsa` |
| `AUDIT_LOG_PATH` | journal d'audit (JSONL, sans identifiant direct) | `outputs/audit/interactions.jsonl` |
| `APP_ENV`, `LOG_LEVEL` | environnement, niveau de journalisation | `dev`, `info` |
| `HF_TOKEN` | accès aux dépôts privés du Hub | |
| `WANDB_API_KEY`, `WANDB_PROJECT` | suivi des entraînements | `triage-chsa` |
| `MODEL_ID`, `MODEL_REVISION` | modèle servi par Modal ou Docker Compose | poids fusionnés du 13/11/2026 |

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `src/triage/` | Code : données (`data/`), entraînement, évaluation, garde-fous (`rules.py`, `consistency.py`, `red_flags.py`), service et API (`api/`) |
| `configs/` | Hyperparamètres SFT et DPO, tableau FRENCH, vignettes, jeux de sécurité, liste d'exclusion |
| `scripts/` | Données, entraînement, évaluation, publication, tests du déploiement, surveillance |
| `scripts/kaggle/` | Une étape d'entraînement ou d'évaluation par script, lancée par le notebook |
| `notebooks/` | Notebook Kaggle (inchangé d'une étape à l'autre) |
| `deploy/` | Application Modal (vLLM + API), comparaison vLLM / Transformers |
| `tests/` | Tests pytest |
| `data/`, `outputs/` | Données et résultats locaux, non versionnés (dataset et poids sur le Hub) |
| `docs/` | Suivi, décisions, évaluation, RGPD, go / no-go, énoncé |
| `livrables/` | Archive à déposer (générée, non versionnée) |

## Documentation

- [Fiche de tâches par étape](docs/TACHES.md)
- [Décisions et leur justification](docs/DECISIONS.md)
- [Données : inventaire, schéma, construction](docs/DONNEES.md)
- [Données de santé et RGPD](docs/RGPD.md)
- [Évaluation : métriques, seuils, résultats](docs/EVALUATION.md)
- [Go / no-go, limites d'usage, surveillance](docs/GO_NO_GO.md)
- [Présentation technique guidée (SFT, DPO)](docs/PRESENTATION_TECHNIQUE.md)
- [Notions clés à savoir](docs/NOTIONS_CLES.md)
- [Plan du rapport](docs/PLAN_RAPPORT.md)
- [Soutenance : réponses pour la discussion](docs/SOUTENANCE_QR.md)
- Livrables à déposer : `uv run --no-project --with typst python scripts/build_livrables.py` (fiches dans `rapport/livrables/`, archive dans `livrables/`)
- Points mentor : [écarts de l'énoncé](docs/POINT_MENTOR.md), [bilan de l'étape 1](docs/BILAN_MENTOR.md), [bilan des étapes 2 et 3](docs/BILAN_MENTOR_ETAPES_2_3.md)
