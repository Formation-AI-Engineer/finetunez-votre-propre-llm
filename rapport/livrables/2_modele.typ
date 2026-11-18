#import "fiche.typ": fiche, note

#show: fiche.with(
  numero: "2",
  titre: "Modèle spécialisé : SFT avec LoRA, puis DPO",
  sous-titre: "Qwen3-1.7B-Base adapté au triage des urgences selon FRENCH",
)

== Où le trouver
#table(columns: (auto, 1fr),
  [Élément], [Valeur],
  [Poids finaux], [Hugging Face, `lcamara/triage-chsa-qwen3-1.7b`, révision `97e8679033fcfd24cdd28f9b4218127cbf9918f8` (privé) : modèle de base + adaptateur SFT + adaptateur DPO fusionnés, 3,4 Go. C'est la révision servie par l'endpoint (livrable 4).],
  [Adaptateurs], [Hugging Face, `lcamara/triage-chsa-adapters` (privé) : SFT `sft-r16-lr2e-4` @ `8f0cbc488afe2dce1c12bb8952cd2507e3f38cae`, DPO `dpo-b0.1-lr3e-5` @ `eb4703b855fb29f4f5a4699e4e81acd6fb2bc7d6`],
  [Copie jointe], [dossier `adaptateurs/` de ce livrable : les deux adaptateurs (environ 25 Mo chacun), identiques au Hub (empreintes SHA-256 vérifiées), avec leur `run.json` (configuration, révision du dataset, commit)],
  [Code], [`scripts/train_sft.py`, `scripts/train_dpo.py`, `scripts/merge_final.py`, `configs/sft.yaml`, `configs/dpo.yaml`, notebook Kaggle `notebooks/`],
)

#note[Les poids fusionnés (3,4 Go) ne tiennent pas dans le dépôt de la plateforme : ils restent
sur le Hub, accessibles sur demande. Les adaptateurs joints suffisent à reconstruire le modèle à
partir de `Qwen/Qwen3-1.7B-Base`, dans l'ordre : SFT d'abord fusionné, puis DPO.]

== Entraînement
#table(columns: (auto, 1fr, 1fr),
  [Réglage], [SFT avec LoRA], [DPO],
  [Point de départ], [`Qwen/Qwen3-1.7B-Base`], [modèle SFT fusionné (aussi la référence)],
  [Données], [5 065 exemples (dataset `7dffce7`)], [2 300 paires (dataset `7dffce7`)],
  [LoRA], [r = 16, α = 32, dropout 0,05, projections q, k, v, o ; plus les 4 lignes des jetons de tour, jamais entraînées dans le modèle Base], [r = 16, α = 32, projections q, k, v, o],
  [Optimisation], [lr 2·10#super[−4] (1·10#super[−4] comparé), cosinus, 3 époques, lot effectif 8, 1 024 jetons au plus], [β = 0,1, lr 3·10#super[−5] (1 et 2·10#super[−5] comparés), cosinus, 1 époque],
  [Matériel], [Kaggle, Tesla T4, fp16, 2 h 18], [Kaggle, Tesla T4, fp16, environ 1 h],
  [Choix du checkpoint], [perte de validation la plus basse (0,611 → 0,397)], [métriques de triage en validation],
)

Fusion : 99,83 % de jetons prédits identiques aux adaptateurs empilés ; mêmes résultats sur le
jeu de sécurité avant et après fusion.

== Résultats (jeu de test, évaluation unique)
#table(columns: (1fr, auto, auto, auto),
  align: (left, right, right, right),
  [Système], [Cas graves manqués], [Exactitude], [Sur-triage],
  [Modèle de base, 3 exemples (validation)], [69,7 %], [44,0 %], [18,0 %],
  [SFT + DPO, modèle seul], [3/84 (3,6 %)], [85,5 %], [12,0 %],
  [SFT + DPO + garde-fous du service], [1/84 (1,2 %)], [86,5 %], [12,0 %],
)
Seuils fixés avant le test : 5 %, 75 %, 20 %. Sur 29 cas neufs écrits à la main, 8 réponses
dangereuses pour le modèle seul, 1 avec les garde-fous (seuil : 0, non atteint). Connaissances
générales préservées (44 % sur FrenchMedMCQA, comme après le SFT). Détail : livrable 3,
sections 4 à 7.

== Charger le modèle
```python
from transformers import AutoModelForCausalLM, AutoTokenizer
rev = "97e8679033fcfd24cdd28f9b4218127cbf9918f8"
tok = AutoTokenizer.from_pretrained("lcamara/triage-chsa-qwen3-1.7b", revision=rev)
model = AutoModelForCausalLM.from_pretrained("lcamara/triage-chsa-qwen3-1.7b", revision=rev)
```
Le prompt système est celui de `src/triage/prompts.py`, avec `enable_thinking=False`. Le modèle
seul n'est pas destiné à un usage direct : il est servi derrière les garde-fous de l'API.
