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
- **QCM, lecture stricte** : `parse_mcq` lit `Bonne réponse : A` ou `Bonnes réponses : A, C`.
  Les lettres doivent être en majuscules et sur la même ligne. C'est le format appris au SFT.
- **QCM, lecture tolérante** : `parse_mcq_lenient` lit la première « réponse … : X » du texte :
  `Réponse : c`, `Réponses : a, d`, `La réponse correcte est :` puis `**B. …` à la ligne suivante,
  `La réponse la plus spécifique … est : D`. Sans deux-points, elle lit aussi `La réponse fausse
  est E.`, mais seulement une majuscule sur la même ligne (`est a priori` n'est pas lu A). Elle
  mesure les connaissances d'un modèle qui n'a pas appris le format, comme le modèle de base.
  Deux garde-fous : une lettre qui commence un mot n'est pas lue (`Réponse : Aucune`), et les
  lignes de l'énoncé que le modèle recopie sont retirées avant lecture (`strip_echo`) : sinon
  `(cochez la réponse fausse) L'hématome … :` suivi de `A. Est une affection …` serait lu A. Les
  propositions recopiées restent, car le modèle cite souvent sa réponse telle quelle
  (`**D. L'action des corticoïdes**`). Les retirer aussi faisait perdre 19 réponses lisibles sur
  200 lors de la mesure de référence.
- **Non lu** : une réponse qui cite les propositions retenues sans les annoncer (`**B. …**`,
  `**C. …**` en liste) reste illisible. Les explications citent aussi les propositions rejetées,
  si bien que relever toutes les lettres citées serait une devinette.

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
| `exact_match_lenient`, `hamming_lenient`, `readable_lenient` | Les mêmes, en lecture tolérante |

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
uv run --extra train python scripts/evaluate.py --name sft --adapter outputs/sft/<nom>/best
```

Si la lecture des réponses ou les métriques changent, `scripts/rescore.py` recalcule les résumés à
partir de `predictions.jsonl`, sans GPU ni nouvelle génération :

```bash
uv run --extra data python scripts/rescore.py outputs/eval/base/validation
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
| `base-fewshot` | Les vignettes seulement, précédées de 3 vignettes résolues (une par priorité) tirées du jeu d'entraînement. Il sépare « ne connaît pas le format » de « ne sait pas trier » |

Le SFT est comparé aux deux : il doit faire mieux que `base-fewshot` pour justifier l'entraînement,
puisqu'un simple prompt avec exemples coûte bien moins cher. Limite : les exemples sont toujours
dans le même ordre (maximale, modérée, différée), ce qui pourrait pousser le modèle vers la
dernière priorité vue. Le biais observé va en fait vers « modérée », la priorité du milieu.

### Résultats (validation, 11/11/2026)

Commit `108a9c3`, dataset `7dffce7`, fp16 sur Tesla T4. Les résumés complets sont dans
`outputs/eval/base*/validation/summary.md`.

| Triage (150 vignettes) | `base` | `base-fewshot` |
|---|---|---|
| Sous-triage des cas maximale | 83,3 % [72,6 ; 90,4] (55/66) | 69,7 % [57,8 ; 79,4] (46/66) |
| Exactitude | 8,7 % [5,1 ; 14,3] | 44,0 % [36,3 ; 52,0] |
| Sous-triage | 57,3 % | 36,0 % |
| Sur-triage | 8,0 % | 18,0 % |
| Réponses lisibles | 17,3 % | 96,7 % |

| QCM, lecture tolérante | Exact match | Hamming | Lisibles |
|---|---|---|---|
| FrenchMedMCQA (50) | 12,0 % [5,6 ; 23,8] | 0,172 | 40,0 % |
| MediQAl (150) | 12,7 % [8,3 ; 18,9] | 0,210 | 48,0 % |

En lecture stricte, aucun QCM n'est lisible (0 %), ce qui est attendu avant le SFT.

Ce qu'on en retient :

- **Le format s'apprend avec 3 exemples** : 17 % de réponses lisibles en zero-shot, 97 % en
  few-shot.
- **Le triage, lui, ne s'apprend pas avec 3 exemples** : le modèle range presque tout en
  « modérée », y compris 38 des 66 cas de priorité maximale. Le SFT doit battre `base-fewshot`,
  c'est-à-dire 44 % d'exactitude et 70 % de sous-triage des cas maximale.
- **Les connaissances QCM sont un plancher** : la moitié des réponses n'est pas lisible. Le SFT
  devra rester au moins à ce niveau en lecture stricte (environ 12 % d'exact match).

Pas de few-shot pour les QCM : avec 2 QCM résolus en exemple, le modèle de base **recopie les
exemples** au lieu de répondre. Ses connaissances sont mesurées en zero-shot, en lecture tolérante.

### fp16 ou fp32 ?

Le T4 n'a pas de bf16, le format d'entraînement de Qwen3, et le fp16 peut déborder (valeur
maximale 65 504). Le modèle de base produisant parfois des sorties dégénérées (`.waitKey` ou
`.createTextNode` répétés), l'étape Kaggle `dtype_check` a comparé fp16 et fp32 sur les mêmes 30
questions par tâche (10/11/2026) :

| | fp16 | fp32 |
|---|---|---|
| Exactitude triage, zero-shot | 3/30 | 2/30 |
| Exactitude triage, few-shot | 13/30 | 13/30 (matrice identique) |
| Sorties dégénérées | sur les mêmes questions | sur les mêmes questions |
| Débit | 195 jetons/s | 89 jetons/s |

Les sorties dégénérées sont un comportement du modèle de base, pas un débordement numérique :
**l'inférence en fp16 est retenue**, plus de deux fois plus rapide.

## Après le SFT (validation, 12/11/2026)

Commit `737b4b0`, dataset `7dffce7`, fp16 sur Tesla T4. Deux runs identiques sauf le taux
d'apprentissage : LoRA r = 16, 3 époques (1 899 pas, lot effectif de 8), planning cosinus avec
5 % de warmup. Résumés dans `outputs/eval/sft-*/validation/summary.md`, journaux d'entraînement
dans `outputs/sft/sft-*/run.json`.

| Triage (150 vignettes) | `base-fewshot` | `sft-r16-lr2e-4` | `sft-r16-lr1e-4` |
|---|---|---|---|
| Sous-triage des cas maximale (≤ 5 %) | 69,7 % (46/66) | **10,6 % [5,2 ; 20,3]** (7/66) | 15,2 % [8,4 ; 25,7] (10/66) |
| Exactitude (≥ 75 %) | 44,0 % | **94,7 % [89,8 ; 97,3]** | 88,0 % [81,8 ; 92,3] |
| Sous-triage | 36,0 % | 4,7 % | 6,7 % |
| Sur-triage | 18,0 % | 0,7 % | 5,3 % |
| Réponses lisibles | 96,7 % | 100 % | 100 % |

| QCM, lecture stricte | `base` (tolérante) | `sft-r16-lr2e-4` | `sft-r16-lr1e-4` |
|---|---|---|---|
| FrenchMedMCQA (50) | 12,0 % | **48,0 % [34,8 ; 61,5]** | 44,0 % [31,2 ; 57,7] |
| MediQAl (150) | 12,7 % | 35,3 % [28,1 ; 43,3] | 36,7 % [29,4 ; 44,6] |

Toutes les réponses sont lisibles en lecture stricte, et aucune n'est coupée (0/350).

| Entraînement | `sft-r16-lr2e-4` | `sft-r16-lr1e-4` |
|---|---|---|
| Perte de validation, pas 100 → fin | 0,611 → **0,397** | 0,673 → 0,404 |
| Meilleur checkpoint | le dernier (1 899) | le dernier (1 899) |
| Durée, mémoire de pointe | 138 min, 11,3 Gio | 133 min, 11,3 Gio |

Ce qu'on en retient :

- **`sft-r16-lr2e-4` est retenu**. Il converge plus vite et plus bas en 3 époques, sans
  instabilité. Sa perte de validation plafonne à partir du pas 1 200 environ, sans remonter : pas
  de sur-apprentissage. À 1e-4, la perte baisse encore au dernier pas : 3 époques ne suffisent
  pas à ce taux.
- **Pas d'oubli des connaissances** : les QCM progressent, de 12 % à 35-48 %.
- **Seul le seuil de sous-triage des cas maximale n'est pas atteint** (10,6 % pour ≤ 5 %). Les 7
  erreurs classent toutes un cas maximale en « modérée », jamais en « différée », et le run à
  1e-4 les commet aussi :
  - 2 escalades par les constantes (FR 44/min dans une crise d'angoisse, PA 68/37 mmHg dans une
    phlébite) : le modèle applique le critère du motif et ignore la constante vitale. Ces
    vignettes sont rares à l'entraînement (88 sur 1 565) ; 11 des 13 de la validation sont
    réussies ;
  - 5 critères de niveau 2 propres au motif : morsure de serpent, allergie avec dyspnée,
    traumatisme à haute vélocité, fièvre ≥ 40 °C ou purpura, AES VIH de moins de 48 h.

  C'est la cible du DPO. Avec 66 cas maximale, même 3 erreurs donneraient un intervalle trop large
  pour garantir 5 % : la conclusion finale portera sur le jeu de test.

## Après le DPO (validation, 12/11/2026)

Commit `af616c5`, dataset `7dffce7`, adaptateur SFT `sft-r16-lr2e-4` (Hub, révision `8f0cbc4`)
fusionné, puis un nouvel adaptateur LoRA r = 16 entraîné par DPO : beta 0,1, 1 époque (288 pas,
lot effectif de 8 paires), planning cosinus avec 10 % de warmup, 66 min et 5,3 Gio par run.
Chiffres relevés dans la sortie du notebook : la session n'avait pas été sauvegardée, les
adaptateurs et les prédictions de ces deux runs sont perdus.

| Triage (150 vignettes) | `sft-r16-lr2e-4` | `dpo-b0.1-lr1e-5` | `dpo-b0.1-lr3e-5` |
|---|---|---|---|
| Sous-triage des cas maximale (≤ 5 %) | 10,6 % (7/66) | 6,1 % [2,4 ; 14,6] (4/66) | **1,5 % [0,3 ; 8,1]** (1/66) |
| Exactitude (≥ 75 %) | 94,7 % | 94,0 % [89,0 ; 96,8] | 90,0 % [84,2 ; 93,8] |
| Sous-triage | 4,7 % | 2,7 % | 0,7 % |
| Sur-triage | 0,7 % | 3,3 % | **9,3 %** (14/150) |
| Réponses lisibles, coupées | 100 %, 0/350 | 100 %, 0/350 | 100 %, 0/350 |

| QCM, lecture stricte | `sft-r16-lr2e-4` | `dpo-b0.1-lr1e-5` | `dpo-b0.1-lr3e-5` |
|---|---|---|---|
| FrenchMedMCQA (50) | 48,0 % | 48,0 % | 48,0 % |
| MediQAl (150) | 35,3 % | 34,7 % | 34,7 % |

| Validation DPO, fin du run | `dpo-b0.1-lr1e-5` | `dpo-b0.1-lr3e-5` |
|---|---|---|
| Paires de triage : justesse, marge | 100 %, 3,2 | 100 %, 5,6 |
| Paires médicales : justesse, marge | 77,7 %, 0,88 | 76,7 %, 1,40 |
| log-prob. des réponses chosen (triage, médical) | −1,2 → −1,4 ; −355 → −350 | −1,4 → −1,9 ; −350 → −348 |

Ce qu'on en retient :

- **Le DPO corrige le sous-triage**, en proportion du taux d'apprentissage : 7 → 4 → 1 cas
  maximale sous-triés. À 3e-5, le seuil de 5 % est atteint (borne haute de l'intervalle : 8,1 %).
- **En contrepartie, le modèle sur-trie** : à 3e-5, 9 cas modérés passent en maximale et 5 cas
  différés en modérée. Toutes les paires françaises opposent la bonne priorité à une priorité
  plus basse : le DPO apprend aussi « dans le doute, monter d'un niveau ». Aux urgences, ce sens
  d'erreur est le moins grave (attente plus courte, pas de retard de soin), mais il encombre les
  box.
- **Pas de régression ailleurs** : QCM inchangés, format intact, paires médicales stables, et la
  probabilité des bonnes réponses ne s'effondre pas (dérive classique du DPO, observée seulement
  dans le sur-apprentissage volontaire du smoke test).
- Les paires de triage de validation sont trop faciles pour la mesure : le modèle SFT les réussit
  déjà toutes (justesse 100 % dès le premier point). Seule l'évaluation par génération
  (`evaluate.py`) départage les runs.
