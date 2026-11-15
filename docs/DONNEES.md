# Données : inventaire, schéma et construction

## Reproduire

```bash
uv sync --extra data
uv run --extra data python scripts/download_data.py    # sources brutes -> data/raw/ (révisions épinglées)
uv run --extra data python scripts/build_dataset.py    # -> data/processed/ + build_log.json
uv run --extra data pytest                             # schéma, règles, anonymisation, fuites
```

`scripts/extract_french.py` régénère `configs/french_table.json` à partir du PDF FRENCH. Il n'est
utile que si le référentiel change.

## Inventaire des sources

| Source | Origine et révision | Licence | Langue | Volume brut | Usage |
|---|---|---|---|---|---|
| MediQAl | HF `ANR-MALADES/MediQAl` @ `5af3494` | CC BY 4.0 | FR | 27 634 QCM (mcqu 17 017, mcqm 10 617) + 4 969 questions ouvertes (test) | SFT, test connaissances FR |
| FrenchMedMCQA | HF `qanastek/frenchmedmcqa` @ `be9a03f`, archive `DEFT-2023-FULL.zip` | Apache 2.0 | FR | 3 105 QCM de pharmacie | SFT, test |
| MedQuAD | GitHub `abachaa/MedQuAD` @ `577bd37` | CC BY 4.0 | EN | 47 457 paires, dont 16 407 avec réponse | SFT, test |
| UltraMedical-Preference | HF `TsinghuaC3I/UltraMedical-Preference` @ `761eb79` | MIT | EN | 112 362 paires (train 109 353, dev 2 232, test 777) | DPO, test préférences |
| Référentiel FRENCH | SFMU, PDF « V1.2 » (pied de page : V1.1, juin 2018), SHA-256 `2212e10…` | SFMU, usage pédagogique | FR | 115 motifs | Vignettes de triage |

Les empreintes SHA-256 de chaque fichier brut sont dans `data/raw/MANIFEST.json`.

### Choix et constats par source

- **MediQAl** : le texte de l'énoncé dit « MediQA » ; le lien pointe vers MediQAl. Les fichiers
  sont au format JSON Lines. Il n'y a pas de justification des réponses : la réponse attendue est
  la liste des bonnes propositions et leur texte. 6 178 QCU et 3 582 QCM d'entraînement n'ont pas
  de cas clinique.
- **FrenchMedMCQA** : le lien de l'énoncé est cassé. On retient `qanastek/frenchmedmcqa`, qui a
  une licence explicite, et on lit l'archive directement, sans exécuter le script de chargement
  du dépôt. Toutes les questions portent sur la pharmacie, sans justification.
