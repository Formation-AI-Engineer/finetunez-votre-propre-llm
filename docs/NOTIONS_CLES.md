# Notions clés à savoir

Fiche de révision pour la mission et la soutenance. À compléter au fil des étapes.

## Ce que couvre cette fiche

| Source | État | Priorité de lecture |
|---|---|---|
| Post-training 101 (Tokens for Thoughts) | Lu en entier, sauf ses tableaux et figures | Haute : sections 1 à 3, DPO et GRPO, section 5 |
| Documentation TRL, DPO Trainer | Lue | Haute, au moment de l'étape 3 |
| Cours Hugging Face, chapitre 11 « Fine-tune LLMs » | Lu (sections 1 à 6). À confirmer comme cours visé par l'énoncé | Moyenne : SFT (lecture des courbes) et LoRA |
| Article JAMA Network Open (Goh et al., 2024) | Lu | Faible : le résumé ci-dessous suffit |
| Référentiel FRENCH (SFMU, v1.1, 2018) | Lu | Moyenne : pour construire les vignettes |
| Cours « Enjeux de l'IA générative pour un citoyen européen » | **Pas lu, page réservée aux inscrits** | Section 8 à recouper avec le cours |

## 1. Le parcours d'un LLM

**Modèle de base** — Entraîné à prédire le jeton suivant sur d'immenses corpus. Il sait beaucoup, mais
il *continue* le texte au lieu de répondre. C'est le cas de `Qwen3-1.7B-Base`.

**Post-training** (ou fine-tuning) — Transforme ce modèle en assistant, avec des données bien plus
réduites et soignées. La qualité des données est le facteur le plus important.

```
Base (prédit le jeton suivant) → SFT (suit les instructions) → DPO (préfère les bonnes réponses)
```

À retenir pour la soutenance : le SFT apprend **quoi répondre**, le DPO apprend **quelle réponse
préférer**.

## 2. SFT, le fine-tuning supervisé

**Principe** — Apprentissage supervisé sur des paires instruction-réponse.

**Perte** — Entropie croisée (log-vraisemblance négative) jeton par jeton, la même qu'au
pré-entraînement. Seules les données changent.

$$\mathcal{L}_{SFT}(\theta) = -\frac{1}{T}\sum_{t=1}^{T}\log p_\theta(y_t^* \mid x, y_{<t})$$

**Format conversationnel**

```json
{"prompt": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
 "completion": [{"role": "assistant", "content": "..."}]}
```

**Chat template** — Convertit les messages en texte avec les jetons spéciaux du modèle. Un mauvais
rendu fausse tout l'entraînement sans provoquer d'erreur : à contrôler en premier, avec
`tokenizer.apply_chat_template(messages, tokenize=False)`. Qwen utilise le format ChatML
(`<|im_start|>rôle … <|im_end|>`). `Qwen3-1.7B-Base` fournit déjà ce template dans son tokenizer : inutile
d'appeler `setup_chat_format`, montré dans le cours Hugging Face pour un modèle qui n'en a pas. Si le
dataset a une colonne `messages` (ou `prompt` / `completion`), `SFTTrainer` applique le template tout
seul.

**Quand faire un SFT** (cours Hugging Face) — Après avoir essayé le prompting d'un modèle instruit,
car le SFT coûte cher. Il se justifie pour imposer un format de sortie strict, pour un domaine que les
modèles maîtrisent mal, ou pour remplacer un grand modèle par un petit modèle spécialisé. C'est
exactement l'argument du POC : un 1,7B spécialisé au lieu d'un grand modèle généraliste.

**Hyperparamètres à connaître**

| Paramètre | Rôle |
|---|---|
| `num_train_epochs` ou `max_steps` | Durée de l'entraînement (le cours conseille 1 à 3 époques) |
| `per_device_train_batch_size` | Taille du lot par GPU : mémoire contre stabilité |
| `gradient_accumulation_steps` | Additionne les gradients de plusieurs petits lots : grand lot effectif sans plus de mémoire |
| `learning_rate`, `warmup_ratio` | Taille des pas, et montée progressive au début |
| `logging_steps`, `eval_steps`, `save_steps` | Fréquence des journaux, des évaluations et des checkpoints |
| `packing` | Concatène les exemples courts. Avec `max_steps`, le nombre réel d'époques change |

**Lire les courbes de perte**

