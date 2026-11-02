# Suivi des tâches – POC agent de triage médical (CHSA)

Référence : énoncé OpenClassrooms (`docs/enonce/`). Durée prévue : 4 semaines, 80 heures.
Branche de travail : `dev`. Fusion vers `main` à chaque étape validée.

Légende : `[x]` fait · `[ ]` à faire · `[~]` en cours · **(ajout)** : absent de l'énoncé, mais
nécessaire d'après l'analyse (voir `docs/POINT_MENTOR.md`).

Vue d'ensemble :

| Étape | Semaine | Résultat | Livrable |
|---|---|---|---|
| 0. Cours et cadrage | avant S1 | Notions comprises, questions mentor prêtes | – |
| 1. Données | S1 | Dataset bilingue anonymisé et versionné | n° 1 |
| 2. SFT | S2 | Modèle spécialisé (adaptateur LoRA) | n° 2 |
| 3. DPO | S3 | Modèle aligné, poids finaux | n° 2 |
| 4. Déploiement | S4 | Endpoint vLLM + FastAPI, CI/CD | n° 4 et 5 |
| 5. Rapport et soutenance | S4 | Rapport de 20 pages max, démonstration | n° 3 |

---

## À faire de votre côté

Ce qui ne peut pas être fait à votre place. Le reste de la fiche est à réaliser ensemble.
Plus rien ne bloque l'étape 1.

### Étape 1 ✅
- [x] Cours OpenClassrooms : lus directement sur la plateforme, pas d'export PDF nécessaire
- [x] PDF `-2` : c'est la page de la mission, renommée
- [x] Fiche d'auto-évaluation : il n'y en a pas pour ce projet
- [x] Jeton Hugging Face (Write) et clé Weights & Biases renseignés dans `.env`

### Pour l'étape 2
- [x] GPU d'entraînement : Kaggle (gratuit), Colab en secours
- [x] Kaggle : GPU T4 x2 (15 Gio chacun), 30 Gio de RAM, sessions de 12 h, Internet activé,
      secret `HF_TOKEN` lu dans un notebook
- [x] Jeton Hugging Face remplacé après son affichage en clair (nouveau jeton Write vérifié dans `.env`)
- [x] Nouveau jeton dans le secret Kaggle `HF_TOKEN`, sortie du notebook de test effacée
- [x] `WANDB_API_KEY` ajouté aux Kaggle Secrets
- [ ] Kaggle tourne sous Python 3.13, le projet sous 3.12 : à gérer dans le notebook d'entraînement

### Avec le mentor
- [ ] Passer en revue `docs/POINT_MENTOR.md`, en commençant par les données de triage synthétiques
- [ ] Faire valider les seuils d'acceptation et la correspondance FRENCH vers les 3 niveaux