- **MedQuAD** : on utilise le dépôt d'origine plutôt que le miroir Hugging Face
  (`keivalya/MedQuad-MedicalQnADataset`). Le miroir n'indique pas de licence, alors que le dépôt
  d'origine est sous CC BY 4.0 et garde le sous-corpus, le type de question, le focus et l'URL.
  Les sous-corpus MedlinePlus ADAM, Drugs et Herbs n'ont pas de réponse : elles ont été retirées
  pour respecter le copyright de MedlinePlus, et ces sous-corpus sont donc ignorés. Deux défauts
  de la source sont corrigés : les `qid` repartent de 1 dans chaque sous-corpus (ils sont
  préfixés) et 5 documents n'ont pas d'attribut `id` (le nom de fichier sert d'identifiant).
- **UltraMedical** : chaque fichier est lu séparément, car `test.json` n'a pas la colonne
  `feedback`. La question, répétée dans `chosen` et `rejected`, n'est gardée que dans le prompt.
  Types de paires : `easy`, `hard` et `length`, plus `human` en test uniquement (163 paires).
  Les paires `length` corrigent le biais de longueur : la réponse préférée n'y est plus longue
  que dans 38 % des cas, contre 90 % pour `easy` et 78 % pour `hard`. On échantillonne donc à
  parts égales entre les trois types. 11 309 paires d'entraînement viennent de ChatDoctor, qui
  contient de vrais messages de patients : priorité de l'anonymisation.
- **FRENCH** : le tableau est extrait du PDF par `pdfplumber`. L'attribution aux colonnes a été
  vérifiée par la position horizontale du texte. La copie structurée est versionnée dans
  `configs/french_table.json`, pour que les tests tournent sans le PDF.

## Vignettes de triage synthétiques (ajout)

Aucune source ne contient de niveau de triage. Les vignettes comblent ce manque. Elles sont
**synthétiques et non validées cliniquement**, et marquées comme telles (`synthetic: true`,
`confidence: synthetic_rules`).

- **Configuration** : `configs/french_vignettes.yaml`, 61 motifs et 193 réalisations de
  critères. Chaque niveau est vérifié contre le tableau FRENCH extrait, et les tests échouent si
  un niveau n'y figure pas.
- **Tirage** : priorité équilibrée (maximale, modérée, différée), puis motif et critère. Le
  patient est tiré ensuite : âge, sexe, antécédents et constantes compatibles avec le critère.
- **Règles de sécurité** (`src/triage/rules.py`) : seuils chiffrés de FRENCH sur SpO2, FR, PAS,
  FC, température et Glasgow. Le niveau attendu n'est jamais moins grave que ces seuils. 5 % des
  vignettes injectent une constante critique dans un motif bénin (« escalade ») pour apprendre
  cette règle.
- **Trois formes** : note d'IOA (40 %), récit du patient (35 %) et dialogue (25 %). Dans le
  dialogue, l'agent pose d'abord la question clé du motif. En entraînement, environ 8 % des
  vignettes ajoutent un tour où la réponse attendue est cette question.
- **Réponse attendue** : niveau de priorité et tri FRENCH, motif, éléments déterminants avec le
  critère FRENCH cité, explication pour le patient, conduite proposée et rappel que l'IOA décide.
  `src/triage/output.py` relit ce format pour l'évaluation et l'API.
- **Paires DPO** : la réponse préférée donne le bon niveau ; la réponse rejetée sous-trie d'une
  catégorie (maximale vers modérée, modérée vers différée) en ignorant les éléments déterminants.

Correspondance vers les trois niveaux de la mission, à valider avec le mentor : tri 1-2 →
maximale, 3A-3B → modérée, 4-5 → différée.

**Limites** : les formulations sont en nombre fini. Une vignette de test n'apparaît jamais à
l'identique en entraînement, mais elle peut réutiliser la même réalisation de critère avec un
autre patient. Le test mesure donc surtout la cohérence du triage, pas la robustesse à des
formulations inédites. Une validation par des soignants, avec des cas réels anonymisés, reste
indispensable.

## Schéma

Défini dans `src/triage/data/schema.py` (pydantic) et contrôlé à l'écriture.

**SFT** : `id`, `prompt` (messages `system` puis `user`, et éventuellement un tour de dialogue),
`completion` (un message `assistant`), `metadata`.
**DPO** : `id`, `prompt`, `chosen`, `rejected`, `metadata`.

| Champ de `metadata` | Contenu |
|---|---|
| `source`, `source_id`, `source_split` | Origine et identifiant d'origine |
| `license`, `language` | Licence de la source, `fr` ou `en` |
| `task` | `qcm`, `qa`, `triage` ou `preference` |
| `confidence` | `reference` (corrigé officiel), `human_preference`, `model_judged` (juge GPT-4), `synthetic_rules` |
| `synthetic`, `anonymized` | Booléens |
| `medical_subject` | Spécialité ou focus, si la source le donne |
| `clinical` | Âge, sexe, motif, symptômes, antécédents, constantes (`Vitals`) : renseignés pour les vignettes |
| `triage` | Tri FRENCH, priorité, motif, catégorie, critère déterminant |
| `extra` | Champs propres à la source (sous-corpus, type de paire, modèles comparés…) |

L'identifiant est une empreinte stable de la source, de l'identifiant d'origine et de la variante :
il ne dépend pas de l'ordre de traitement.

Le prompt système (`src/triage/prompts.py`) est le même pour l'entraînement et le service.

## Construction

Étapes de `scripts/build_dataset.py` :

1. **Filtrage** : réponses vides, longueur totale au-delà de 3 200 caractères en SFT et 3 600 en
   DPO (environ 900 jetons ; le filtre exact au tokenizer est refait à l'étape 2), doublons
   internes sur la question normalisée.
2. **Découpage** : splits officiels pour MediQAl, FrenchMedMCQA et UltraMedical. MedQuAD n'en a
   pas : il est découpé **par document** (80/10/10), pour qu'une même maladie ne soit pas à la
   fois en entraînement et en test.
3. **Jeux d'évaluation d'abord** : test, puis validation (sans aucune question du test).
4. **Retrait des fuites** : toute question d'entraînement présente en validation ou en test, dans
   n'importe quelle source, est retirée. UltraMedical reprend notamment MedQuAD et MedQA.
5. **Sélection** selon la composition cible (tirage stratifié, graine 42).
6. **Anonymisation** (voir `docs/RGPD.md`).
7. **Écriture** et journal `data/processed/build_log.json` : comptages de chaque étape, entités
   masquées, empreintes des fichiers, révisions des sources, commit Git, graine.

## Composition obtenue

| Jeu | Train | Validation | Test |
|---|---|---|---|
| SFT MediQAl (QCU et QCM, stratifié par sous-ensemble) | 1 800 | 150 | 400 |
| SFT FrenchMedMCQA | 500 | 50 | 200 |
| SFT MedQuAD | 1 200 | 98 | 150 |
| SFT vignettes FRENCH | 1 565 (dont tours « question ») | 150 | 200 |
| **Total SFT** | **5 065** | **448** | **950** |
| DPO UltraMedical (`easy`, `hard`, `length` à parts égales) | 2 000 | 100 | 777 (test officiel complet) |
| DPO paires de triage FR | 300 | 50 | 100 |
| **Total DPO** | **2 300** | **150** | **877** |

Le test est découpé par `metadata.source` et `metadata.task` en jeux d'évaluation séparés :
connaissances FR (MediQAl et FrenchMedMCQA), questions-réponses EN (MedQuAD), triage et sécurité
(vignettes, dont les escalades), et préférences EN (UltraMedical, dont 163 paires `human`).

Retraits observés lors de la construction : 74 questions MedQuAD d'entraînement présentes dans
d'autres documents du test ou de la validation, 215 paires UltraMedical d'entraînement dont la
question figure dans un jeu d'évaluation, et 48 tours « question » de vignettes en double.