| Ce qu'on voit | Diagnostic | Que faire |
|---|---|---|
| Chute rapide, puis plateau, écart faible entre train et validation | Sain | Rien |
| La perte de validation remonte pendant que celle du train baisse | Sur-apprentissage | Moins d'étapes, plus de données, données plus variées |
| Aucune baisse notable | Sous-apprentissage | Taux d'apprentissage trop faible, tâche mal posée |
| Perte du train très basse, mauvaises réponses sur des cas nouveaux | Mémorisation | Comme le sur-apprentissage |
| Format de sortie incohérent | Problème de template | Vérifier le rendu du template |

Une bonne perte ne suffit pas : lisez régulièrement des réponses générées.

**Jeton de fin** — Il doit figurer dans la cible. Sinon, le modèle ne sait pas s'arrêter.

**Padding et masque d'attention** — Les séquences d'un lot sont complétées à la même longueur. Le
masque exclut ces jetons de la perte. Regrouper les exemples de longueur proche réduit le gaspillage.

**Défauts des données**

| Défaut | Exemple ici |
|---|---|
| Bruit d'étiquette | Réponse fausse ou incomplète |
| Décalage de distribution | QCM d'examen, alors que l'usage réel est un patient qui décrit ses symptômes |
| Raisonnement trompeur | Justification sans lien avec la conclusion |

**Risques** — Sur-apprentissage et oubli des connaissances générales. Parades : petit taux
d'apprentissage, arrêt anticipé, weight decay, dropout.

## 3. LoRA

**Principe** — On gèle les poids d'origine et on ajoute à certaines couches une petite mise à jour
de faible rang :

$$W' = W + \frac{\alpha}{r}\,BA$$

$A$ et $B$ sont deux petites matrices de rang $r$. Peu de paramètres s'entraînent, donc la mémoire GPU
et le temps de calcul baissent nettement.

| Paramètre | Rôle | Point d'attention |
|---|---|---|
| `r` | Rang, donc capacité de l'adaptateur | Le cours conseille 4 à 32, en commençant par 4-8 |
| `lora_alpha` | Échelle de la mise à jour (`alpha / r`) | Environ le double de `r` |
| `target_modules` | Couches modifiées | Attention seule (`q_proj`, `k_proj`, `v_proj`, `o_proj`) ou `"all-linear"` : plus adaptable, plus de mémoire |
| `lora_dropout` | Régularisation | 0,05 à 0,1 |
| `bias` | Entraîne ou non les biais | `"none"`, le plus courant |

`configs/sft.yaml` part de `r=16` sur l'attention seule : un rang plus bas et `"all-linear"` sont à
comparer lors des petits runs.

**QLoRA** — LoRA sur un modèle de base chargé en 4 bits : encore moins de mémoire. Inutile a priori pour
un modèle de 1,7B sur un GPU de 16 Go.

**Adaptateur ou fusion** — Un adaptateur est léger et s'échange facilement : PEFT permet d'en charger
plusieurs et de basculer de l'un à l'autre (`load_adapter`, `set_adapter`), pratique pour comparer
SFT et SFT + DPO. Un modèle fusionné (`merge_and_unload`) se sert plus simplement et sans latence
supplémentaire. vLLM accepte les deux (`--enable-lora`, `--lora-modules`, `--max-lora-rank`). Le projet
retient la fusion, puisque les poids finaux sont un livrable.

Pour fusionner : garder la même précision qu'à l'entraînement, prévoir assez de mémoire pour charger
le modèle de base, et sauvegarder le tokenizer avec le modèle fusionné.

**Ordre de grandeur** — 1,7 milliard de paramètres en BF16 (2 octets) : environ 3,4 Go pour les seuls
poids. Le pic réel se mesure pendant le premier run.

## 4. DPO, l'alignement par préférences

**Principe** — À partir de triplets (prompt, réponse préférée, réponse rejetée), le modèle apprend à
écarter leurs probabilités, par rapport à un modèle de référence figé. Il n'y a pas de modèle de
récompense à entraîner.

$$\mathcal{L}_{DPO} = -\mathbb{E}\left[\log\sigma\left(\beta\left(\log\frac{\pi_\theta(y^+|x)}{\pi_{ref}(y^+|x)} - \log\frac{\pi_\theta(y^-|x)}{\pi_{ref}(y^-|x)}\right)\right)\right]$$

- $\pi_\theta$ : le modèle entraîné.
- $\pi_{ref}$ : le modèle SFT de départ. Dans TRL, c'est automatiquement l'état initial si `ref_model`
  n'est pas fourni.
