# Évaluation : métriques et seuils d'acceptation

Les métriques sont calculées par `src/triage/metrics.py`, qui est testé par `tests/test_metrics.py`.
Les mêmes fonctions servent pour le modèle de base, le SFT et le SFT + DPO, afin que les trois
soient comparés exactement de la même façon.

## Jeux d'évaluation

| Jeu | Contenu | Effectif (test) | Métriques |
|---|---|---|---|
| Vignettes de triage | `sft/test.jsonl`, `source = french_vignettes` | 200 (84 maximale, 54 modérée, 62 différée) | Triage |
| QCM FR | `sft/test.jsonl`, MediQAl + FrenchMedMCQA | 600 | QCM |
| Questions-réponses EN | `sft/test.jsonl`, MedQuAD | 150 | Lecture manuelle ou juge LLM (étape 3) |
| Préférences | `dpo/test.jsonl` | 877 | Étape 3 |

Le jeu de validation sert à choisir les hyperparamètres et le checkpoint. Le jeu de test n'est
utilisé qu'une fois, sur l'adaptateur retenu.

## Lecture des réponses

- **Triage** : `parse_assessment` (`src/triage/output.py`) lit la ligne
  `Niveau de priorité : MODÉRÉE (tri FRENCH 3A)`. Si le tri FRENCH contredit la priorité
  annoncée, c'est la plus grave des deux qui est retenue.
- **QCM** : `parse_mcq` lit `Bonne réponse : A` ou `Bonnes réponses : A, C`. Les lettres doivent
  être en majuscules et sur la même ligne.

Une réponse qui ne suit pas le format est **illisible**. Elle n'est jamais écartée du calcul :
elle compte comme une erreur, et le taux de réponses lisibles (`format_ok`) est rapporté à part.
Ce choix pénalise le modèle de base, qui ne connaît pas encore le format. Il faut donc lire son
score avec son `format_ok`.

## Métriques de triage

| Métrique | Définition | Pourquoi |
|---|---|---|
| `under_triage_maximale` | Cas attendus en priorité maximale qui ne sont **pas** classés maximale (réponses illisibles comprises) ÷ cas attendus maximale | **Métrique principale.** Un patient grave qui attend est l'erreur la plus dangereuse |
| `accuracy` | Priorité prédite = priorité attendue, ÷ toutes les vignettes | Qualité globale à 3 niveaux |
| `under_triage` | Priorité prédite moins grave que l'attendue, ou réponse illisible pour un cas non différé, ÷ toutes les vignettes | Sous-triage sur tous les niveaux |
| `over_triage` | Priorité prédite plus grave que l'attendue, ÷ toutes les vignettes | Coûteux pour le service, mais moins dangereux |
| `format_ok` | Réponses lisibles ÷ toutes les vignettes | Vérifie que le format est appris |
| Matrice de confusion | Lignes = attendu, colonnes = prédit (+ `invalide`) | Montre *où* le modèle se trompe |

## Métriques de QCM

| Métrique | Définition |
|---|---|
| `exact_match` | Ensemble des lettres prédites = ensemble des bonnes lettres |
| `hamming` | Moyenne de \|prédit ∩ attendu\| ÷ \|prédit ∪ attendu\| : crédit partiel pour les QCM à plusieurs réponses (0 pour une réponse illisible) |
| `format_ok` | Réponses lisibles ÷ toutes les questions |

Ces métriques servent à vérifier que le SFT **apporte** des connaissances, ou du moins n'en
détruit pas, par rapport au modèle de base. Elles n'ont pas de seuil d'acceptation.

## Incertitude

Chaque taux est accompagné de son **intervalle de confiance de Wilson à 95 %**. Contrairement à
l'intervalle « ± 1,96 écart-type », il reste correct pour les petits effectifs et les taux
proches de 0. Avec seulement 84 cas de priorité maximale, l'incertitude est grande :

