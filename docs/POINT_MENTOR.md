# Point mentor : écarts de l'énoncé et questions

Écarts relevés en analysant l'énoncé et en vérifiant ses liens le 30/10/2026, avec le choix retenu en
attendant une confirmation.

## À valider en priorité

### 1. Aucune source ne contient de données de triage

MediQAl, FrenchMedMCQA, MedQuAD et UltraMedical portent sur des connaissances médicales (QCM d'examen,
questions-réponses, préférences), sans niveau de priorité. Un modèle entraîné uniquement dessus ne
saura pas forcément trier les patients.

**Choix retenu :** ajouter des vignettes synthétiques en français, dérivées du référentiel FRENCH,
pour l'entraînement et l'évaluation, et les signaler comme synthétiques.

**Question :** cette approche est-elle acceptée ? Une autre source est-elle attendue ?

### 2. Les paires DPO ne sont ni « validées cliniquement » ni francophones

L'étape 1 parle de paires validées cliniquement. Or, dans UltraMedical, les libellés observés sont
`easy`, `hard`, `length` et `human`. Seuls 163 exemples du jeu de test sont de type `human`, et le jeu
est entièrement en anglais, alors que les patients seront francophones.

**Choix retenu :** utiliser UltraMedical, ajouter environ 300 paires de triage en français, contrôler
l'absence de régression en français, et décrire clairement cette limite.

**Question :** sans clinicien dans le projet, cette limite documentée suffit-elle ?

### 3. Le périmètre de l'agent dépasse les étapes décrites

Le courriel demande un questionnaire adaptatif et une intégration au système d'information. Ni les
étapes ni les livrables ne détaillent ces points.

**Choix retenu :** questionnaire adaptatif simple dans l'API. Pour le SI, une conception décrite dans
le rapport (FHIR), sans intégration réelle.

**Question :** ce niveau suffit-il pour la soutenance ?

### 4. Les seuils d'acceptation sont à définir

L'étape 2 exige des seuils sans les donner. Les propositions figurent dans `docs/TACHES.md`.

**Question :** ces seuils sont-ils réalistes, et faut-il les atteindre, ou un no-go argumenté est-il
acceptable ?

## Écarts mineurs

| Point | Constat | Choix retenu |
|---|---|---|
| Nom du corpus | « MediQA » dans le texte, `ANR-MALADES/MediQAl` dans le lien | MediQAl |
| Lien FrenchMedMCQA | Lien cassé (`http://nthngdy/frenchmedmcqa`). Sur le Hub, `nthngdy/frenchmedmcqa` : 1 080 lignes, sans licence ni description ; `qanastek/frenchmedmcqa` : 3 105 questions, Apache 2.0, à script de chargement | `qanastek`, en lisant ses fichiers directement, sauf avis contraire |
| Licence MedQuAD | Aucune sur le miroir `keivalya/MedQuad-MedicalQnADataset` | Vérifier la licence du dépôt d'origine avant publication |
| Modèle livré | Le tableau des livrables cite « SFT et LoRA », la mission ajoute DPO | SFT + LoRA + DPO |
| GRPO | Cité seulement à l'étape 2 (« DPO / GRPO ») | Facultatif |
| Ressource manquante | « Tutoriels LoRA + PEFT [nom & lien] » est resté à l'état de modèle | Documentation PEFT |
| Notebooks Unsloth | Rien pour Qwen3-1.7B ; pour le DPO, seulement un notebook Zephyr | Script Transformers + PEFT + TRL |
| Article JAMA | La mission parle de performances comparables à des médecins en formation. L'article montre surtout que GPT-4 seul dépasse les médecins, et que son accès ne les améliore pas significativement | Citer l'article tel quel |

## Autres questions

- Le dataset doit-il être public sur Hugging Face, ou un dépôt privé partagé suffit-il ?
- L'endpoint doit-il rester en ligne après la soutenance ? Un GPU allumé en continu coûte cher.
- Un fournisseur cloud certifié HDS est-il attendu pour le POC ? Sans donnée réelle, ce choix ne semble
  pas nécessaire : je le traiterais uniquement dans la roadmap.
- Faut-il aussi évaluer en français des cas ouverts (`oeq` de MediQAl, jeu de test uniquement) ?

## Contraintes matérielles

Le poste local n'a pas de GPU détecté (7,6 Go de RAM sous WSL2). Il sert à la préparation des données,
à l'API et aux tests. L'entraînement et vLLM tournent sur un GPU distant.
