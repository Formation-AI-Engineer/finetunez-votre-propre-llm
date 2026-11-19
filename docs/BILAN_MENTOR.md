# Projet 14 : point mentor, bilan du travail réalisé

4 novembre 2026

L'étape 1 est terminée : le dataset SFT et DPO est construit, désidentifié, testé et publié en
privé sur Hugging Face (`lcamara/triage-chsa`). Il reste à valider avec vous les choix sur les
données de triage synthétiques avant d'entraîner.

## Contexte

Le Centre Hospitalier Saint-Aurélien (CHSA) veut un POC d'agent de pré-triage aux urgences.
L'agent pose des questions au patient, une à la fois, propose une priorité (maximale, modérée ou
différée) et explique son choix. L'infirmier ou l'infirmière d'accueil (IOA) garde la décision.

| Choix | Retenu | Raison |
|---|---|---|
| Modèle | Qwen3-1.7B-Base | Petit, multilingue, entraînable sur un GPU gratuit |
| Entraînement | SFT + LoRA, puis DPO | SFT pour le format et les connaissances, DPO pour éviter le sous-triage |
| GPU | Kaggle (2 × T4), Colab en secours | Gratuit, sessions de 12 h |
| Service | vLLM + FastAPI, démonstration sur Modal | Facturé à l'usage |
| Référentiel de triage | FRENCH (SFMU, 2018) | Grille française officielle, 115 motifs, tri 1 à 5 |

Correspondance proposée vers les trois niveaux de la mission : tri 1-2 → maximale, tri 3A-3B →
modérée, tri 4-5 → différée.

## Étape 0 : mise en place du projet

Le projet est prêt à accueillir le code d'entraînement et l'API : dépôt, intégration continue,
comptes et GPU sont en place.

- **Dépôt GitHub** : branches `main` et `dev`, dépendances gérées avec `uv` (Python 3.12).
- **Squelette d'API** FastAPI avec une route `/api/v1/healthcheck` et son test.
- **Intégration continue** GitHub Actions : vérification du style (ruff) et tests (pytest) à
  chaque envoi.
- **Hyperparamètres de départ** : `configs/sft.yaml` et `configs/dpo.yaml`.
- **Comptes et secrets** : Hugging Face, Weights & Biases et Kaggle. Les jetons sont dans `.env`
  (ignoré par Git) et dans les secrets Kaggle, jamais dans le code.
- **Cadrage** : écarts de l'énoncé relevés dans `docs/POINT_MENTOR.md` (lien FrenchMedMCQA cassé,
  licence MedQuAD, absence de données de triage), notions clés résumées dans
  `docs/NOTIONS_CLES.md`.

## Étape 1 : collecte et structuration des données

Le dataset est produit par un programme, reproductible à l'identique en deux commandes
(`download_data.py` puis `build_dataset.py`), et vérifié par 42 tests.

### Composition

| Jeu | Train | Validation | Test |
|---|---|---|---|
| SFT : MediQAl, FrenchMedMCQA, MedQuAD, vignettes de triage | 5 065 | 448 | 950 |
| DPO : UltraMedical, paires de triage en français | 2 300 | 150 | 877 |