- $\beta$ : contrôle l'écart au modèle de référence. Dans TRL, défaut à 0,1, et un β plus élevé
  signifie moins d'écart.

**Format attendu par TRL**

```json
{"prompt": [{"role": "user", "content": "..."}],
 "chosen": [{"role": "assistant", "content": "..."}],
 "rejected": [{"role": "assistant", "content": "..."}]}
```

**Métriques à lire**

| Métrique | Bon signe |
|---|---|
| `rewards/accuracies` | Monte : la réponse préférée passe devant |
| `rewards/margins` | S'écarte de 0 en restant raisonnable |
| `logps/chosen` | Ne s'effondre pas (voir le piège ci-dessous) |

**Pièges**

- Le DPO progresse souvent en *baissant* la réponse rejetée, pas en améliorant la réponse préférée.
- Biais de longueur : il peut favoriser les réponses longues. `sigmoid_norm` (SimPO) le corrige.
- Avec un adaptateur, TRL conseille un taux d'apprentissage vers 1e-5 (défaut du DPOConfig : 1e-6).
- `sync_ref_model=True` n'est pas compatible avec PEFT.

**Comparatif**

| Méthode | Signal | Modèle de récompense | Génère pendant l'entraînement | Coût |
|---|---|---|---|---|
| RLHF + PPO | Préférences humaines | Oui, plus un critique | Oui | Élevé |
| DPO | Paires fixes | Non | Non | Faible |
| GRPO | Récompense quelconque, K réponses comparées entre elles | Facultatif, pas de critique | Oui | Moyen |
| RLVR | Vérificateur automatique | Non | Oui | Moyen |
| RLAIF | Un LLM et une « constitution » | Oui | Oui | Moyen |

Pourquoi le DPO ici : simple, stable, compatible avec les ressources du POC, et les paires existent
déjà. La mission demande le DPO ; l'étape 2 cite aussi le GRPO, traité comme facultatif.

## 5. Évaluer un modèle post-entraîné

| Type | Comment | Forces et limites |
|---|---|---|
| Vérité terrain | Comparaison à la réponse attendue (QCM, niveau de triage) | Objectif et bon marché, limité aux tâches fermées |
| Juge LLM | Un LLM note selon une grille | Rapide, mais favorise les réponses longues et rate des problèmes subtils |
| Humain, score | Note de 1 à 7 sur une grille | Note absolue, mais bruitée |
| Humain, préférence | Choix entre A et B | Fiable, mais relatif |

**Agrégats** — Net win rate : $(W-L)/(W+L)$, de −1 à +1. Elo : le classement tient compte du niveau de
l'adversaire.

**Benchmarks standards** (cours Hugging Face) — Ils donnent une base de comparaison reproductible,
mais un bon score académique ne garantit pas l'efficacité sur le métier. MMLU (57 matières) a des
sous-tâches médicales : `anatomy`, `professional_medicine`, etc. LightEval les lance, par exemple
`mmlu|professional_medicine|0|0` en zero-shot. Utile ici pour vérifier que le SFT n'a pas détruit les
connaissances générales.

**Évaluation propre au domaine** — Le cours insiste : les benchmarks ne suffisent pas. Il faut un jeu
construit sur les vrais usages et les cas limites, plus une revue humaine ou experte. C'est le rôle du
jeu de vignettes de triage.

**Taille d'échantillon** — Avec 40 exemples par tâche, l'écart-type atteint ±0,12 dans l'exemple du
cours : un écart de quelques points peut venir du hasard. Donnez toujours l'effectif et l'incertitude.

**Contamination** — Une donnée de test présente dans le train fausse les résultats. C'est un vrai risque
ici : UltraMedical reprend notamment MedQuAD. Il faut dédoublonner entre sources.

**Spécifique au triage (non traité par les cours)**

- **Sous-triage** : un cas grave classé trop bas. C'est l'erreur la plus dangereuse, donc la métrique
  principale.
- **Sur-triage** : un cas léger classé trop haut. Coûteux, mais moins dangereux.
- **Matrice de confusion** par niveau : plus parlante qu'une exactitude globale.
- **Rappel sur la priorité maximale**.

**Infrastructure (objectif pédagogique du projet)** — Latence p50 et p95, temps au premier jeton,
jetons par seconde, requêtes simultanées, mémoire GPU, coût par heure.

## 6. Le triage médical

**FRENCH** (*FRench Emergency Nurses Classification in-Hospital*, SFMU) — Échelle française de tri par
motif de recours : tri 1, 2, 3A, 3B, 4, 5. La table associe à chaque motif un niveau de base (colonne
« Tri M », selon ma lecture) et des critères qui le modulent.

