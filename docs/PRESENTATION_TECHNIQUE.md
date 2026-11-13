# Projet 14 : présentation technique guidée (étapes 2 et 3)

Déroulé pour le point mentor du 13/11/2026, environ 20 minutes. On suit le chemin d'une
exécution, du notebook Kaggle jusqu'au DPO, en ne montrant que les **points d'attention** :
les endroits où un choix a été fait, ou un piège évité. Les résultats sont dans
`docs/BILAN_MENTOR_ETAPES_2_3.md`.

| # | Partie | À ouvrir | Points d'attention |
|---|---|---|---|
| 1 | Vue d'ensemble | arborescence | qui fait quoi : local, GitHub, Hub, Kaggle |
| 2 | Notebook Kaggle | `notebooks/kaggle.ipynb` | notebook figé, secrets, versions verrouillées |
| 3 | Étapes shell | `scripts/kaggle/sft.sh` | une carte par run, smoke test avant le run complet |
| 4 | SFT | `scripts/train_sft.py` | LoRA, perte sur la réponse, jetons jamais entraînés, contrôle du template |
| 5 | Évaluation | `scripts/evaluate.py`, `src/triage/metrics.py` | génération déterministe, illisible = sous-triage, Wilson |
| 6 | DPO | `scripts/train_dpo.py` | la référence doit être le SFT, d'où la fusion |
| – | Questions probables | – | réserve |

---

## 1. Vue d'ensemble

> **À dire.** Le code est dans GitHub (branche `dev`). Les données et les adaptateurs sont dans
> des dépôts privés du Hub, à des **révisions figées**. Le calcul tourne sur Kaggle, les courbes
> vont dans W&B. Mon poste n'a pas de GPU : il sert aux données, aux tests et à l'API.

```
 Poste local ── données, tests (CPU) ──► Hub privé : dataset @7dffce7, adaptateurs @8f0cbc4
      │ git push                                       │ téléchargés à révision fixe
      ▼                                                ▼
 GitHub (dev) ──── git clone ────────────────► Kaggle, 2 × T4 ──► W&B (courbes)
                                                       └──► /kaggle/working (sorties gardées)
```

- **Séparation du code** : `src/triage/` contient la logique testable sans GPU (lecture des
  réponses, métriques, configuration), couverte par 102 tests. `scripts/` contient les points
  d'entrée GPU. `configs/` contient tous les hyperparamètres, en YAML.

---

## 2. Le notebook Kaggle

> **À dire.** Le notebook est **figé** : importé une seule fois, il récupère le code à jour à
> chaque lancement. On choisit l'étape avec une seule variable. Tout le travail est dans des
> scripts versionnés.

Il compte 4 cellules : les secrets, le clone de `dev`, l'installation (`setup.sh`), et
`STEP = "sft"` qui lance `!bash scripts/kaggle/{STEP}.sh`.

**Points d'attention**
- **Secrets.** Ils sont lus depuis les secrets Kaggle, puis placés dans des variables
  d'environnement. Le jeton GitHub passe par un en-tête HTTP, jamais par l'URL ni par
  `.git/config`. Le code est cloné dans `/tmp`, hors de `/kaggle/working`, le seul dossier que
  Kaggle publie avec le notebook.
- **Versions verrouillées.** `uv sync --frozen` installe exactement les versions de `uv.lock`
  (torch 2.14.1, transformers 5.22.1, peft 0.21.2, trl 1.17.1). Kaggle a Python 3.13 : uv
  installe la 3.12 du projet.
- **fp16 et pas bf16.** La T4 a une capacité de 7.5, et le bf16 n'existe qu'à partir de 8.
- **Lancer en commit (Save & Run All)** pour les runs longs : le run continue PC éteint, et les
  sorties sont gardées. J'ai perdu des adaptateurs une fois en mode interactif.

---

## 3. Les étapes shell

> **À dire.** Kaggle donne deux GPU : chaque étape lance deux runs en parallèle, un par carte,
> chacun suivi de son évaluation.

`scripts/kaggle/sft.sh:24` et `:33` :

```bash
CUDA_VISIBLE_DEVICES=$gpu "${PY[@]}" scripts/train_sft.py --name "$name" $overrides &&
    "${PY[@]}" scripts/evaluate.py --name "$name" --adapter "outputs/sft/$name/best" --device "cuda:$gpu"
...
train_and_evaluate "$gpu" "$name" "$overrides" > "outputs/logs/$name.log" 2>&1 &
```

**Points d'attention**
- **Une carte par processus** (`CUDA_VISIBLE_DEVICES`). Sinon, le Trainer répartit chaque lot
  sur les deux cartes, ce qui est plus lent et instable. Le script refuse d'ailleurs de démarrer
  s'il voit deux GPU.
- **Une variante = une seule valeur changée** (`--set training.learning_rate=1e-4`) : aucune
  configuration n'est dupliquée.
