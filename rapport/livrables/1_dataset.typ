#import "fiche.typ": fiche, note

#show: fiche.with(
  numero: "1",
  titre: "Dataset médical bilingue",
  sous-titre: "Format Hugging Face Datasets / JSONL, versionné sur un dépôt",
)

== Où le trouver
#table(columns: (auto, 1fr),
  [Élément], [Valeur],
  [Dépôt], [Hugging Face, dataset `lcamara/triage-chsa` (privé, accès sur demande)],
  [Révision], [`7dffce7d0494094a0197f67a3085d8823fdb6d9f` (celle des entraînements et de l'évaluation)],
  [Copie jointe], [dossier `donnees/` de ce livrable : les mêmes fichiers JSONL, la fiche du dataset (`README.md`) et le journal de construction (`build_log.json`)],
  [Code], [`scripts/download_data.py`, `scripts/build_dataset.py`, `src/triage/data/` ; documentation `docs/DONNEES.md` et `docs/RGPD.md` du dépôt GitHub],
)

```python
from datasets import load_dataset
sft = load_dataset("lcamara/triage-chsa", "sft", revision="7dffce7d0494094a0197f67a3085d8823fdb6d9f")
dpo = load_dataset("lcamara/triage-chsa", "dpo", revision="7dffce7d0494094a0197f67a3085d8823fdb6d9f")
```

== Composition
#table(columns: (1fr, auto, auto, auto),
  align: (left, right, right, right),
  [Jeu], [Entraînement], [Validation], [Test],
  [SFT : QCM MediQAl et FrenchMedMCQA (FR)], [2 300], [200], [600],
  [SFT : questions-réponses MedQuAD (EN)], [1 200], [98], [150],
  [SFT : vignettes de triage FRENCH (FR, synthétiques)], [1 565], [150], [200],
  [*Total SFT* (`sft/*.jsonl`)], [*5 065*], [*448*], [*950*],
  [DPO : paires UltraMedical (EN)], [2 000], [100], [777],
  [DPO : paires de triage (FR, synthétiques)], [300], [50], [100],
  [*Total DPO* (`dpo/*.jsonl`)], [*2 300*], [*150*], [*877*],
)

*Schéma.* SFT : `id`, `prompt` (messages système et utilisateur), `completion` (réponse de
l'assistant), `metadata`. DPO : `id`, `prompt`, `chosen`, `rejected`, `metadata`. Les
métadonnées donnent la source et son identifiant, la licence, la langue, la tâche, le niveau
de confiance (`reference`, `human_preference`, `model_judged`, `synthetic_rules`), et pour les
vignettes le contexte clinique et le tri FRENCH attendu.

== Sources et licences
#table(columns: (auto, auto, auto, 1fr),
  [Source], [Révision], [Licence], [Usage],
  [MediQAl (`ANR-MALADES/MediQAl`)], [`5af3494`], [CC BY 4.0], [QCM de médecine, français],
  [FrenchMedMCQA (`qanastek/frenchmedmcqa`)], [`be9a03f`], [Apache 2.0], [QCM de pharmacie, français],
  [MedQuAD (`abachaa/MedQuAD`)], [`577bd37`], [CC BY 4.0], [questions-réponses, anglais],
  [UltraMedical-Preference (`TsinghuaC3I`)], [`761eb79`], [MIT], [paires de préférences, anglais],
  [Référentiel FRENCH (SFMU, v1.1, 2018)], [SHA-256 `2212e10…`], [usage pédagogique], [niveaux de tri des vignettes],
)

== Construction
Entièrement scriptée et reproductible (graine 42) : filtrage des réponses vides et trop
longues ; découpage selon les splits officiels (MedQuAD par document) ; jeux d'évaluation
construits d'abord ; retrait de toute question d'entraînement présente en validation ou en test
(74 MedQuAD, 215 UltraMedical, 48 vignettes) ; tirage stratifié ; désidentification ; journal
des comptages, empreintes, révisions et commit (`build_log.json`).

Aucune source ne contenant de décision de triage, 1 565 vignettes ont été générées à partir de
FRENCH (61 motifs, 193 critères, trois formes : note d'IOA, récit, dialogue), chaque niveau étant
vérifié contre le référentiel par un test. Les paires DPO de triage opposent la réponse au bon
niveau à la même réponse sous-triée d'une catégorie.

== Données personnelles
#note[Une partie d'UltraMedical (ChatDoctor) reprend de vrais messages de patients. Tous les
textes non synthétiques ont été désidentifiés avec Presidio (noms, téléphones, e-mails, IBAN
remplacés par une balise). Retirer les identifiants directs ne rend pas un texte anonyme : le
jeu reste une donnée personnelle. Il est publié en dépôt privé et ce dossier est remis pour la
seule évaluation du projet ; merci de ne pas le diffuser. Aucune donnée du CHSA n'a été
utilisée.]

*Limites.* Vignettes synthétiques, écrites par un seul auteur, non validées par des soignants ;
paires UltraMedical jugées par un modèle (GPT-4). Détail dans le rapport (livrable 3, section 3).