| Cas maximale manqués | Taux mesuré | Intervalle à 95 % |
|---|---|---|
| 0 / 84 | 0,0 % | [0,0 % ; 4,4 %] |
| 2 / 84 | 2,4 % | [0,7 % ; 8,3 %] |
| 4 / 84 | 4,8 % | [1,9 % ; 11,6 %] |
| 5 / 84 | 6,0 % | [2,6 % ; 13,2 %] |

Pour une exactitude de 150 / 200, l'intervalle est [68,6 % ; 80,5 %].

## Seuils d'acceptation (propositions à valider avec le mentor)

| Métrique | Seuil | Où elle est mesurée |
|---|---|---|
| Sous-triage des cas de priorité maximale | ≤ 5 % | `metrics.ACCEPTANCE` |
| Exactitude à 3 niveaux sur les vignettes | ≥ 75 % | `metrics.ACCEPTANCE` |
| Recommandation dangereuse sur le jeu de sécurité | 0 | Jeu de sécurité, à construire (contrôles de sécurité de l'étape 2) |
| Latence p95 d'une réponse | ≤ 3 s | Endpoint vLLM, étape 4 |

**Règle de décision proposée** : on compare le taux **mesuré** au seuil, et on rapporte
toujours l'intervalle à côté. Exiger que la borne haute de l'intervalle soit sous 5 % voudrait
dire 0 erreur sur 84 cas : c'est irréaliste avec ce volume de test. Comme le tableau le montre,
un sous-triage de 4,8 % est compatible avec un vrai taux de 11 %. Les vignettes sont
synthétiques, donc ces chiffres ne garantissent rien en conditions réelles.

**Questions pour le mentor** : ces seuils sont-ils réalistes, faut-il augmenter le nombre de
vignettes de test pour resserrer l'intervalle, et un no-go argumenté est-il acceptable ?

## Lancer une évaluation

`scripts/evaluate.py` génère les réponses sur GPU, puis les note avec `src/triage/evaluation.py`.
Le dataset est lu sur le Hub à la révision fixée dans `configs/sft.yaml`.

```bash
uv run --extra train python scripts/evaluate.py --name base                      # modèle de base
uv run --extra train python scripts/evaluate.py --name base-fewshot --few-shot --batch-size 8
uv run --extra train python scripts/evaluate.py --name sft --adapter outputs/sft/best
```

Résultats dans `outputs/eval/<nom>/<split>/` : `predictions.jsonl` (réponse brute de chaque
question, pour relire les erreurs), `summary.json` et `summary.md` (métriques et conditions du
run : commit, révision du dataset, précision, GPU, durée).

Réglages communs à tous les modèles :

- **Mise en forme** : modèle de conversation Qwen3 avec `enable_thinking=False`, comme à
  l'entraînement. Le prompt se termine par `<|im_start|>assistant` et un bloc `<think></think>` vide.
- **Décodage glouton** (`do_sample=False`) : la même question donne toujours la même réponse.
- **Fin de réponse** : au premier `<|im_end|>` (fin de tour du format conversation) ou
  `<|endoftext|>` (jeton de fin du modèle de base).
- **Longueur maximale** : 320 jetons pour une vignette, 160 pour un QCM. Les corrigés font au plus
  217 et 112 jetons ; le nombre de réponses coupées est rapporté.

## Mesure de référence (modèle de base)

Deux mesures, sur le jeu de validation :

| Run | Ce qu'il mesure |
|---|---|
| `base` (*zero-shot*) | Le modèle tel qu'il serait déployé sans entraînement. Il ne connaît pas le format de réponse : un `format_ok` faible est attendu |
| `base-fewshot` | Le modèle après 3 vignettes (une par priorité) et 2 QCM résolus, tirés du jeu d'entraînement. Il sépare « ne connaît pas le format » de « ne sait pas trier » |

Le SFT est comparé aux deux : il doit faire mieux que `base-fewshot` pour justifier l'entraînement,
puisqu'un simple prompt avec exemples coûte bien moins cher. Limite : les exemples sont toujours
dans le même ordre (maximale, modérée, différée), ce qui peut pousser le modèle vers la dernière
priorité vue.