| Source | Langue | Licence | Rôle |
|---|---|---|---|
| MediQAl | FR | CC BY 4.0 | QCM de médecine (1 800 en train) |
| FrenchMedMCQA (`qanastek`) | FR | Apache 2.0 | QCM de pharmacie (500) |
| MedQuAD (dépôt d'origine) | EN | CC BY 4.0 | Explications en phrases (1 200) |
| UltraMedical-Preference | EN | MIT | Préférences médicales (2 000 paires) |
| Vignettes FRENCH | FR | Synthétiques | Triage : 1 565 en SFT, 300 paires DPO |

Chaque source est téléchargée à une révision fixée, avec l'empreinte SHA-256 de chaque fichier.

### Les vignettes de triage

Aucun jeu public de triage en français n'existe, je les génère donc par règles.

- **Base** : le tableau FRENCH extrait du PDF de la SFMU (115 motifs). 61 motifs et 193 critères
  sont décrits dans `configs/french_vignettes.yaml`, chaque niveau vérifié contre le tableau.
- **Trois formes** : note de l'IOA (40 %), récit du patient (35 %), dialogue où l'agent pose
  d'abord une question (25 %).
- **Réponse à format fixe** : niveau, motif, éléments déterminants, critère FRENCH cité,
  explication, conduite proposée, rappel que l'IOA décide. Le niveau est relu automatiquement
  pour l'évaluation.
- **Paires DPO** : la bonne réponse contre un **sous-triage** plausible, qui ignore les signes de
  gravité et descend d'une catégorie. C'est l'erreur la plus dangereuse.

### Le filet de sécurité sur les constantes

Des règles fixes imposent un niveau minimal : par exemple SpO2 < 86 % ou Glasgow ≤ 8 → tri 1. Les
seuils de pouls, tension, fréquence respiratoire et température ne s'appliquent qu'aux adultes.
Ces règles garantissent qu'aucune vignette n'est sous-triée. 5 % des vignettes injectent une
constante critique dans un motif bénin. Les mêmes règles serviront de garde-fou dans l'API.

### Aucune fuite entre entraînement et évaluation

Le test est construit en premier, puis la validation, puis l'entraînement, en retirant toute
question déjà vue, toutes sources confondues. Le build échoue s'il reste une fuite. Il a retiré
74 questions MedQuAD et 215 paires UltraMedical.

### Désidentification

Une partie d'UltraMedical (ChatDoctor) contient de vrais messages de patients. Les noms,
téléphones, e-mails, NIR et dates précises sont remplacés par des balises (`<PERSONNE>`…) avec
Presidio. Les âges, durées, lieux et constantes sont gardés, car utiles au triage.

- **Problème rencontré** : Presidio brut masquait 5 445 « personnes » à tort (« Splénomégalie »,
  « Parkinson », lettres de QCM).
- **Correction** : une liste d'environ 220 éponymes et médicaments, et un nom n'est masqué que
  dans un contexte de nom (civilité, présentation, parenté, signature).
- **Mesure sur 300 messages réels relus** : précision et rappel d'environ 80 %. Des prénoms isolés
  peuvent subsister.
- **Conséquence** : les données sont désidentifiées, pas anonymes. Le dataset est donc privé, et
  la justification est dans `docs/RGPD.md`.

### Documentation produite

- `docs/DONNEES.md` : inventaire, schéma des métadonnées, construction, limites.
- `docs/RGPD.md` : base légale, minimisation, méthode et mesure de la désidentification,
  conditions d'une mise en production (AIPD, hébergement HDS, AI Act).
- Fiche du dataset sur Hugging Face : sources, licences, attributions, limites.

## Points à valider avec le mentor

Plus de mentor : chaque point a été tranché et documenté (`docs/DECISIONS.md`, « Points du
4 novembre », et les documents cités).

- [x] **Vignettes synthétiques** : approche par règles dérivées de FRENCH conservée, acceptée
      comme limite signalée partout. Aucune relecture par un soignant n'a pu être organisée.
- [x] **Correspondance FRENCH → 3 niveaux** : conservée (1-2 maximale, 3A-3B modérée,
      4-5 différée).
- [x] **Seuils sur les constantes** : ceux du référentiel FRENCH chez l'adulte
      (`src/triage/rules.py`).
- [x] **Paires DPO** : UltraMedical gardé avec les paires de triage en français, limite
      documentée. Le français n'a pas régressé (`docs/EVALUATION.md`).
- [x] **Seuils d'acceptation** : sous-triage maximale ≤ 5 %, exactitude ≥ 75 %, sur-triage ≤ 20 %,
      0 réponse dangereuse, latence p95 ≤ 3 s. Les trois seuils de triage sont atteints sur le test.
- [x] **Périmètre** : questionnaire adaptatif dans l'API (`POST /api/v1/triage`), intégration
      FHIR au SI décrite dans la roadmap, sans mise en œuvre.
- [x] **Dataset** : dépôt privé, accès donné au jury sur demande (`docs/DECISIONS.md` § 8,
      `docs/RGPD.md`).
- [x] **Endpoint** : arrêt après 5 min d'inactivité, démarré avant la soutenance puis arrêté
      (`docs/GO_NO_GO.md`).
- [x] **Hébergement HDS** : dans la roadmap seulement. Modal n'est pas certifié HDS, d'où le
      no-go pour un usage réel (`docs/GO_NO_GO.md`).

## Prochaines étapes

1. **Étape 2, SFT + LoRA sur Kaggle** : charger le dataset depuis Hugging Face, refaire le filtre
   de longueur avec le tokenizer de Qwen (1 024 tokens), gérer l'écart Python 3.13 (Kaggle) /
   3.12 (projet), suivre l'entraînement dans Weights & Biases.
2. **Évaluation** : exactitude des QCM, niveau de triage correct et taux de sous-triage sur les
   vignettes de test.
3. **Étape 3, DPO** à partir du modèle SFT, puis comparaison avant et après.
4. **Étape 4, déploiement** : vLLM + FastAPI sur Modal, avec les règles sur les constantes comme
   garde-fou.
5. **Étape 5** : rapport de 20 pages maximum et démonstration.