- **Smoke test avant chaque run complet** (15 à 20 min, contre 1 à 2 h) :
  - un sur-apprentissage volontaire, où la perte doit tomber vers 0 ;
  - un test de reprise : on tue le run après un checkpoint, puis on le relance avec `--resume`.

  C'est lui qui a révélé le bug des réponses sans fin (point 4).

---

## 4. Le SFT : `scripts/train_sft.py`

> **À dire.** Le script suit 4 blocs : configuration, données, modèle, entraînement. Je montre
> les 4 décisions qui comptent.

### 4.1 LoRA : quoi est entraîné

```
sortie = W·x + (alpha / r) · B·A·x      W gelée ; A, B entraînées ; B = 0 au départ
```

- r = 16 et alpha = 32, sur `q_proj`, `k_proj`, `v_proj` et `o_proj` des 28 couches.
- On obtient 6,4 M de paramètres entraînés, soit **0,37 %** du modèle.
- Le compte, à savoir refaire. La dimension vaut 2 048, et k et v font 1 024 (attention
  groupée).
  - Par couche : 2 × 16 × (2 048 + 2 048) pour q et o, plus 2 × 16 × (2 048 + 1 024) pour k et
    v, soit 229 376.
  - Sur 28 couches : 6 422 528. Plus 8 192 pour les 4 lignes de jetons (point 4.3).
- **Pourquoi** : un fine-tuning complet avec AdamW demande environ 4 fois le modèle en mémoire,
  hors de portée d'une T4. Et W gelé limite l'oubli des connaissances.

### 4.2 Perte sur la réponse seulement, exemples longs retirés

```python
"completion_only_loss": True,   # l. 175 : label -100 sur le prompt, ignoré par la perte
```

- Le modèle apprend à **répondre**, pas à écrire des questions de patients.
- `drop_too_long` (l. 80) **retire** les exemples de plus de 1 024 jetons au lieu de les
  tronquer. Tronqué, un exemple perdrait son `<|im_end|>` final, et le modèle apprendrait à ne
  jamais s'arrêter.

### 4.3 Le bug des jetons jamais entraînés (le point fort à raconter)

```python
# l. 156-163
peft_config = LoraConfig(
    task_type="CAUSAL_LM",
    bias="none",
    trainable_token_indices=list(token_ids.values()) or None,
    **lora,
)
```

- **Symptôme** : au premier smoke test, les 40 réponses sur 40 étaient sans fin.
- **Diagnostic** : en lisant les poids, j'ai vu que dans Qwen3-**Base**, `<|im_start|>`,
  `<|im_end|>`, `<think>` et `</think>` ont **la même ligne d'embeddings**, jamais entraînée
  (similarité cosinus de 1,000). Comme cette table sert aussi en sortie (`tie_word_embeddings`),
  le modèle ne peut pas émettre `<|im_end|>` plutôt qu'un autre de ces jetons. LoRA sur
  l'attention n'y touche pas.
- **Correction** : PEFT entraîne aussi ces 4 lignes, et rien d'autre de la table.
- **Second piège** : pour économiser la mémoire, TRL calcule la perte en lisant directement
  `lm_head.weight`, ce qui contourne ces lignes. D'où `FullLogitsSFTTrainer` (l. 38), qui revient
  à la perte standard de `transformers`. Elle coûte plus de mémoire, d'où un lot de 4 avec une
  accumulation de 2, soit un lot effectif de 8.

### 4.4 Le contrôle du template, avant de dépenser du GPU

```python
"prompt_ends_with_empty_think": prompt.endswith("<think>\n\n</think>\n\n"),   # l. 98
"completion_ends_with_end_of_turn": end_id in learned[-2:],                    # l. 99
```

- Le premier exemple est décodé **tel que le trainer va l'apprendre**, à partir des labels.
- Il doit commencer après le bloc de réflexion vide de Qwen3 (`enable_thinking=False`),
  exactement comme à l'évaluation, et finir par un seul `<|im_end|>`.
- Sinon, le run s'arrête (`SystemExit`).

Le reste est standard (`configs/sft.yaml`) :
- lr 2e-4, planning cosinus avec 5 % de warmup, 3 époques ;
- perte de validation et checkpoint tous les 100 pas, puis on garde le meilleur ;
- tout est noté dans `run.json` (commit, révision, configuration, pertes, mémoire), pour pouvoir
  refaire le run.

---

## 5. L'évaluation : `scripts/evaluate.py`

> **À dire.** Un seul script pour le modèle de base, le SFT et le SFT + DPO, avec les mêmes
> réglages : seul l'adaptateur change, donc les chiffres sont comparables.

**Points d'attention**
- **Génération déterministe** (`do_sample=False`, l. 111) : la même entrée donne toujours la même
  réponse, d'un modèle à l'autre.
- **Arrêt** sur `<|im_end|>` ou `<|endoftext|>` (l. 95). Une réponse qui ne s'arrête pas est
  comptée comme **coupée** (l. 117). C'est cet indicateur qui a révélé le bug du point 4.3.
- **Lecture prudente** (`src/triage/output.py:42`) : si la priorité annoncée et le tri FRENCH
  cité se contredisent, on retient **le plus grave** des deux.