### Pour l'étape 4
- [x] Fournisseur de la démonstration : Modal (30 $ de crédits par mois, facturé seulement à l'usage)
- [ ] Compte Modal, avec un plafond de dépenses s'il demande une carte bancaire
- [ ] Jeton Hugging Face Read (ou *fine-grained* limité au dépôt du modèle) pour l'endpoint

---

## Initialisation du projet ✅

- [x] Dépôt Git local (branches `main` et `dev`), `.gitignore`, `.env.example`
- [x] `pyproject.toml` + `uv.lock` : socle API, extras `data` et `train`, groupe `dev`
- [x] Squelette `src/triage/` : configuration, route `/api/v1/healthcheck`, test pytest
- [x] CI GitHub Actions : ruff et pytest (`.github/workflows/ci.yml`)
- [x] Hyperparamètres de départ : `configs/sft.yaml`, `configs/dpo.yaml`
- [x] Dépôt distant GitHub configuré (`origin`)
- [x] Premier commit et premier envoi vers GitHub (`main` et `dev`)
- [x] Comptes et jetons : Hugging Face (Write), Weights & Biases

---

## Étape 0 – Cours et cadrage

**À la fin :** vous savez expliquer SFT, LoRA et DPO, et le périmètre est validé par le mentor.

- [ ] Lire `docs/NOTIONS_CLES.md`, puis les sections conseillées des cours
- [ ] Lire l'article du JAMA cité dans la mission (résumé dans `docs/NOTIONS_CLES.md`)
- [ ] Parcourir le référentiel FRENCH de la SFMU **(ajout)**
- [ ] Passer en revue `docs/POINT_MENTOR.md` en session de mentorat
- [ ] Valider le périmètre de l'agent : questionnaire adaptatif, intégration au SI

---

## Étape 1 – Collecter et structurer les données (semaine 1)

**À la fin :** dataset anonymisé, versionné, avec schéma de métadonnées et justification RGPD.

### Inventaire et collecte
- [ ] Inventaire des sources : origine, licence, langue, volume (`docs/DONNEES.md`)
- [ ] Trancher la source FrenchMedMCQA et vérifier la licence de MedQuAD (voir point mentor)
- [ ] Script de téléchargement avec révision Hub épinglée pour chaque source
- [ ] UltraMedical : charger chaque fichier séparément (`data/train.json`, `dev.json`, `test.json`),
      car `test.json` n'a pas la colonne `feedback` et casse le chargement global

### Schéma et normalisation
- [ ] Schéma pydantic des métadonnées : symptômes, antécédents, constantes, source, langue,
      licence, niveau de confiance, identifiant d'origine
- [ ] Format SFT conversationnel `prompt` / `completion`, format DPO `prompt` / `chosen` / `rejected`
- [ ] Convertir les QCM (`correct_answers`) en réponses rédigées, avec la justification si disponible
- [ ] Sortir la question de `chosen` et `rejected` dans UltraMedical (le prompt y est répété)
- [ ] Filtrer : réponses vides ou trop longues (MedQuAD va jusqu'à ~29 000 caractères), doublons

### Jeu de triage **(ajout)**
- [ ] Générer des vignettes FR à partir du référentiel FRENCH : motif, constantes, antécédents,
      niveau attendu et justification
- [ ] Table de correspondance vers les 3 niveaux : tri 1-2 → maximale, 3A-3B → modérée,
      4-5 → différée (à faire valider)
- [ ] Marquer ces données `synthetic` et ne jamais les présenter comme validées cliniquement

### Composition cible (à ajuster selon la qualité observée)

| Jeu | Source | Volume | Langue |
|---|---|---|---|
| SFT | MediQAl (`mcqu`, `mcqm`, train) | ~1 800 | FR |
| SFT | FrenchMedMCQA (train) | ~500 | FR |
| SFT | MedQuAD | ~1 200 | EN |
| SFT | Vignettes FRENCH **(ajout)** | ~1 500 | FR |
| DPO | UltraMedical-Preference (train) | ~2 000 | EN |
| DPO | Paires de triage FR : bon niveau / sous-triage **(ajout)** | ~300 | FR |

### Anonymisation et RGPD
- [ ] Moteurs Presidio FR (`fr_core_news_md`) et EN (`en_core_web_md`), entités personne, dates,
      téléphones, adresses
- [ ] Liste d'exclusion des éponymes : testé ici, Presidio masque « Parkinson » et
      « Guillain-Barré » comme des personnes
- [ ] Comparer les stratégies `replace`, `mask`, `redact` et justifier le choix
- [ ] Priorité sur UltraMedical : sa partie ChatDoctor contient de vrais messages de patients
- [ ] Contrôle qualité : échantillon relu à la main, faux négatifs et faux positifs mesurés
- [ ] Rédiger la justification RGPD : base légale, minimisation, traçabilité (`docs/RGPD.md`)

### Découpage et publication
- [ ] Train / val / test sans fuite : garder les tests officiels, dédoublonner **entre** sources
      (UltraMedical reprend MedQuAD et d'autres corpus)
- [ ] Jeux d'évaluation séparés : connaissances FR, préférence EN (777 exemples de test, dont 163
      annotés par des humains), triage et sécurité (~200 vignettes jamais vues)
- [ ] Journal de chaque transformation : entrée, sortie, comptages, empreinte
- [ ] Carte du dataset et dépôt Hugging Face en privé (publication à décider ensuite)
- [ ] Tests pytest : schéma, absence de fuite entre jeux, anonymisation

---

## Étape 2 – Fine-tuning supervisé avec LoRA (semaine 2)

**À la fin :** adaptateur SFT reproductible, métriques documentées, comparaison avec le modèle de base.

### Préparation
- [ ] Définir les métriques cliniques et les seuils d'acceptation (propositions ci-dessous)
- [ ] Activer le GPU Kaggle (pas de GPU sur le poste local) et installer `uv sync --extra train`
- [ ] Mesure de référence : évaluer Qwen3-1.7B-Base **avant** tout entraînement
- [ ] Choisir et documenter le mode sans raisonnement (`enable_thinking=False`)

### Entraînement
- [ ] Script SFT : Transformers + PEFT + TRL, configuré par `configs/sft.yaml`
- [ ] Petit run (~100 exemples) : la perte doit chuter jusqu'au sur-apprentissage volontaire
- [ ] Vérifier le rendu du chat template et le jeton de fin (`<|im_end|>`)
- [ ] Run complet avec suivi W&B : perte train / val, mémoire GPU, durée
- [ ] Faire varier `r`, le taux d'apprentissage et le nombre d'époques ; garder une trace de chaque essai
- [ ] Checkpoints, reprise testée, graine, hyperparamètres et révision du dataset enregistrés

### Validation intermédiaire
- [ ] Évaluation automatique : exactitude sur les QCM, niveau de triage sur les vignettes
- [ ] Contrôles de sécurité : hallucinations, recommandations dangereuses
- [ ] Surveiller le sur-apprentissage et la perte de connaissances générales
- [ ] Sélectionner l'adaptateur retenu, avec justification chiffrée

### Seuils proposés (à valider avec le mentor)

| Métrique | Seuil |
|---|---|
| Sous-triage des cas de priorité maximale | ≤ 5 % |
| Exactitude à 3 niveaux sur les vignettes | ≥ 75 % |
| Recommandation dangereuse sur le jeu de sécurité | 0 |
| Latence p95 d'une réponse | ≤ 3 s |

---

## Étape 3 – Alignement par préférences DPO (semaine 3)

**À la fin :** modèle aligné, gain mesuré par rapport au SFT seul, poids finaux disponibles.

- [ ] Script DPO : reprise de l'adaptateur SFT avec `is_trainable=True`, `configs/dpo.yaml`
- [ ] Petit run : `rewards/accuracies` doit monter et `rewards/margins` s'écarter de 0
- [ ] Faire varier `beta` et le taux d'apprentissage ; surveiller `logps/chosen`
- [ ] Contrôler le biais de longueur (catégorie `length` d'UltraMedical, `loss_type="sigmoid_norm"`)
- [ ] Comparer base / SFT / SFT + DPO sur les mêmes jeux, sécurité comprise
- [ ] Comparaison par préférence : net win rate, juge LLM avec grille
- [ ] Vérifier que le français n'a pas régressé (paires DPO majoritairement en anglais)
- [ ] Fusionner l'adaptateur et publier les poids finaux (`merge_and_unload`)
- [ ] GRPO : facultatif, à ne traiter que s'il reste du temps

---

## Étape 4 – Déployer et valider le POC (semaine 4)

**À la fin :** endpoint accessible, déploiement automatisé, tests de latence et d'audit réalisés.

### Service
- [ ] Choisir le fournisseur GPU et noter le coût
- [ ] Conteneur vLLM (`vllm serve`, modèle fusionné) et test de l'API au format OpenAI
- [ ] FastAPI : `POST /api/v1/triage`, session de questionnaire adaptatif, authentification par clé
- [ ] Règles de sécurité déterministes : les drapeaux rouges FRENCH (ex. SpO2 < 86 %) forcent la
      priorité maximale, quel que soit le modèle **(ajout)**
- [ ] Réponse structurée : niveau, explication, questions restantes, avertissement « aide à la décision »
- [ ] Page de démonstration minimale pour la soutenance
- [ ] `Dockerfile`, `docker-compose.yml`, versions épinglées, sondes de santé

### Traçabilité
- [ ] Journal d'audit : horodatage, version du modèle, prompt, réponse, niveau, latence, sans
      donnée directement identifiante
- [ ] Route de consultation d'audit protégée et test d'audit de bout en bout

### CI/CD
- [ ] Workflow de test étendu : données de test, API avec vLLM simulé
- [ ] Construction et publication de l'image, déploiement automatique sur `main`
- [ ] Déploiement d'une nouvelle version du modèle par simple changement de révision
- [ ] Secrets dans GitHub Actions uniquement, clés jamais dans le dépôt

### Tests
- [ ] Charge (locust ou équivalent) : latence p50 / p95, débit, temps au premier jeton, mémoire GPU
- [ ] Robustesse : entrées vides ou très longues, injection de prompt, anglais, vLLM indisponible
- [ ] Comparer vLLM et Transformers seul pour justifier le choix
- [ ] Limites d'usage, surveillance après déploiement, checklist go / no-go

---

## Étape 5 – Rapport et soutenance

**À la fin :** archive déposée et présentation répétée dans les temps.

### Rapport (PDF, 20 pages maximum)
- [ ] Méthodologie : données, entraînement, validation
- [ ] Métriques : latence, pertinence, sécurité, infrastructure
- [ ] Analyse des résultats, y compris les échecs et les limites
- [ ] Cadre réglementaire : RGPD, hébergement de données de santé, AI Act, dispositif médical
- [ ] Roadmap : validation clinique, modèles 32B+, données étendues, intégration FHIR au SI

### Dépôt
- [ ] Livrables nommés `Nom_Prenom_n°_nom_mmaaaa` (mois de démarrage, 102026 si le projet démarre
      en octobre 2026), dans une archive `Titre_du_projet_nom_prenom.zip`

| N° | Livrable | Forme |
|---|---|---|
| 1 | Dataset médical bilingue | HF Datasets / JSONL versionné sur un dépôt |
| 2 | Modèle SFT + LoRA + DPO | Poids finaux |
| 3 | Rapport technique et recommandations | PDF, 20 pages max |
| 4 | Endpoint de démonstration | Cloud, vLLM |
| 5 | Pipeline CI/CD | GitHub Actions |

### Soutenance : 30 minutes, l'évaluateur joue la Dr Dubois
- [ ] Présentation de 15 min (refus possible sous 10 min ou au-delà de 20 min) : démonstration,
      faisabilité technique, valeur clinique
- [ ] Discussion de 10 min : préparer méthodologie et validation, fine-tuning, passage à l'échelle,
      déploiement
- [ ] Vidéo de secours de la démonstration
- [ ] Endpoint démarré et vérifié avant la séance (puis arrêté pour limiter le coût)
