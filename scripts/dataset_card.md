---
language:
- fr
- en
license: other
license_name: mixed
pretty_name: Triage CHSA - SFT et DPO
task_categories:
- text-generation
tags:
- medical
- triage
- synthetic
- dpo
- sft
configs:
- config_name: sft
  data_files:
  - split: train
    path: sft/train.jsonl
  - split: validation
    path: sft/validation.jsonl
  - split: test
    path: sft/test.jsonl
- config_name: dpo
  data_files:
  - split: train
    path: dpo/train.jsonl
  - split: validation
    path: dpo/validation.jsonl
  - split: test
    path: dpo/test.jsonl
---

# Triage CHSA : dataset SFT et DPO (POC)

Dataset préparé pour le POC d'agent de pré-triage des urgences du Centre Hospitalier
Saint-Aurélien (projet de formation). **Ce n'est pas un dataset clinique validé : il ne doit pas
servir à prendre des décisions médicales.**

## Contenu

| Configuration | Train | Validation | Test |
|---|---|---|---|
| `sft` : QCM MediQAl et FrenchMedMCQA, questions-réponses MedQuAD, vignettes de triage | 5 065 | 448 | 950 |
| `dpo` : UltraMedical-Preference, paires de triage (bon niveau / sous-triage) | 2 300 | 150 | 877 |

Format conversationnel compatible avec TRL : `prompt` et `completion` pour le SFT, `prompt`,
`chosen` et `rejected` pour le DPO. Chaque exemple porte des `metadata` : source, licence,
langue, tâche, niveau de confiance, et pour les vignettes le contexte clinique et le niveau de
tri attendu.

## Sources et licences

| Source | Licence | Attribution |
|---|---|---|
| MediQAl (`ANR-MALADES/MediQAl`) | CC BY 4.0 | Projet ANR MALADES |
| FrenchMedMCQA (`qanastek/frenchmedmcqa`) | Apache 2.0 | Labrak et al., DEFT 2023 |
| MedQuAD (`abachaa/MedQuAD`) | CC BY 4.0 | Ben Abacha et Demner-Fushman, BMC Bioinformatics, 2019 |
| UltraMedical-Preference (`TsinghuaC3I/UltraMedical-Preference`) | MIT | Zhang et al., 2024 |
| Vignettes de triage | Synthétiques, générées par règles | Dérivées du référentiel FRENCH (SFMU, 2018) |

## Vignettes synthétiques

Les vignettes de triage sont générées par règles à partir du tableau FRENCH. Elles sont marquées
`synthetic: true` et ne sont **pas validées cliniquement**. Correspondance retenue : tri 1-2 →
priorité maximale, 3A-3B → modérée, 4-5 → différée.

## Anonymisation

Les textes non synthétiques sont désidentifiés avec Presidio (noms, téléphones, e-mails, NIR,
dates explicites). Les éponymes médicaux, les lieux et les durées sont conservés. Mesure sur
300 messages réels de patients : précision et rappel d'environ 80 % sur les noms.
Des prénoms isolés peuvent subsister. Les données restent donc des données personnelles
désidentifiées, pas anonymes : le dépôt est **privé**.

## Construction

Reproductible depuis le dépôt du projet : `scripts/download_data.py` (révisions épinglées) puis
`scripts/build_dataset.py` (graine 42). `build_log.json` donne les comptages de chaque étape et
les empreintes des fichiers. Aucune question n'est partagée entre l'entraînement, la validation
et le test, toutes sources confondues.
