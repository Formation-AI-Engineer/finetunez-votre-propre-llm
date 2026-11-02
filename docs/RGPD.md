# Données de santé et RGPD : justification du traitement

Document du POC, à relire avec le délégué à la protection des données (DPO) du CHSA avant tout
usage de données réelles. Les références réglementaires sont à confirmer : elles n'ont pas été
vérifiées dans les textes officiels pour ce projet.

## 1. Périmètre

Le POC **n'utilise aucune donnée de patient du CHSA**. Il combine :

| Source | Nature | Données personnelles possibles |
|---|---|---|
| MediQAl, FrenchMedMCQA | Questions d'examens médicaux et de pharmacie | Cas cliniques pédagogiques, déjà pseudonymisés (« Monsieur R. ») |
| MedQuAD | Fiches de sites institutionnels américains (NIH) | Aucune attendue |
| UltraMedical-Preference | Questions médicales et réponses de modèles | **Oui** : la partie ChatDoctor reprend de vrais messages de patients |
| Vignettes FRENCH | Générées par règles | Aucune : patients fictifs |

Même publiques, ces données peuvent contenir des données de santé concernant des personnes
identifiables, qui sont une catégorie particulière au sens de l'article 9 du RGPD. Elles sont
donc traitées avec les mêmes précautions.

## 2. Base légale

- **POC** : réutilisation de jeux publics, sous licence ouverte, à des fins de recherche et de
  démonstration. Pistes : intérêt légitime (art. 6.1.f), et recherche scientifique pour les
  données de santé (art. 9.2.j), avec les garanties de l'article 89 (minimisation,
  pseudonymisation).
- **Production avec des données du CHSA** : mission d'intérêt public de l'hôpital (art. 6.1.e) et
  prise en charge sanitaire (art. 9.2.h). Ce cadre imposerait :
  - une analyse d'impact (AIPD), obligatoire pour un traitement de données de santé à grande
    échelle reposant sur une technologie innovante ;
  - l'information des patients ;
  - un hébergement certifié HDS ;
  - pour réentraîner le modèle sur des données réelles, un cadre de recherche en santé, comme une
    méthodologie de référence de la CNIL ou une autorisation.

## 3. Minimisation

- Seuls les textes utiles à l'apprentissage sont gardés : question, réponse, propositions.
- Les réponses de référence ChatDoctor (`golden_answer`) et les commentaires du juge
  (`feedback`) ne sont pas repris.
- Les métadonnées conservées décrivent la source, pas les personnes : identifiant d'origine,
  licence, type de question, modèle ayant produit la réponse.
- Les vignettes ne contiennent que les éléments cliniques nécessaires au tri.
- Seul un échantillon est retenu (environ 5 000 exemples SFT et 2 300 paires DPO), pas les
  sources complètes.

## 4. Anonymisation

### Méthode

Outil : Presidio (`src/triage/data/anonymize.py`), avec les modèles spaCy `fr_core_news_md` et
`en_core_web_md`, plus des reconnaisseurs à motifs. Tous les textes non synthétiques sont
traités : messages utilisateur et réponses, avant écriture.

| Entité | Détection | Remplacée par |
|---|---|---|
| Nom de personne | Modèle spaCy, retenu seulement dans un contexte de nom ; motif « civilité + Nom » | `<PERSONNE>` |
| Téléphone (France, Amérique du Nord) | Motifs explicites | `<TELEPHONE>` |
| E-mail, IBAN, carte bancaire, adresse IP | Reconnaisseurs Presidio | `<EMAIL>`, `<IBAN>`… |
| Numéro de sécurité sociale (NIR) | Motif explicite | `<NIR>` |
| Date explicite (jour, mois, année) | Motifs explicites | `<DATE>` |

**Volontairement conservés**

- **Lieux** : un séjour au Gabon ou une piqûre de tique dans le Connecticut sont des
  informations cliniques (exposition, épidémiologie). Aucune adresse postale n'a été observée
  dans les échantillons relus.
- **Durées relatives** (« depuis 3 jours ») et **âges** : indispensables au tri. Le détecteur
  DATE_TIME de Presidio, qui les masquerait, n'est pas utilisé.
- **Constantes et posologies** (« PA 130/80 », « 12,5 mg ») : vérifiées par les tests.

**Liste d'exclusion** (`configs/eponymes.txt`) : spaCy prend des éponymes pour des noms de
personnes. Testé sur ce projet : « Parkinson », « Guillain-Barré », « Crohn », mais aussi
« Doliprane » ou la classification « Ann Arbor ». La liste réunit environ 200 éponymes, noms de
germes et noms commerciaux de médicaments. Elle est complétée par une règle de contexte : un
nom précédé de « maladie de », « syndrome de », « score de »… n'est pas masqué.

**Contexte de nom obligatoire** : un premier build appliquait le NER de spaCy sans filtre. Il a
masqué 5 445 « personnes » dans le seul jeu d'entraînement SFT, presque toutes à tort :
- « Bonne » (de « Bonne réponse ») ;
- les lettres d'options de QCM (« D. Est ») ;
- des termes médicaux (« Splénomégalie », « Rhabdomyosarcoma », « ACTH », « NASH »).

