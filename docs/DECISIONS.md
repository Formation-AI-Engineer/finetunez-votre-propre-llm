# Décisions de fin d'étape 3 (13/11/2026)

Il n'y aura plus de point mentor avant la soutenance. Les questions ouvertes de
`docs/BILAN_MENTOR_ETAPES_2_3.md` (et celles du 4 novembre) sont donc tranchées ici, avec leur
justification. Elles ont été prises **avant** toute évaluation sur le jeu de test.

## 1. Système retenu : SFT + DPO (lr 3e-5), avec les deux garde-fous

Le système évalué et servi est **le modèle SFT + DPO `dpo-b0.1-lr3e-5`, suivi des règles sur
les constantes (`src/triage/rules.py`) puis de la cohérence du critère cité
(`src/triage/consistency.py`)**. Les garde-fous font partie du système. Les chiffres du modèle
seul sont toujours donnés à côté.

| Avec les deux garde-fous | Maximale manqués (validation) | Sur-triage (validation) | Dangereuses (sécurité) |
|---|---|---|---|
| SFT | 0/66 | 0,7 % | 12/40 |
| **SFT + DPO** | 0/66 | 10,0 % | **9/40** |

C'est un compromis, pas une victoire nette :

- En validation, les deux font 0/66 sur les cas maximale. Le DPO sur-trie 14 vignettes de plus
  sur 150. Taux de victoire déterministe (sous-triage compté plus grave que sur-triage) : le
  DPO gagne 6 vignettes, en perd 14, soit **−5,3 % net** face au SFT.
- Sur le jeu de sécurité, rédigé hors des gabarits d'entraînement, le DPO fait 3 réponses
  dangereuses de moins (9 contre 12). L'écart est petit, sur 40 cas.

**Le choix va au DPO**, car le jeu de sécurité est le seul à mesurer des formulations libres,
c'est-à-dire le risque réel. Un sous-triage peut retarder la prise en charge d'une urgence
vitale. Un sur-triage coûte du temps d'attente aux autres patients, et l'IOA le corrige. En
traumatologie, le Comité de traumatologie de l'American College of Surgeons tolère 25 à 35 %
de sur-triage pour viser moins de 5 % de sous-triage. **Nouveau seuil : sur-triage ≤ 20 %.**

Repli documenté : si le jury préfère limiter le sur-triage, SFT + garde-fous reste disponible.
Il est évalué lui aussi sur le test, pour mesurer l'apport du DPO, pas pour choisir.

## 2. Conclure sur le test

Une seule évaluation, sur le système retenu (étape Kaggle `final`). **Résultat (13/11)** :
1/84 cas maximale manqués (1,2 %, IC 95 % [0,2 ; 6,4]), exactitude 86,5 %, sur-triage 12,0 % :
les trois seuils sont atteints sur la valeur observée (`docs/EVALUATION.md`, « Jeu de test »). On compare la **valeur
observée** au seuil, et on donne toujours l'intervalle de Wilson à côté. Avec 84 cas maximale,
0 erreur donne une borne haute de 4,4 % et 1 erreur 6,4 %. Exiger la borne haute sous le seuil
reviendrait à exiger 0 erreur.

Pas de vignettes de test supplémentaires : en ajouter après avoir vu les résultats
changerait le protocole. La limite de taille est assumée.

## 3. Pas de DPO on-policy

Les erreurs restantes sont des cas formulés hors des gabarits (sécurité). Sur les vignettes
gabaritées, le modèle ne manque déjà plus qu'un cas maximale sur 66. Des paires générées par
le modèle sur ces vignettes ne couvriraient donc pas ses vraies faiblesses. Il faudrait
d'abord des vignettes plus variées : c'est une perspective, pas une tâche du POC.

## 4. Pas d'autre variation d'hyperparamètres

Comparés : 2 taux d'apprentissage au SFT, 3 au DPO. La perte de validation du SFT est en
plateau sans remontée, donc plus d'époques n'apporterait rien de mesurable. `r` et `beta`
restent des perspectives. Le temps GPU restant va à l'évaluation finale et à l'API.

**Biais de longueur contrôlé, sans effet** : réponses de triage de 587 caractères en moyenne
(SFT) contre 581 (DPO), QCM 109 contre 113, sécurité 491 contre 520. `sigmoid_norm` n'est donc
pas utile.

## 5. Jeu de sécurité : complété par des cas neufs pour l'étape 4

Le jeu de 40 cas est construit et mesuré (`docs/EVALUATION.md`). Les 9 échecs restants
appellent des **drapeaux rouges sur le texte du patient** (douleur thoracique avec sueurs,
déficit brutal, idées suicidaires, ingestion de médicaments chez l'enfant, crises répétées).
Ces règles seront écrites à partir des critères FRENCH de tri 1 et 2, puis mesurées sur **un
second jeu de cas neufs**, rédigé avant elles. Ce second jeu comprendra des **cas témoins sans
la phrase de pression**, pour isoler son effet. Le premier jeu, qui a inspiré les règles, ne
peut pas servir à les mesurer.

## 6. Pas de juge LLM

Les métriques cliniques (sous-triage, réponses dangereuses) sont directes et reproductibles.
Un juge LLM ajouterait son propre biais. Surtout, il faudrait envoyer à une API externe des
données issues d'un dataset privé, qui contient des messages de patients réels désidentifiés
(`docs/RGPD.md`). La comparaison par préférence est remplacée par le **taux de victoire
déterministe** du point 1 (−5,3 % net pour le DPO en validation).

## 7. Stratégie de sécurité : par l'architecture

**No-go pour le modèle seul** : 13 réponses dangereuses sur 40, toutes des sous-triages. **Go
pour le POC sous conditions** :

- les garde-fous déterministes (constantes, cohérence, puis drapeaux rouges à l'étape 4) ne
  peuvent que relever le niveau ;
- chaque réponse rappelle que l'IOA valide, et l'API renvoie ce rappel dans un champ dédié ;
- le risque résiduel est affiché : 9/40 cas dangereux avec les garde-fous actuels, sur des
  formulations libres.

Viser 0 par le modèle seul demanderait des données nouvelles et variées, hors de portée du POC.

## 8. Publication : privée

Les adaptateurs et les poids fusionnés restent dans des dépôts **privés** du Hub. Ils dérivent
d'un dataset privé qui contient des messages de patients réels désidentifiés, pas anonymes, et
un modèle peut mémoriser une partie de ses données d'entraînement. L'accès est donné au jury
sur demande.

## Points du 4 novembre

- **Vignettes synthétiques** : acceptées comme limite, signalée partout (« synthétiques et non
  validées cliniquement »). Aucune relecture par un soignant n'a pu être organisée.
- **Correspondance FRENCH → 3 niveaux** : conservée, tri 1-2 → maximale, 3A-3B → modérée,
  4-5 → différée.
- **Seuils sur les constantes** : ceux du référentiel FRENCH, chez l'adulte (`src/triage/rules.py`).
- **Seuils d'acceptation** : sous-triage maximale ≤ 5 %, exactitude ≥ 75 %, sur-triage ≤ 20 %
  (nouveau), 0 réponse dangereuse sur le jeu de sécurité, latence p95 ≤ 3 s.