Exemple tiré du référentiel, dyspnée (tri M 3B) : détresse respiratoire, FR ≥ 40/min ou SpO2 < 86 %
→ tri 1 ; dyspnée à la parole, tirage, orthopnée, FR 30-40/min ou SpO2 86-90 % → tri 2. Les colonnes
ont été vérifiées par la position du texte dans le PDF (une version précédente de cette fiche indiquait
à tort tri 2 et tri 3A).

Vérifiez le niveau exact et les délais cibles dans le référentiel officiel : je ne les ai pas
trouvés dans le fichier consulté.

**Trois niveaux de la mission** (correspondance proposée) : maximale = tri 1-2, modérée = tri 3A-3B,
différée = tri 4-5.

**Pourquoi des règles en plus du modèle** — Certains critères sont objectifs et vitaux. Une règle
déterministe est testable et auditable, alors qu'un modèle de 1,7B peut se tromper. Le modèle recueille
et explique ; les règles garantissent un plancher de sécurité ; le soignant décide.

**Article JAMA cité par la mission** (Goh et al., 2024) — Essai randomisé, 50 médecins, GPT-4.

- Avec le LLM : 76 %. Sans : 74 %. Différence non significative (p = 0,60).
- LLM seul : 92 %, soit 16 points de plus que le groupe sans LLM (p = 0,03).
- Le modèle seul a donc fait mieux, mais il n'a pas amélioré les médecins.

À ne pas sur-interpréter en soutenance : il s'agit de GPT-4 et de raisonnement diagnostique, pas d'un
modèle de 1,7B ni de triage. L'article souligne surtout l'enjeu de l'interaction entre humain et IA.

## 7. Le déploiement

**vLLM** — Moteur d'inférence pour LLM, plus performant que Transformers seul grâce au batching continu
(les requêtes entrent et sortent d'un lot en cours) et à une gestion optimisée du cache KV. Il expose
une API au format OpenAI : `vllm serve <modèle>`.

**Raisonnement Qwen3** — Le chat template gère `enable_thinking`. S'il vaut `false`, un bloc `<think>`
vide est ajouté et le modèle répond directement. Choix du POC : désactivé, pour une latence et un format
stables. Côté vLLM, le parser lit ce réglage dans `chat_template_kwargs`.

**Architecture retenue**

```
Client / démo → FastAPI (clé API, règles de sécurité, session, audit) → vLLM (GPU, modèle fusionné)
```

**CI/CD** — Intégration continue : tests à chaque push. Déploiement continu : image construite et
publiée, puis mise en service automatique. Les secrets restent dans GitHub Actions.

**Go / no-go** — Checklist de critères mesurables, décidée à l'avance, pour autoriser ou non le passage
à l'étape suivante.

## 8. Données de santé et réglementation

Section écrite de mémoire et à recouper avec le cours européen et le mentor.

**RGPD** — Les données de santé sont une catégorie particulière (article 9). Principes à citer :
minimisation, finalité, durée de conservation, traçabilité.

**Anonymisation et pseudonymisation** — Anonymisé : ré-identification impossible, le RGPD ne s'applique
plus. Pseudonymisé (« Monsieur R. ») : toujours des données personnelles. Ne prétendez pas avoir
anonymisé sans contrôle mesuré.

**Presidio** — `AnalyzerEngine` détecte, `AnonymizerEngine` masque. Testé sur ce projet :

- « Jean Dupont » est bien détecté, mais « Parkinson » et « Guillain-Barré » le sont aussi, à tort :
  masquer ces termes détruirait l'information médicale. Il faut une liste d'exclusion.
- En anglais, « Tylenol » est classé comme organisation.

**Hébergement** — En France, l'hébergement de données de santé réelles exige un hébergeur certifié HDS.
Le POC n'utilise pas de vraies données de patients ; c'est un point clé de la roadmap.

**AI Act** — Le triage des patients aux urgences figure parmi les systèmes à haut risque (annexe III) :
gestion des risques, documentation, journalisation, contrôle humain.

**Dispositif médical** — Un logiciel d'aide au triage relèverait probablement du règlement (UE) 2017/745.
À signaler dans la roadmap : le POC n'est pas un produit clinique.

## 9. Questions probables de la Dr Dubois

| Question | Élément de réponse |
|---|---|
| Pourquoi un si petit modèle ? | Validation rapide et peu coûteuse de la chaîne, avant 32B+ |
| Pourquoi LoRA ? | Moins de mémoire et de calcul, sans toucher aux poids de base |
| Pourquoi DPO après SFT ? | Le SFT donne la compétence, le DPO affine le comportement sans modèle de récompense |
| Vos paires sont-elles validées cliniquement ? | Répondre honnêtement : seuls 163 exemples de test sont annotés par des humains ; une validation clinique reste à prévoir |
| Que se passe-t-il si le modèle se trompe ? | Règles déterministes, soignant décisionnaire, journal d'audit |
| Comment savez-vous qu'il n'y a pas de fuite de données ? | Dédoublonnage entre sources, tests automatisés, journal des transformations |
| Quelle valeur clinique ? | Taux de sous-triage et temps de recueil. Sans essai réel, le POC ne prouve qu'un potentiel |
| Que manque-t-il pour la production ? | Validation clinique, HDS, conformité AI Act et dispositif médical, intégration au SI, surveillance |

## Corrections du cours Post-training 101

Le cours contient trois erreurs. Voici les versions correctes, à retenir pour la soutenance.

**1. Les logits passent par un softmax, pas par une sigmoïde.**

Le cours parle de la sortie de la dernière couche « avant la sigmoïde ». La distribution sur le
vocabulaire s'obtient par un **softmax** (la sigmoïde ne sert que pour deux classes, comme dans la perte
DPO) :

