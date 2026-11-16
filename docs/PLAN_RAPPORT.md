# Plan du rapport technique (étape 5)

Livrable n° 3 : « Rapport technique complet et recommandations stratégiques », PDF, **20 pages
au maximum**. Cible : **18 pages**, pour garder de la marge. Lectrice : la Dr Dubois, directrice
de l'innovation médicale. Elle n'est pas ingénieure : chaque section technique s'ouvre sur une
phrase qui dit ce que cela change pour le CHSA.

L'énoncé demande quatre contenus. Le plan les couvre tous, et ajoute ce que la mission et les
points de vigilance demandent aussi :

| Attendu de l'énoncé | Sections |
|---|---|
| Méthodologie : préparation des données et entraînement | 3, 4, 5 |
| Métriques de performance (latence, pertinence, etc.) | 6 |
| Analyse des résultats | 6, 7 |
| Roadmap de passage à l'échelle au CHSA | 10 |
| Mission : traçabilité, intégration au SI | 2, 8, 10 |
| Points de vigilance : secrets, surveillance, limites d'usage, go / no-go | 7, 8, 9 |

**Format** : source Typst versionnée (`rapport/rapport.typ`), compilée en PDF avec
`uvx --from typst` (aucune installation système). Les figures sont produites par un script à
partir de `outputs/`, pour que chaque chiffre du rapport soit traçable.

## Plan détaillé

| § | Titre | Pages | Contenu | Sources |
|---|---|---|---|---|
| — | Page de garde | 1 | Titre, CHSA, auteur, date, version du modèle et du service | |
| 0 | Synthèse | 1 | Verdict go / no-go en un tableau, 5 chiffres clés (1,2 % de sous-triage maximale, 86,5 % d'exactitude, 12 % de sur-triage, 1/29 réponse dangereuse, p95 de 2,03 s), les 3 recommandations | `GO_NO_GO.md` |
| 1 | Contexte et objectifs | 1 | Surcharge des urgences, les 5 attentes de la mission, ce que le POC fait et ne fait pas, l'IOA décide toujours, seuils fixés avant le test | énoncé, `DECISIONS.md` |
| 2 | Architecture du système | 1,5 | **Schéma** : patient → API → vLLM → 3 garde-fous (constantes, cohérence du critère, drapeaux rouges) → message et journal d'audit. Questionnaire adaptatif, échelle FRENCH ramenée à 3 niveaux. Les garde-fous ne peuvent que relever le niveau | `DECISIONS.md` § 7, `src/triage/` |
| 3 | Données | 2,5 | Inventaire des 4 sources et constat : aucune ne contient de triage, d'où les vignettes synthétiques. Composition, schéma, découpage sans fuite, paires DPO (UltraMedical, anglophones, non validées cliniquement). Anonymisation et RGPD en résumé | `DONNEES.md`, `RGPD.md`, `POINT_MENTOR.md` |
| 4 | Entraînement | 2,5 | SFT LoRA : réglages, perte sur la réponse seule, **bug des jetons jamais entraînés**, contrôle du template avant le GPU. DPO : principe, référence = SFT, 3 taux d'apprentissage comparés. Fusion des poids, contrôles, publication privée. Contraintes matérielles (Kaggle) | `PRESENTATION_TECHNIQUE.md`, `BILAN_MENTOR_ETAPES_2_3.md` |
| 5 | Protocole de validation | 1,5 | Jeux (validation, test, sécurité v1 et v2), métriques, intervalles de Wilson, règle de décision, **une seule évaluation sur le test**, seuils écrits avant | `EVALUATION.md` |
| 6 | Résultats | 3 | Pertinence au test (tableau des 6 systèmes), apport du DPO et des garde-fous (**figure**), sécurité, QCM, latence par palier (**figure**), vLLM contre Transformers, robustesse 20/20 | `EVALUATION.md`, `outputs/` |
| 7 | Échecs et limites | 2 | Les **5 défauts trouvés sur le vrai déploiement**, invisibles aux tests unitaires. Le cas manqué (brûlure). Limites d'usage. Biais d'auteur, données synthétiques, taille du test | `EVALUATION.md`, `GO_NO_GO.md` |
| 8 | Déploiement et exploitation | 1,5 | Modal et vLLM, secrets et clés, journal d'audit, CI/CD (**schéma**), mode dégradé, surveillance (6 indicateurs), retour arrière, coûts | `GO_NO_GO.md`, `.github/workflows/` |
| 9 | Cadre réglementaire | 1 | RGPD et AIPD, hébergement HDS (Modal ne l'est pas), AI Act (haut risque, annexe III), dispositif médical (règlement 2017/745) | `RGPD.md`, `NOTIONS_CLES.md` § 8 |
| 10 | Go / no-go et roadmap | 2 | Checklist et verdict. Roadmap en 3 phases avec conditions de passage : expérimentation encadrée avec les IOA ; validation clinique et hébergement HDS ; production (32B+, données réelles, intégration FHIR, montée en charge). Ordre de grandeur des coûts GPU | `GO_NO_GO.md`, énoncé (phase 3) |
| — | Références | 0,5 | Échelle FRENCH, ACS (sur-triage toléré), articles, cours | |

Total : 18 à 19 pages.

## Choix éditoriaux

- **Les chiffres du modèle seul sont toujours donnés à côté** de ceux du système complet, comme
  dans les docs. On ne masque pas que ce sont les garde-fous qui tiennent la sécurité.
- **Les échecs ont leur propre section** (7), pas une note de bas de page. C'est ce que la
  discussion de la soutenance va chercher.
- **Pas de code dans le rapport**, sauf la formule du DPO. Le détail reste dans le dépôt, avec
  des renvois.
- **Trois figures et deux schémas au plus.** Les tableaux portent le reste.

## Ordre de rédaction

1. Sections 3 à 8 : elles reprennent des docs existantes et se condensent vite.
2. Figures et schémas.
3. Sections 9 et 10, puis 1 et 2.
4. Synthèse en dernier, une fois les chiffres figés.
5. Relecture pour la longueur, compilation, contrôle du nombre de pages.