- **Une réponse illisible compte comme un sous-triage** (`src/triage/metrics.py:105`), puisque le
  patient reste sans priorité. Un modèle qui « ne répond pas » ne peut donc pas améliorer son
  score.
- **Intervalle de Wilson à 95 %** sur chaque taux. Avec 66 cas de priorité maximale et des taux
  proches de 0, l'intervalle normal donnerait des bornes fausses, voire négatives.

---

## 6. Le DPO : `scripts/train_dpo.py`

> **À dire.** Le SFT apprend à imiter. Le DPO apprend à **préférer** : pour un même patient, la
> bonne priorité plutôt qu'un sous-triage.

### 6.1 Le principe, à savoir écrire

```
perte = −log σ( β · [ (log πθ(y⁺|x) − log πref(y⁺|x)) − (log πθ(y⁻|x) − log πref(y⁻|x)) ] )
```

- πref est le **modèle de référence**, figé. Il ancre l'entraînement : on récompense le progrès
  *relatif* à lui. β = 0,1 limite l'écart.
- Ce qu'on suit :
  - `rewards/accuracies` doit monter ;
  - `rewards/margins` doit s'écarter de 0 ;
  - `logps/chosen` ne doit pas s'effondrer. S'il s'effondre, le modèle gagne en abîmant aussi les
    bonnes réponses.

### 6.2 Le point d'attention : la référence doit être le SFT

```python
merged = peft_model.merge_and_unload()                            # l. 116
"same_top1_tokens": (before.argmax(-1) == after.argmax(-1)).mean()   # l. 122, seuil 0,98
```

- Reprendre l'adaptateur SFT tel quel posait deux problèmes, trouvés en lisant le code de
  TRL 1.17 :
  1. pour la référence, TRL copie les paramètres dont le nom contient `.default.`. Ceux des 4
     jetons se terminent par `.default` : ils ne seraient pas copiés, et la référence serait un
     SFT abîmé ;
  2. la perte du DPO passe par le même raccourci qu'au SFT, qui ignore ces lignes.
- **La solution** :
  1. on **fusionne** l'adaptateur SFT dans les poids, jetons compris ;
  2. on vérifie que les prédictions sont identiques avant et après la fusion : 99,8 % mesurés,
     les écarts venant des arrondis du fp16 ;
  3. on entraîne un **nouvel** adaptateur LoRA. Pour la référence, TRL désactive cet adaptateur,
     et retombe exactement sur le SFT.
- L'adaptateur SFT est téléchargé depuis le Hub à une révision fixe (`hf://…@8f0cbc4`).

### 6.3 Une validation en deux jeux

- On suit à part `triage` (50 paires françaises, la cible) et `medical` (99 paires en anglais),
  pour voir si l'une progresse au détriment de l'autre.
- TRL mélangeait les métriques des deux jeux sous un même nom : `NamedEvalDPOTrainer.log`
  (l. 67) les préfixe par le nom du jeu.
- Pas de sélection par la perte DPO (`load_best_model_at_end: false`) : elle ne dit pas si le
  triage est meilleur. On compare les runs avec `evaluate.py`.

---

## Questions techniques probables (réponses courtes)

**Le taux d'apprentissage ?** C'est la taille du pas : paramètre −= lr × gradient. Il vaut 2e-4
pour le SFT, la valeur classique avec LoRA. Il est 10 fois plus bas pour le DPO (1e-5 à 3e-5),
parce qu'on ajuste un modèle déjà bon.

**Accumulation et gradient checkpointing ?** L'accumulation additionne 2 mini-lots de 4 avant de
corriger, ce qui équivaut à un lot de 8 avec la mémoire d'un lot de 4. Le gradient checkpointing
recalcule les activations pendant le backward au lieu de les garder : beaucoup moins de mémoire,
pour environ 30 % de temps en plus.

**Perte de validation ou métriques métier ?** La perte détecte le sur-apprentissage. Elle ne dit
pas si la priorité est juste : seule la génération lue par `evaluate.py` le dit.

**Pourquoi le modèle Base et pas Instruct ?** C'est l'énoncé. C'est aussi la cause du bug des
jetons : un modèle Instruct les aurait déjà appris.

**SFT, DPO et RLHF ?** Le SFT imite une réponse. Le DPO compare deux réponses, sans modèle de
récompense ni PPO, à la différence du RLHF.

**Pourquoi le sur-triage augmente-t-il après le DPO ?** Les paires françaises opposent toutes la
bonne priorité à une priorité **plus basse**. Le modèle apprend donc aussi « plus haut, c'est
mieux ». La correction serait d'ajouter des paires opposées (bonne priorité contre sur-triage),
ou de tirer les paires des vraies erreurs du modèle.

**Avec un A100 ?** bf16 au lieu de fp16, des lots plus grands sans accumulation, et 5 à 10 fois
plus vite.

**Le déploiement ?** On fusionne base + SFT + DPO en un seul modèle, que vLLM sert à l'étape 4.
Les règles sur les constantes vitales restent un garde-fou dans l'API.