$$p_\theta(y_t^* \mid x, y_{<t}) = \frac{\exp(z_{t,y_t^*})}{\sum_{v=1}^{V}\exp(z_{t,v})}$$

**2. Dans l'astuce log-sum-exp, on soustrait le plus grand logit, pas le plus grand exponentiel.**

Le cours écrit $m = \max_v \exp(z_{t,v})$. Il faut :

$$m = \max_{v} z_{t,v} \qquad \log\sum_{v=1}^{V}\exp(z_{t,v}) = m + \log\sum_{v=1}^{V}\exp(z_{t,v}-m)$$

Ainsi, tous les exposants $z_{t,v}-m$ sont négatifs ou nuls : aucun $\exp$ ne dépasse 1, donc pas de
dépassement de capacité. Le cours parle aussi de dépassement « d'entier » : il s'agit en réalité de
nombres à virgule flottante. En pratique, `F.cross_entropy` de PyTorch fait déjà ce calcul.

**3. Un net win rate de −1 signifie que le modèle perd toujours.**

Le cours affiche « 1.0 » pour ce cas, le signe moins a disparu :

$$\text{Net win rate} = \frac{W-L}{W+L} \in [-1, +1]$$

+1 : le modèle gagne toujours ; 0 : autant de victoires que de défaites ; **−1** : il perd toujours.

## Pièges du cours Hugging Face, chapitre 11

- **Code incomplet :** les extraits n'importent pas `AutoModelForCausalLM`, `AutoTokenizer` ni
  `setup_chat_format`, et `setup_chat_format` vient d'une ancienne version de TRL. Ne copiez pas le
  code tel quel, vérifiez l'API de la version installée.
- **Règle non respectée par son propre exemple :** le cours conseille `lora_alpha` ≈ 2 × `r`, mais
  son exemple utilise `r=6` et `lora_alpha=8` (la règle donnerait 12).
- **Backend d'évaluation :** le texte annonce vLLM, mais la commande lance `lighteval accelerate`.
- **Exemple médical discutable :** il inclut `high_school_chemistry`, qui n'est pas de la médecine.

## Sources

- [Post-training 101](https://tokens-for-thoughts.notion.site/post-training-101)
- [TRL, DPO Trainer](https://huggingface.co/docs/trl/dpo_trainer)
- [Cours LLM de Hugging Face, chapitre 11](https://huggingface.co/learn/llm-course/en/chapter11/1) (sections 1 à 6)
- [Goh et al., JAMA Network Open, 2024](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2825395)
- [Référentiel FRENCH, SFMU](https://www.sfmu.org/upload/referentielsSFMU/2019%2012%2006%20FRENCH%20pour%20PDF%20A4%20V1.2%20site.pdf)
- [vLLM, adaptateurs LoRA](https://docs.vllm.ai/en/latest/features/lora/)
- [vLLM, parser de raisonnement Qwen3](https://docs.vllm.ai/api/vllm/reasoning/qwen3_reasoning_parser.html)
- [Notebooks Unsloth](https://unsloth.ai/docs/get-started/unsloth-notebooks)