Sur du texte médical, ce taux de faux positifs détruit l'information. Un nom détecté par spaCy
n'est donc retenu que s'il suit :
- une civilité (M., Mme, Dr, Pr…) ;
- une formule de présentation (« je m'appelle », « my name is », « I am »…) ;
- un lien de parenté (« mon mari », « my daughter »…).

Une signature est aussi reconnue : nom après « thanks » ou « merci », nom de deux mots ouvrant
la dernière phrase du message, ou nom suivi de « M.D. ». Les options de QCM (« - D. Prurit »), les
fins de question (« How to diagnose X ? ») et les mots « called » ou « named », qui introduisent
surtout des maladies, sont exclus après vérification sur les données. Une première version de la
règle de signature masquait des noms de maladies en fin de question MedQuAD. Un motif indépendant capte « civilité + Nom capitalisé ». Ce choix favorise la précision.
Il peut laisser passer un nom cité sans contexte, ce qui est rare dans des messages de patients,
où le nom suit presque toujours une présentation ou une civilité.

### Choix de la stratégie

| Stratégie | Résultat sur « Monsieur Jean Dupont, 06 12 34 56 78 » | Avantages | Inconvénients |
|---|---|---|---|
| `replace` (retenue) | « Monsieur `<PERSONNE>`, `<TELEPHONE>` » | Phrase lisible, type d'information conservé, longueur masquée | Le modèle apprend les balises : à reproduire telles quelles côté service |
| `mask` | « Monsieur \*\*\*\*\*\*\*\*\*\*\*, \*\*\*\*\*\*\*\*\*\*\*\*\*\* » | Simple | Révèle la longueur, bruit inutile pour le modèle |
| `redact` | « Monsieur , » | Rien ne subsiste | Phrases cassées, le modèle apprend du texte incohérent |
| `hash` | « Monsieur 3f2a… » | Lien possible entre occurrences | Inutile ici, et réversible par force brute sur des noms courants |

### Contrôle qualité

`scripts/audit_anonymization.py` mesure la détection sur un corpus annoté à la main
(`tests/fixtures/anonymization_gold.jsonl`). Ce corpus contient 40 phrases en français et en
anglais : 22 identifiants à masquer et 18 pièges médicaux. Le script produit aussi une revue des
entités détectées sur 300 prompts réels tirés au hasard par source (ChatDoctor, MediQAl,
MedQuAD), à relire à la main.

| Mesure | Résultat |
|---|---|
| Rappel sur le corpus annoté | 100 % (22/22) |
| Noms retenus sur 300 messages ChatDoctor réels (relecture manuelle) | 22, dont environ 18 vrais noms : précision d'environ 80 % |
| Faux positifs sur 400 textes MediQAl et 400 textes MedQuAD | 1 dans chaque source |
| Vrais noms manqués sur ce même échantillon | environ 5, des prénoms isolés sans contexte (« Eleni », « Amanda ») : rappel d'environ 80 % |
| Précision sur le corpus annoté | 100 % après ajout des médicaments et de « arbor » à la liste (91,7 % avant) |
| Entités masquées dans le dataset final (tous jeux) | 40 noms (`PERSON`), 33 noms précédés d'une civilité, 20 dates explicites, 5 téléphones, 2 e-mails, dans 80 enregistrements sur 9 790 |

**Limite principale** : environ un prénom isolé sur cinq échappe à la détection dans les messages
de patients. Le risque de ré-identification reste faible : il s'agit de prénoms seuls, tirés
d'un corpus déjà public. Ce ne serait pas acceptable sur des données réelles du CHSA. Pistes pour
la roadmap :
- un modèle de désidentification spécialisé (NER clinique, ou LLM local relu par sondage) ;
- une liste de prénoms ;
- une relecture humaine systématique.

**Autre limite** : le corpus annoté est petit et a servi à ajuster la liste d'exclusion. Ses scores
surestiment donc la performance réelle. La relecture des échantillons réels reste la mesure de
référence.

### Ce que l'anonymisation ne garantit pas

Retirer les identifiants directs ne rend pas un texte anonyme au sens du RGPD. Une combinaison
d'âge, de maladie rare et de lieu peut encore permettre une ré-identification. Le terme exact est
donc **désidentification** (ou pseudonymisation) : les données traitées restent des données
personnelles, et le dataset est publié **en privé**.

## 5. Traçabilité

| Élément | Où |
|---|---|
| Révision exacte et empreinte SHA-256 de chaque fichier source | `data/raw/MANIFEST.json` |
| Comptages à chaque étape, entités masquées, empreintes des fichiers produits, commit Git, graine | `data/processed/build_log.json` |
| Code de chaque transformation | `src/triage/data/`, `scripts/` (versionnés) |
| Provenance et niveau de confiance de chaque exemple | `metadata` de chaque enregistrement |

## 6. Conservation et accès

- Les sources brutes restent sur le poste de travail : elles sont exclues de Git.
- Le dataset produit est déposé sur Hugging Face en dépôt **privé**. Son ouverture sera décidée
  après la revue des licences : celle de MedQuAD (CC BY 4.0) impose l'attribution, et le
  référentiel FRENCH appartient à la SFMU.
- Le dataset est supprimé à la fin du projet si aucune suite n'est décidée.
- Les jetons d'accès restent dans `.env` ou dans les secrets des plateformes (Kaggle, GitHub,
  Modal), jamais dans le code.

## 7. Suite pour une mise en production

1. AIPD avec le DPO du CHSA ; hébergement HDS du modèle, de l'API et des journaux.
2. Journal d'audit des interactions, sans donnée identifiante en clair, avec une durée de
   conservation définie.
3. AI Act : un système d'aide au triage des patients aux urgences relèverait des systèmes à haut
   risque (annexe III). Il faudrait une gestion des risques, une documentation technique, une
   journalisation et un contrôle humain : ici, l'IOA décide toujours.
4. Statut de dispositif médical (règlement 2017/745) à qualifier avec le service juridique.
