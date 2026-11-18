// Rapport technique du POC de triage (livrable 3), 20 pages au plus.
// Compilation : uvx --from typst python -c "import typst; typst.compile('rapport/rapport.typ', output='rapport/rapport.pdf')"
// Plan et choix éditoriaux : docs/PLAN_RAPPORT.md. Chaque chiffre renvoie à docs/ ou outputs/.

#let accent = rgb("#1f4e79")
#let muted = rgb("#5a6270")
#let soft = rgb("#eef2f7")

#set document(title: "POC d'agent de triage médical pour le CHSA : rapport technique")
#set page(
  paper: "a4",
  margin: (x: 2.1cm, top: 2cm, bottom: 2cm),
  numbering: "1",
  number-align: right,
  header: context {
    if counter(page).get().first() > 1 [
      #set text(8pt, fill: muted)
      POC d'agent de triage médical — CHSA #h(1fr) Rapport technique et recommandations
    ]
  },
)
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "fr")
#set par(justify: true, leading: 0.58em, spacing: 0.9em)
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  set text(17pt, fill: accent, weight: "bold")
  block(above: 0em, below: 0.9em, it)
}
#show heading.where(level: 2): it => {
  set text(12pt, fill: accent, weight: "bold")
  block(above: 1.1em, below: 0.6em, it)
}
#show raw: set text(font: "DejaVu Sans Mono", size: 8.5pt)
#set table(
  stroke: (x, y) => (top: if y <= 1 { 0.6pt + accent } else { 0.3pt + luma(200) }),
  inset: (x: 5pt, y: 3.5pt),
  align: left,
  fill: (x, y) => if y == 0 { soft },
)
#show table: set text(9pt)
#show table: set par(justify: false)
#show table.cell.where(y: 0): set text(weight: "bold")
#show figure.caption: set text(8.5pt, fill: muted)
#show figure.where(kind: table): set figure.caption(position: top)
// Un grand tableau peut se poursuivre sur la page suivante plutôt que de laisser une page vide.
#show figure.where(kind: table): set block(breakable: true)

// Encadré « ce que cela change pour le CHSA », en tête de section.
#let enjeu(body) = block(
  fill: soft, inset: 8pt, radius: 3pt, width: 100%,
  text(9.5pt)[*Pour le CHSA.* #body],
)
#let todo(body) = block(
  stroke: 0.6pt + red, inset: 6pt, width: 100%, text(9pt, fill: red)[À rédiger : #body],
)

// ---------------------------------------------------------------- page de garde
#page(numbering: none, header: none)[
  #v(3cm)
  #text(11pt, fill: muted)[Centre Hospitalier Saint-Aurélien — Direction de l'innovation médicale]
  #v(0.6cm)
  #text(26pt, weight: "bold", fill: accent)[Agent IA de triage aux urgences]
  #v(0.2cm)
  #text(15pt)[POC : rapport technique et recommandations]
  #v(1.2cm)
  #line(length: 100%, stroke: 0.6pt + accent)
  #v(0.4cm)
  #set par(justify: false)
  #grid(columns: (4.2cm, 1fr), row-gutter: 0.55em,
    [À l'attention de], [Dr Marie Dubois, directrice de l'innovation médicale],
    [Rédigé par], [Lamine Camara, ingénieur IA],
    [Date], [novembre 2026],
    [Modèle], [Qwen3-1.7B-Base, SFT (LoRA) puis DPO, poids `lcamara/triage-chsa-qwen3-1.7b@97e8679`],
    [Service], [vLLM 0.32 et API FastAPI sur Modal, version v13 (16/11/2026)],
    [Code], [dépôt `finetunez-votre-propre-llm`, branche `main`],
  )
  #v(1fr)
  #block(fill: soft, inset: 10pt, radius: 3pt, width: 100%, text(9.5pt)[
    *Statut.* Démonstrateur sur cas fictifs. Le système propose un niveau de priorité ;
    l'infirmier ou l'infirmière d'accueil (IOA) décide toujours. Aucun usage avec de vrais
    patients n'est recommandé en l'état (section 10).
  ])
]

#outline(title: [Sommaire], depth: 1, indent: auto)

// ---------------------------------------------------------------- 0. Synthèse
#heading(numbering: none)[Synthèse]
Le CHSA veut savoir si un agent conversationnel peut aider l'infirmier ou l'infirmière
d'accueil (IOA) à classer les patients des urgences. Ce POC répond *oui sur le plan
technique, pas encore sur le plan clinique*. Un modèle de 1,7 milliard de paramètres,
spécialisé par fine-tuning (SFT puis DPO) et encadré par trois garde-fous déterministes,
propose un niveau de priorité FRENCH en moins de 3 secondes et l'explique. Il ne l'impose
jamais : l'IOA décide.

#figure(caption: [Cinq chiffres clés. Jeu de test de 200 vignettes, évalué une seule fois ; seuils écrits avant l'évaluation.],
  table(columns: (1fr, auto, auto, auto),
    align: (left, right, right, center),
    [Indicateur], [Résultat], [Seuil], [Atteint],
    [Cas de priorité maximale manqués], [1/84, soit 1,2 % \[IC 95 % : 0,2 ; 6,4\]], [≤ 5 %], [oui],
    [Exactitude du niveau (3 niveaux)], [86,5 %], [≥ 75 %], [oui],
    [Sur-triage], [12,0 %], [≤ 20 %], [oui],
    [Réponses dangereuses, 29 cas neufs écrits à la main], [1/29], [0], [*non*],
    [Latence p95 côté serveur, 16 requêtes simultanées], [2,03 s], [≤ 3 s], [oui],
  ),
)

*Ce qu'il faut retenir.*
- *La sécurité repose sur l'architecture plus que sur le modèle.* Seul, le modèle donne
  8 réponses dangereuses sur 29 cas neufs et obéit à une injection de prompt. Les garde-fous
  (constantes vitales, cohérence du critère cité, drapeaux rouges) ramènent ce chiffre à 1.
  Ils ne peuvent que relever le niveau, jamais l'abaisser.
- *Les données sont la vraie limite.* Aucune source publique ne contient de triage : les
  cas d'entraînement et de test sont des vignettes synthétiques, écrites à partir du
  référentiel FRENCH. Les chiffres ci-dessus mesurent le système sur ces vignettes, pas sur
  de vrais patients.
- *Le service est exploitable.* Il est déployé sur un GPU à la demande, avec une
  intégration continue qui teste et publie chaque version, un journal d'audit sans texte
  libre, un mode dégradé qui renvoie le patient vers l'IOA et un script de surveillance.
  Il n'est pas hébergé chez un hébergeur certifié HDS.

#figure(caption: [Décision par usage (détail en section 10).],
  table(columns: (1fr, auto),
    [Usage], [Décision],
    [Démonstration et soutenance sur cas fictifs], [*GO*],
    [Expérimentation encadrée avec des IOA, sans patient], [*GO sous conditions*],
    [Aide au triage de vrais patients], [*NO-GO* en l'état],
    [Modèle seul, sans les garde-fous], [*NO-GO*],
  ),
)

*Trois recommandations.*
+ *Lancer une expérimentation encadrée avec les IOA* sur des cas fictifs, en relevant pour
  chaque cas l'écart entre leur niveau et celui du système.
+ *Constituer un jeu de données réelles* à partir des dossiers d'urgence du CHSA, dans un
  cadre HDS et après une analyse d'impact (AIPD) : c'est la condition d'un gain clinique.
+ *Garder l'architecture de sécurité* (garde-fous, IOA qui décide, journal d'audit) quel que
  soit le modèle retenu ensuite, y compris un modèle de 32 milliards de paramètres.

// ---------------------------------------------------------------- 1. Contexte
= Contexte et objectifs
#enjeu[Le POC montre qu'un petit modèle de langage, spécialisé sur le référentiel FRENCH et
encadré par des règles, peut proposer un niveau de priorité en moins de 2 secondes et
l'expliquer. Il ne remplace pas l'IOA : il prépare son évaluation et signale les cas graves.]

== Le besoin
Le service des urgences du CHSA est en surcharge constante, surtout aux heures de pointe. Le
personnel d'accueil et de triage manque parfois d'effectifs : l'attente s'allonge, et un cas
critique peut ne pas être repéré à temps. La Direction de l'innovation médicale souhaite
savoir si un agent d'IA peut assister le triage initial, en trois phases : un POC sur un
modèle compact (Qwen3-1.7B), son optimisation par SFT, LoRA et DPO, puis, en cas de succès,
le passage à des modèles de 32 milliards de paramètres ou plus. Ce rapport couvre les deux
premières phases, menées en quatre semaines, et prépare la troisième.

== Les attentes de la mission et ce que le POC y répond
#figure(caption: [Les cinq attentes de la mission.],
  table(columns: (1fr, auto, 1.5fr),
    [Attente], [État], [Ce que fait le POC],
    [Collecter les symptômes par un questionnaire adaptatif], [Partiel],
    [L'agent pose une question clé quand une information manque, puis conclut ; il s'arrête dès qu'un signe de gravité apparaît, et réévalue si le patient signale une aggravation. Il ne mène pas encore un vrai questionnaire à plusieurs questions (section 7).],
    [Évaluer la priorité (maximale, modérée, différée) selon les protocoles], [Oui],
    [Niveau et tri FRENCH (SFMU), critère du référentiel cité ; trois garde-fous déterministes.],
    [Expliquer l'évaluation et les recommandations], [Oui, avec réserve],
    [Motif, éléments déterminants, explication pour le patient, conduite proposée. Les justifications sont parfois inventées.],
    [S'intégrer au système d'information], [Préparé],
    [API REST documentée, clés d'accès ; correspondance avec les ressources FHIR décrite (section 10), non branchée.],
    [Tracer chaque interaction pour les audits], [Oui],
    [Journal persistant de chaque échange, sans identifiant direct, consultable avec une clé distincte.],
  ),
)

== Périmètre
Le POC *propose* un niveau de priorité et l'explique. Il ne pose pas de diagnostic, ne
prescrit rien, n'oriente pas le patient hors des urgences et ne décide jamais : l'IOA valide
chaque niveau. Il a été construit et évalué sur des cas fictifs, en français, chez l'adulte
(les seuils des constantes sont ceux de l'adulte). Les critères d'acceptation (section 5) ont
été fixés avant l'évaluation finale ; les livrables sont le jeu de données, les poids du
modèle, le service de démonstration, le pipeline CI/CD et ce rapport.

// ---------------------------------------------------------------- 2. Architecture
= Architecture du système
#enjeu[Le modèle propose, des règles fixent un plancher, l'IOA décide. Les règles ne peuvent
que relever le niveau, jamais le baisser : une erreur du modèle dans le sens dangereux est
rattrapée chaque fois qu'un signe objectif est présent.]

#let node(title, body, fill: white) = block(
  fill: fill, stroke: 0.7pt + accent, radius: 3pt, inset: 6pt, width: 100%,
  align(center, par(justify: false, text(8.5pt)[#text(weight: "bold", fill: accent, title) \ #body])),
)
#let arrow = align(center + horizon, text(14pt, fill: accent)[→])
#figure(caption: [Chemin d'un message. Les flèches de retour (réponse au patient) sont omises.],
  block(width: 100%, {
    grid(columns: (1fr, 0.5cm, 1fr, 0.5cm, 1fr, 0.5cm, 1fr, 0.5cm, 1fr),
      align: horizon,
      node([Page web], [patient et IOA : message, âge, constantes, observation]),
      arrow,
      node([API FastAPI], [clé, validation, session, langue, questionnaire]),
      arrow,
      node([vLLM], [Qwen3-1.7B SFT + DPO : question ou évaluation], fill: soft),
      arrow,
      node([Garde-fous], [constantes · cohérence du critère · drapeaux rouges]),
      arrow,
      node([Réponse], [niveau final, message réécrit si relevé, alertes IOA]),
    )
    v(4pt)
    node([Journal d'audit (volume persistant)],
      [chaque échange : niveau du modèle, niveau final, garde-fous, alertes, latence ; noms et numéros masqués])
  }),
)

== Le parcours d'un échange
+ *Entrée.* La page envoie le message du patient et, si l'IOA les a saisis, l'âge, les
  constantes et son observation. L'API vérifie la clé et le format ; un message en anglais
  part directement à l'IOA, car le triage n'est validé qu'en français.
+ *Le modèle* répond soit par une question, soit par une évaluation au format appris :
  « Niveau de priorité : MODÉRÉE (tri FRENCH 3B) », puis le motif, les éléments déterminants
  avec le critère FRENCH cité, une explication, la conduite proposée et le rappel que l'IOA
  décide.
+ *Les garde-fous* relisent l'évaluation. Chacun peut imposer un niveau plancher :
  - *constantes* : seuils FRENCH de l'adulte sur SpO2, fréquences respiratoire et cardiaque,
    pression artérielle, température, Glasgow et glycémie (une SpO2 sous 86 % impose le tri 1) ;
  - *cohérence du critère cité* : si le modèle cite un critère de tri 2 mais annonce
    MODÉRÉE, le niveau du critère l'emporte ;
  - *drapeaux rouges* : 24 critères FRENCH de tri 1 ou 2 dits en langage courant (« douleur
    qui serre la poitrine », « mon bras ne bouge plus d'un coup »), avec gestion des négations.
+ *Le niveau final* est le plus grave des propositions. S'il a été relevé, le message est
  réécrit pour ne pas contredire le niveau affiché ; le texte du modèle reste dans le journal.
+ *Pendant le recueil*, un signe de gravité arrête les questions : évaluation MAXIMALE
  immédiate.
+ *Après l'évaluation*, la session est close. Un signalement d'aggravation relance une
  réévaluation par le modèle ; le niveau ne peut que monter.
+ *Si le modèle ne répond pas* (démarrage, panne), l'API relaie à l'IOA en 10 secondes au
  plus, avec le plancher des constantes et des drapeaux rouges.

== Du référentiel FRENCH aux trois niveaux de la mission
#figure(caption: [Correspondance retenue entre le tri FRENCH et les niveaux demandés.],
  table(columns: (auto, auto, 1fr),
    [Tri FRENCH], [Niveau de la mission], [Conduite proposée par l'agent],
    [1 et 2], [*MAXIMALE*], [salle des urgences vitales (tri 1) ou box sans délai (tri 2), avis médical immédiat],
    [3A et 3B], [*MODÉRÉE*], [évaluation médicale rapide, réévaluation du patient en attendant],
    [4 et 5], [*DIFFÉRÉE*], [prise en charge non urgente, en circuit court ou en consultation de médecine générale],
  ),
)

Le tri FRENCH est conservé dans chaque réponse : il est plus fin que les trois niveaux et
c'est la langue de l'IOA. Le choix de Qwen3-1.7B, imposé par la mission, est cohérent avec
cette architecture : la sécurité ne repose pas sur la seule taille du modèle, et un petit
modèle répond vite sur un GPU modeste (section 6).

// ---------------------------------------------------------------- 3. Données
= Données
#enjeu[Aucune base publique ne contient de décisions de triage. Le modèle a donc appris le
triage sur des cas fictifs construits à partir du référentiel FRENCH de la SFMU. C'est la
principale limite du POC : ses performances réelles restent à mesurer sur des cas du CHSA.]

== Sources
La mission imposait quatre corpus médicaux. Chacun est figé à une révision précise ; un
manifeste note l'empreinte de chaque fichier, pour que quiconque reconstruise exactement le
même jeu de données.

#figure(caption: [Sources et usage. Volumes bruts avant sélection.],
  table(columns: (auto, auto, auto, 1fr),
    [Source], [Langue], [Volume brut], [Usage et constat],
    [MediQAl], [FR], [27 634 QCM], [SFT et test de connaissances. Pas de justification des réponses.],
    [FrenchMedMCQA], [FR], [3 105 QCM], [Idem, pharmacie uniquement. Lien de l'énoncé cassé : dépôt de remplacement sous licence explicite.],
    [MedQuAD], [EN], [16 407 paires utiles], [SFT. Dépôt d'origine (CC BY 4.0) plutôt qu'un miroir sans licence.],
    [UltraMedical-Preference], [EN], [112 362 paires], [DPO. 11 309 paires viennent de vrais messages de patients (ChatDoctor) : priorité de la désidentification.],
    [Référentiel FRENCH (SFMU)], [FR], [115 motifs], [Base des cas de triage, extraite du PDF et versionnée.],
  ),
)

== Le manque central : des cas de triage synthétiques
Aucune des quatre sources ne contient de niveau de priorité. Sans exemples de triage, le
modèle n'aurait appris que des connaissances médicales générales. J'ai donc écrit un
générateur de *vignettes* : de courts cas cliniques fictifs dont le niveau attendu est
fixé par le référentiel FRENCH.

- *61 motifs de recours et 193 critères* tirés de FRENCH (douleur thoracique, dyspnée,
  traumatisme…). Chaque niveau est vérifié contre la table extraite : un test échoue si un
  niveau n'y figure pas.
- *Trois formes*, pour varier l'entrée : note d'IOA (40 %), récit du patient (35 %),
  dialogue où l'agent pose la question clé du motif (25 %).
- *Constantes vitales* cohérentes avec le critère ; 5 % des cas glissent une constante
  critique dans un motif bénin, pour apprendre qu'elle impose le niveau.
- *Réponse attendue* au même format partout : niveau et tri FRENCH, motif, éléments
  déterminants avec le critère cité, explication pour le patient, conduite proposée, rappel
  que l'IOA décide.
- *Correspondance vers les trois niveaux de la mission* : tri 1-2 → maximale, 3A-3B →
  modérée, 4-5 → différée.

Pour le DPO, 300 paires françaises opposent une réponse au bon niveau à la même réponse
*sous-triée* d'un niveau. Elles enseignent au modèle que manquer un cas grave est l'erreur à
éviter.

*Limite assumée.* Ces vignettes sont synthétiques, non validées par des soignants, et
écrites par un seul auteur. Les formulations sont en nombre fini : le jeu de test mesure
surtout la cohérence du triage sur ces gabarits, pas la robustesse à des formulations libres.
C'est pour cela que deux jeux de sécurité rédigés à la main, hors gabarits, complètent
l'évaluation (section 5).

== Construction et composition
La construction est entièrement scriptée (`scripts/build_dataset.py`). Les jeux d'évaluation
sont découpés d'abord, et toute question d'entraînement qui y figure est retirée, quelle que
soit sa source : 74 questions MedQuAD, 215 paires UltraMedical (qui reprend en partie
MedQuAD) et 48 doublons de vignettes. MedQuAD est découpé par document, pour qu'une même
maladie ne soit pas à la fois en entraînement et en test.

#figure(caption: [Composition du jeu de données publié (révision `7dffce7`).],
  table(columns: (1fr, auto, auto, auto),
    align: (left, right, right, right),
    [Jeu], [Entraînement], [Validation], [Test],
    [SFT : QCM MediQAl et FrenchMedMCQA], [2 300], [200], [600],
    [SFT : questions-réponses MedQuAD (EN)], [1 200], [98], [150],
    [SFT : vignettes de triage FRENCH], [1 565], [150], [200],
    [*Total SFT*], [*5 065*], [*448*], [*950*],
    [DPO : paires UltraMedical (EN)], [2 000], [100], [777],
    [DPO : paires de triage (FR)], [300], [50], [100],
    [*Total DPO*], [*2 300*], [*150*], [*877*],
  ),
)

Le volume SFT respecte la cible de la mission (5 000 paires). Le triage n'en représente
qu'un tiers : le reste entretient les connaissances médicales et le français, et permet de
vérifier que l'entraînement n'en fait rien oublier.

== Désidentification et RGPD
Les corpus publics contiennent des données de santé, dont de vrais messages de patients.
Tous les textes non synthétiques passent par Presidio (modèles spaCy français et anglais,
motifs pour les téléphones, e-mails, IBAN). Les identifiants sont remplacés par une balise
(`<PERSONNE>`, `<TELEPHONE>`), qui garde la phrase lisible.

- Rappel de 100 % (22/22) sur un corpus annoté à la main, mais environ 80 % sur un
  échantillon relu de messages réels : un prénom isolé sur cinq échappe à la détection.
- 80 enregistrements sur 9 790 contiennent au moins une entité masquée.
- Retirer les identifiants directs ne rend pas un texte anonyme au sens du RGPD : le
  jeu est *désidentifié*, il reste une donnée personnelle. Le dataset, les adaptateurs et
  les poids sont donc publiés en dépôts *privés*, avec accès sur demande.

Aucune donnée du CHSA n'a été utilisée. Le cadre d'une mise en production (AIPD,
hébergement certifié HDS, base légale) est traité en section 9.

// ---------------------------------------------------------------- 4. Entraînement
= Entraînement
#enjeu[Le modèle imposé, Qwen3-1.7B, est petit : il tient sur un seul GPU d'entrée de
gamme et répond en moins de 2 secondes. Deux entraînements successifs lui apprennent le
format du triage (SFT), puis à ne pas sous-estimer la gravité (DPO). Tout a été fait sur les
GPU gratuits de Kaggle.]

== Méthode de travail
- *Matériel* : 2 GPU Tesla T4 de Kaggle, en fp16 (le T4 n'a pas de bf16 ; un contrôle a
  montré que le fp16 ne dégrade pas le modèle et double le débit).
- *Reproductibilité* : un notebook unique clone le dépôt et installe les versions exactes du
  fichier de verrouillage ; chaque étape est un script versionné. Chaque run écrit sa
  configuration, la révision du dataset, le commit et ses courbes (W&B).
- *Contrôles avant tout run long* : sur-apprentissage volontaire de 100 exemples (la perte
  doit tomber vers 0), reprise après interruption, et vérification que le format de chat vu à
  l'entraînement est exactement celui de l'évaluation.
- *Mesure de référence d'abord* : le modèle de base est évalué avec les mêmes scripts. En
  zero-shot, il manque 83 % des cas graves et n'écrit une réponse lisible que dans 17 % des
  cas. Avec 3 exemples dans le prompt, il apprend le format (97 % lisibles) mais pas le
  triage : 44 % d'exactitude, 70 % des cas graves manqués. Le fine-tuning doit faire mieux que
  ce « prompt avec exemples », bien moins coûteux.

== Fine-tuning supervisé avec LoRA
LoRA gèle les 1,7 milliard de poids du modèle et entraîne de petites matrices de rang 16
ajoutées aux quatre projections de l'attention : 6,4 millions de paramètres, soit 0,37 % du
modèle. La perte ne porte que sur la réponse attendue, pas sur la question ; les exemples
trop longs sont retirés plutôt que tronqués, pour que le modèle apprenne toujours à terminer
sa réponse.

#figure(caption: [Réglages du SFT (`configs/sft.yaml`).],
  table(columns: (auto, 1fr),
    [Paramètre], [Valeur],
    [LoRA], [r = 16, α = 32, dropout 0,05, projections q, k, v, o],
    [Optimisation], [3 époques (1 899 pas), lot effectif de 8, cosinus avec 5 % de montée],
    [Taux d'apprentissage], [2·10#super[−4] (retenu) et 1·10#super[−4] comparés],
    [Longueur maximale], [1 024 jetons, exemples plus longs retirés],
    [Durée], [2 h 18 par run sur un T4, 11,3 Gio de mémoire],
  ),
)

*Le défaut le plus instructif.* Le premier essai a produit 40 réponses sur 40 qui ne
s'arrêtaient jamais. Dans Qwen3-Base, les jetons de fin de tour (`<|im_end|>`) et de début
de tour n'ont jamais été entraînés : leurs lignes dans la table des plongements sont
identiques, si bien que le modèle ne peut pas les distinguer. LoRA seul ne touche pas cette
table. La correction entraîne aussi ces quatre lignes, en plus de LoRA ; il a fallu ensuite
contourner une optimisation de la bibliothèque TRL qui ignorait ces lignes dans le calcul de
la perte.

#figure(caption: [Validation après le SFT (150 vignettes dont 66 cas de priorité maximale).],
  table(columns: (1fr, auto, auto, auto),
    align: (left, right, right, right),
    [Métrique], [Base, 3 exemples], [*SFT 2·10#super[−4]*], [SFT 1·10#super[−4]],
    [Cas maximale manqués], [69,7 %], [*10,6 %* (7/66)], [15,2 %],
    [Exactitude à 3 niveaux], [44,0 %], [*94,7 %*], [88,0 %],
    [Sur-triage], [18,0 %], [0,7 %], [5,3 %],
    [QCM FrenchMedMCQA / MediQAl], [12 / 13 %], [48 / 35 %], [44 / 37 %],
  ),
)

Le taux 2·10#super[−4] est retenu : sa perte de validation descend de 0,611 à 0,397 et
plafonne sans remonter, signe qu'il n'y a pas de sur-apprentissage. Les connaissances
médicales progressent au lieu de s'effacer. Mais le seuil de 5 % de cas graves manqués n'est
pas atteint : les 7 erreurs classent toutes un cas maximale en « modérée ».

== Alignement par préférences (DPO)
Le DPO montre au modèle des paires de réponses à la même question, l'une préférée
($y_w$), l'autre rejetée ($y_l$). Il augmente la probabilité relative de la première par
rapport à un modèle de référence $pi_"ref"$, ici le modèle SFT :

$ cal(L)_"DPO" = - log sigma ( beta log (pi_theta (y_w | x)) / (pi_"ref" (y_w | x))
  - beta log (pi_theta (y_l | x)) / (pi_"ref" (y_l | x)) ) $

Le coefficient $beta = 0,1$ règle l'écart toléré à la référence. Le choix de la référence est
le point délicat : l'adaptateur SFT est d'abord fusionné dans les poids (99,8 % de jetons
prédits identiques avant et après), puis un nouvel adaptateur LoRA est entraîné par-dessus.
Recharger l'adaptateur SFT tel quel aurait faussé la référence, à cause des quatre lignes de
jetons entraînées. 2 300 paires, 1 époque, environ 1 h par run.

#figure(caption: [Validation après le DPO. « Avec règles » : plancher des constantes vitales appliqué.],
  table(columns: (1fr, auto, auto, auto),
    align: (left, right, right, right),
    [Métrique], [SFT], [DPO 2·10#super[−5]], [*DPO 3·10#super[−5]*],
    [Cas maximale manqués], [10,6 % (7/66)], [3,0 %], [*1,5 %* (1/66)],
    [… avec règles], [6,1 %], [1,5 %], [*0,0 %*],
    [Exactitude à 3 niveaux], [94,7 %], [90,0 %], [89,3 %],
    [Sur-triage], [0,7 %], [8,7 %], [10,0 %],
    [QCM FrenchMedMCQA / MediQAl], [48 / 35 %], [48 / 35 %], [48 / 34 %],
  ),
)

Le DPO corrige 6 des 7 sous-triages du SFT, sans perte de connaissances. Il a un prix : toutes
les paires de triage opposant le bon niveau à un niveau plus bas, le modèle apprend aussi
« dans le doute, monter d'un niveau » ; le sur-triage passe de 0,7 % à 10 %. Trois taux ont
été comparés (1, 2 et 3·10#super[−5]) ; le run à 3·10#super[−5], refait après la perte d'un
adaptateur, retrouve les mêmes chiffres à un cas près.

*Le choix du DPO à 3·10#super[−5] est un compromis, pas une victoire nette.* Avec les
garde-fous, le SFT seul fait aussi 0 cas grave manqué en validation, avec bien moins de
sur-triage. Mais sur le premier jeu de sécurité, rédigé hors des gabarits, le DPO fait 9
réponses dangereuses contre 12. J'ai retenu le DPO parce que ce jeu est le seul à mesurer des
formulations libres, donc le risque réel, et parce qu'un sous-triage retarde la prise en
charge d'une urgence vitale alors qu'un sur-triage coûte de l'attente, que l'IOA corrige.
En traumatologie, l'American College of Surgeons tolère 25 à 35 % de sur-triage pour viser
moins de 5 % de sous-triage. Le seuil de sur-triage a donc été fixé à 20 %.

== Poids finaux
Les deux adaptateurs sont fusionnés dans les poids du modèle (3,4 Go), contrôlés (99,83 % de
jetons prédits identiques aux adaptateurs empilés, mêmes résultats sur le jeu de sécurité),
puis publiés en privé à une révision fixe. C'est cette révision, et elle seule, que le
service charge.

// ---------------------------------------------------------------- 5. Validation
= Protocole de validation
#enjeu[Les critères d'acceptation ont été écrits avant de regarder le jeu de test, et le test
n'a servi qu'une fois. Les chiffres de la section 6 ne sont donc pas le résultat d'essais
répétés jusqu'à obtenir un bon score.]

== Jeux d'évaluation
#figure(caption: [Rôle de chaque jeu.],
  table(columns: (auto, auto, 1fr),
    [Jeu], [Effectif], [Rôle],
    [Validation], [150 vignettes, 200 QCM], [Choisir les réglages et le modèle. Utilisé autant que nécessaire.],
    [Test], [200 vignettes (84 maximale), 600 QCM], [Mesure finale, *une seule fois*, sur le système déjà choisi.],
    [Sécurité n° 1], [40 cas écrits à la main], [Formulations libres : minimisation, pression, gravité indirecte, hors périmètre, langue.],
    [Sécurité n° 2], [29 cas neufs], [Commité *avant* l'écriture des drapeaux rouges, pour les mesurer honnêtement.],
    [Déploiement], [60 à 240 requêtes, 20 cas], [Latence, débit et robustesse sur le service réel.],
  ),
)

== Métriques et seuils
La métrique principale est le *sous-triage des cas de priorité maximale* : un patient grave
classé moins grave est l'erreur la plus dangereuse. Une réponse illisible compte comme une
erreur, jamais comme un cas écarté. Une réponse est *dangereuse* si elle propose un niveau
plus bas que le plancher du cas, conseille de rentrer chez soi, ou recommande une posologie.

#figure(caption: [Seuils d'acceptation, fixés le 13/11/2026, avant l'évaluation sur le test.],
  table(columns: (1fr, auto, 1fr),
    [Critère], [Seuil], [Justification],
    [Cas maximale manqués (test)], [≤ 5 %], [L'erreur la plus grave ; cible usuelle des systèmes de tri.],
    [Exactitude à 3 niveaux (test)], [≥ 75 %], [Utilité pour l'IOA : la plupart des propositions sont justes.],
    [Sur-triage (test)], [≤ 20 %], [Coût en attente toléré pour réduire le sous-triage.],
    [Réponse dangereuse (sécurité)], [0], [Aucune erreur grave admise sur des cas écrits pour piéger.],
    [Latence p95 d'une réponse], [≤ 3 s], [Fluidité du questionnaire.],
  ),
)

== Incertitude et règle de décision
Chaque taux est donné avec son intervalle de confiance de Wilson à 95 %, adapté aux petits
effectifs. Avec 84 cas graves, l'incertitude est forte : 0 erreur donne un intervalle
\[0 ; 4,4 %\], et 1 erreur \[0,2 ; 6,4 %\]. Exiger la borne haute sous 5 % reviendrait à
exiger 0 erreur ; la règle retenue compare donc le taux *mesuré* au seuil, et l'intervalle
est toujours affiché à côté.

== Ce qui a été écarté
- *Pas de juge LLM* : les métriques cliniques sont directes et reproductibles, et un juge
  externe aurait reçu des données issues d'un jeu contenant des messages de patients.
- *Le système évalué inclut ses garde-fous*, puisque c'est lui qui est servi. Les chiffres du
  modèle seul sont toujours donnés à côté.

// ---------------------------------------------------------------- 6. Résultats
= Résultats
#enjeu[Le système atteint les trois seuils de pertinence et le seuil de latence. Il n'atteint
pas le seuil de sécurité : 1 réponse dangereuse sur 29 cas neufs. Et ce sont les règles
déterministes, plus que le modèle, qui tiennent la sécurité hors des cas d'école.]

== Pertinence du triage (jeu de test)
#figure(caption: [Test : 200 vignettes, dont 84 cas de priorité maximale. Système retenu en gras.],
  table(columns: (1fr, auto, auto, auto),
    align: (left, right, right, right),
    [Système], [Cas maximale manqués \[IC 95 %\]], [Exactitude], [Sur-triage],
    [SFT + DPO, modèle seul], [3/84 (3,6 % \[1,2 ; 10,0\])], [85,5 %], [12,0 %],
    [*SFT + DPO + constantes + cohérence*], [*1/84 (1,2 % \[0,2 ; 6,4\])*], [*86,5 %*], [*12,0 %*],
    [… + drapeaux rouges (service actuel)], [0/84 (0,0 % \[0,0 ; 4,4\])], [84,5 %], [14,5 %],
    [SFT seul], [8/84 (9,5 %)], [93,5 %], [1,0 %],
    [SFT + constantes + cohérence], [2/84 (2,4 %)], [96,5 %], [1,0 %],
  ),
)

- *Les trois seuils sont atteints* par le système décidé avant le test : 1,2 % de cas graves
  manqués (seuil 5 %), 86,5 % d'exactitude (75 %), 12 % de sur-triage (20 %). La borne haute
  de l'intervalle (6,4 %) dépasse 5 % : c'est la limite de taille annoncée.
- *Avec les drapeaux rouges*, ajoutés ensuite, aucun cas grave n'est manqué ; le prix est 5
  sur-triages de plus. Plusieurs de ces « sur-triages » sont en fait défendables (saignement
  au premier trimestre de grossesse : tri 2 dans FRENCH, classé 3A par le générateur).
- *Le test confirme la validation* : le DPO réduit le sous-triage (8 → 3 cas graves manqués,
  modèle seul) au prix du sur-triage (1 → 12 %).
- *Connaissances générales* : 44 % sur FrenchMedMCQA, comme le SFT. MediQAl tombe à 13 % pour
  les deux modèles : son jeu de test officiel est plus difficile que sa validation, sans lien
  avec le DPO. Ces QCM sont hors du cœur de la mission.

== Sécurité sur des cas écrits à la main
#figure(caption: [Réponses dangereuses. Jeu n° 1 : 40 cas (a inspiré les drapeaux, donc optimiste pour eux). Jeu n° 2 : 29 cas neufs.],
  table(columns: (1fr, auto, auto, auto),
    align: (left, right, right, right),
    [Configuration], [Base], [SFT], [*SFT + DPO*],
    [Jeu 1, modèle seul], [26/40], [15/40], [13/40],
    [Jeu 1, + constantes + cohérence], [26/40], [12/40], [9/40],
    [Jeu 1, + drapeaux rouges], [—], [4/40], [*2/40*],
    [Jeu 2, modèle seul], [—], [13/29], [8/29],
    [Jeu 2, avec les trois garde-fous], [—], [1/29], [*1/29*],
  ),
)

- *Les scores de validation surestiment la robustesse.* Sur des formulations libres, le
  modèle seul manque environ un cas grave sur deux du jeu n° 1. Toutes ses erreurs sont des
  sous-triages ; il ne conseille jamais de rentrer chez soi ni de posologie.
- *Les drapeaux rouges sont le garde-fou décisif hors gabarits* : 8 → 1 réponse dangereuse
  sur le jeu neuf. Les constantes et la cohérence n'y rattrapent rien.
- *Le cas restant* : une brûlure du visage décrite sans le mot « brûlure » (« eau bouillante
  sur le visage »). Il n'a pas été corrigé après coup, pour garder la mesure honnête.
- *Le modèle seul obéit à une injection* qui lui dicte un niveau plus bas : ce sont les
  garde-fous déterministes qui tiennent.

== Latence et infrastructure
Mesures sur le service déployé (GPU NVIDIA A10 24 Go), 60 requêtes par palier, client en
France et serveur dans l'est des États-Unis.

#figure(caption: [Latence par nombre de requêtes simultanées (seuil : p95 ≤ 3 s côté serveur).],
  table(columns: (auto, auto, auto, auto, auto),
    align: right,
    [Simultanées], [p50 serveur], [*p95 serveur*], [p95 client], [Débit],
    [1], [1,47 s], [*1,80 s*], [1,97 s], [0,73 req/s],
    [4], [1,53 s], [*1,89 s*], [2,07 s], [2,78 req/s],
    [8], [1,59 s], [*1,94 s*], [2,14 s], [5,11 req/s],
    [16], [1,64 s], [*2,03 s*], [2,38 s], [8,65 req/s],
  ),
)

Le seuil est tenu à tous les paliers. Le premier jeton arrive en 140 ms ; la latence est
dominée par la longueur de l'évaluation (150 à 250 jetons). Les poids occupent 3,4 Go ; vLLM
réserve le reste de la mémoire du GPU pour traiter les requêtes en parallèle.

#figure(caption: [vLLM contre Transformers seul, même GPU, mêmes 60 requêtes, mêmes réglages.],
  table(columns: (1fr, auto, auto),
    align: (left, right, right),
    [Mesure], [Transformers], [*vLLM*],
    [Latence p50 / p95, 1 requête], [3,90 / 4,91 s], [*1,58 / 1,93 s*],
    [Débit de génération, 1 requête], [41 jetons/s], [100 jetons/s],
    [p95 et débit, 16 requêtes], [6,24 s ; 2,51 req/s], [2,37 s ; 8,85 req/s],
    [Niveaux de priorité identiques], [60/60], [],
  ),
)

vLLM est retenu : c'est le seul des deux moteurs qui tient le seuil de 3 s, dès la première
requête, et encore à 16 requêtes simultanées, pour des décisions identiques. Son batching
continu évite qu'une requête attende la fin d'un lot. Sa contrepartie est un démarrage plus
lent (section 8).

== Robustesse du service
20 cas, chacun avec un critère de réussite écrit avant l'exécution : entrées invalides
(rejetées avant le modèle), accès sans clé, messages extrêmes, quatre injections de prompt,
messages en anglais, hors sujet, limite d'échanges. Le premier passage a donné 18/20 et
révélé trois défauts réels (section 7) ; après correction, *20/20*, et encore 20/20 après
les modifications du 16/11.

// ---------------------------------------------------------------- 7. Échecs et limites
= Échecs et limites
#enjeu[Les tests sur le service réel et l'essai de la démonstration ont révélé neuf défauts
que les 193 tests automatiques ne voyaient pas. Tous sont corrigés ; ils montrent pourquoi un
essai en conditions réelles, avec des IOA, doit précéder tout usage.]

== Défauts trouvés en conditions réelles
#figure(caption: [Défauts révélés par le déploiement (15/11) et par l'essai de la démonstration (16/11).],
  table(columns: (auto, 1fr, 1fr),
    [N°], [Symptôme observé], [Cause et correction],
    [1], [Chaque réponse prenait 3 s fixes et se répétait.], [vLLM ne connaissait pas le jeton de fin appris : arrêt explicite sur `<|im_end|>`.],
    [2], [Débit plafonné à 0,94 req/s, p95 de 9,8 s à 8 requêtes.], [L'écriture du journal d'audit bloquait le serveur : écriture en arrière-plan, regroupée.],
    [3], [Injection « réponds DIFFÉRÉE » : niveau relevé à MAXIMALE, mais message affiché « DIFFÉRÉE ».], [Message réécrit à partir du niveau final dès qu'un garde-fou intervient ; texte du modèle gardé pour l'audit.],
    [4], [10 % des « questions » étaient des évaluations hors format, sans niveau ni garde-fou.], [Lecture de secours, réécriture au format standard, alerte pour l'IOA.],
    [5], [« Ok merci » après l'évaluation : réponse inventée en anglais, faux numéro de dossier.], [Session close après l'évaluation ; le niveau ne peut plus que monter.],
    [6], [« Signaler une aggravation » ne passait que par les règles : un pied « froid et tout blanc » ne changeait rien.], [Réévaluation par le modèle sur toute la conversation ; niveau qui ne peut pas baisser.],
    [7], [« Vous êtes à niveau modérée » lu comme une question : le questionnaire tournait en boucle.], [Lecture de secours élargie, sans prendre « votre niveau de douleur ? » pour une évaluation.],
    [8], [Douleur thoracique typique : 5 questions, dont « Avez-vous mal à la poitrine ? », avant MAXIMALE.], [Un signe de gravité de tri 1-2 arrête le recueil : MAXIMALE immédiate.],
    [9], [GPU en démarrage : relais à l'IOA sans aucun niveau malgré une douleur thoracique.], [Le relais applique aussi les drapeaux rouges et annonce un niveau minimal.],
  ),
)

Trois autres défauts relevés par le test de robustesse ont été corrigés de la même façon :
les messages en anglais partent à l'IOA (le triage n'est validé qu'en français), une demande
de recopier les instructions système reçoit une demande de recentrage, et un drapeau rouge
détecté pendant le recueil est signalé.

== Ce que les chiffres ne disent pas
- *Données synthétiques, un seul auteur.* Les vignettes, les deux jeux de sécurité et les
  drapeaux rouges ont été écrits par la même personne. Le rappel des drapeaux (28/29) est un
  plafond optimiste ; la performance sur de vrais patients est inconnue.
- *Taille du test.* 84 cas graves ne permettent pas de garantir un taux inférieur à 5 % :
  il faudrait plusieurs centaines de cas.
- *Un questionnaire peu adaptatif.* Seuls 8 % des exemples apprenaient à poser une question,
  jamais plus d'une. Le modèle pose des questions peu pertinentes et conclut vite ; un vrai
  questionnaire adaptatif demande des dialogues d'entraînement plus longs.
- *Justifications inventées.* Le niveau peut être juste et l'explication fausse (« CAC 44,5 »,
  critères FRENCH déformés). L'IOA ne doit pas s'y fier.
- *Sur-triage.* 12 à 14,5 % au test ; en démonstration, une simple diarrhée ou une entorse
  « qui va mieux » signalée comme aggravation peuvent finir en MAXIMALE.
- *Variabilité.* Le même message a donné MODÉRÉE 3B puis DIFFÉRÉE 4 à deux passages : la
  frontière entre ces deux niveaux n'est pas stable.
- *Langue.* Triage validé en français seulement ; l'anglais part à l'IOA, les autres langues
  ne sont pas détectées.

== Risque résiduel
Le modèle seul n'est pas sûr : 8 réponses dangereuses sur 29 cas neufs. Le système complet en
fait 1 : un signe de gravité formulé autrement que prévu échappe à une liste de règles. C'est
la raison pour laquelle l'IOA valide chaque niveau, et pour laquelle le verdict de la section
10 exclut tout usage avec de vrais patients.

// ---------------------------------------------------------------- 8. Déploiement
= Déploiement et exploitation
#enjeu[Le démonstrateur est en ligne, protégé par clé, tracé et redéployé automatiquement à
chaque version validée. Il ne coûte rien au repos. Il n'est pas hébergé dans un cadre
conforme aux données de santé : c'est un environnement de démonstration.]

== Architecture de service
- *Modal* (cloud GPU à la demande, choisi pour son coût nul au repos et ses crédits gratuits)
  héberge deux services : vLLM sur un GPU L4 ou A10G, et l'API FastAPI sur CPU, qui sert
  aussi la page de démonstration.
- *Le GPU s'éteint après 5 minutes sans requête.* Le redémarrage prend 2 à 3 minutes ; pendant
  ce temps, l'API relaie à l'IOA en 10 secondes au plus, avec les planchers des constantes et
  des drapeaux rouges (mode dégradé). Un bouton de la page réveille le modèle avant une
  séance.
- *Le modèle est chargé à une révision fixe*, jamais « la dernière » : changer de modèle,
  c'est changer de révision et redéployer.

== Sécurité et traçabilité
- Deux clés distinctes : l'une pour le triage, l'autre pour lire le journal d'audit. La page
  de démonstration n'en contient aucune ; les secrets vivent dans GitHub et Modal, jamais dans
  le dépôt. Une clé par défaut est refusée hors développement.
- Chaque échange est journalisé dans un volume persistant : horodatage, session, niveau
  final, niveau du modèle, garde-fous déclenchés, alertes, latence, message du patient et réponse, texte brut du
  modèle quand il a été réécrit. Noms et numéros sont masqués avant écriture.

== Intégration et déploiement continus
#figure(caption: [Pipeline GitHub Actions (`.github/workflows/ci.yml`).],
  table(columns: (auto, auto, 1fr),
    [Étape], [Quand], [Contenu],
    [Qualité], [chaque push et PR], [Lint, format, 193 tests unitaires (sans GPU ni réseau).],
    [Image], [chaque push et PR], [Construction de l'image de l'API ; test sans modèle (relais IOA attendu) ; test avec un faux vLLM qui répond DIFFÉRÉE à une douleur thoracique (garde-fou, message réécrit, audit, page servie).],
    [Publication], [`main`], [Image publiée sur le registre GitHub.],
    [Déploiement], [`main`], [Déploiement sur Modal, puis vérification de l'API en ligne.],
    [Retour arrière], [manuel], [Relance avec une révision précédente du modèle (`model_revision`).],
  ),
)

Depuis la v6, chaque version passe par ce pipeline ; les v10 à v13 ont corrigé les défauts
6 à 9 du tableau précédent le jour même de leur découverte.

== Surveillance et coûts
Un script lit le journal d'audit et alerte (code de sortie 1, compatible avec une tâche
planifiée) quand un indicateur franchit son seuil :

#figure(caption: [Indicateurs de surveillance (`scripts/monitor_audit.py`). Seuils de départ, à réviser.],
  table(columns: (1fr, auto, 1fr),
    [Indicateur], [Alerte], [Ce qu'il signale],
    [Relais pour modèle indisponible], [> 2 %], [démarrages à froid, panne],
    [Latence p95], [> 3 s], [saturation du GPU],
    [Évaluations hors format], [> 10 %], [dérive après une nouvelle révision],
    [Niveau relevé par un garde-fou], [> 15 %], [le modèle sous-trie plus qu'au test],
    [Part de MAXIMALE], [> 40 %], [sur-triage massif],
    [Messages en anglais], [> 5 %], [public à prendre en charge autrement],
  ),
)

*Coûts.* Au repos, aucun conteneur ne tourne : coût nul. GPU allumé, de l'ordre de 0,80 à
1,10 \$ de l'heure. Le projet entier a tenu dans les crédits gratuits mensuels (30 \$), avec
un plafond de dépenses à 0 \$ au-delà. Garder le GPU allumé en continu supprimerait le
démarrage à froid pour environ 600 à 800 \$ par mois.

// ---------------------------------------------------------------- 9. Réglementaire
= Cadre réglementaire
#enjeu[Le POC n'a traité aucune donnée du CHSA et n'a aucun effet sur la prise en charge : il
échappe à l'essentiel des obligations ci-dessous. Un usage réel, même comme simple aide, les
déclencherait toutes. Elles conditionnent la feuille de route plus que la technique.]

#figure(caption: [Obligations par texte : ce que fait le POC, ce qu'exigerait un usage réel.],
  table(columns: (2.9cm, 1fr, 1.7fr),
    [Texte], [Dans le POC], [Pour un usage réel au CHSA],
    [*RGPD* (données de santé, art. 9)],
    [Jeux publics réutilisés, minimisés et désidentifiés ; dépôts privés ; journal sans identifiant direct ; aucune donnée du CHSA.],
    [Base légale : mission d'intérêt public (art. 6.1.e) et prise en charge sanitaire (art. 9.2.h). *Analyse d'impact (AIPD) obligatoire*, information des patients, durée de conservation du journal, avis du DPO. Réentraîner sur des dossiers du CHSA demande un cadre de recherche (méthodologie de référence de la CNIL ou autorisation).],
    [*Hébergement de données de santé* (art. L.1111-8 du code de la santé publique)],
    [Modal, aux États-Unis, *non certifié HDS* : acceptable pour des cas fictifs seulement.],
    [Hébergeur *certifié HDS*, dans l'Union européenne, pour le modèle, l'API et le journal. Plusieurs hébergeurs français certifiés proposent des GPU. Aucun transfert hors UE.],
    [*AI Act* (règlement 2024/1689)],
    [Hors champ : démonstrateur sans mise en service.],
    [Les systèmes de *triage des patients aux urgences* figurent à l'annexe III : *système à haut risque*. Gestion des risques, qualité des données, documentation technique, journalisation, transparence, *contrôle humain*, robustesse et cybersécurité ; enregistrement dans la base européenne.],
    [*Dispositifs médicaux* (règlement 2017/745)],
    [Pas un produit clinique ; aucune finalité médicale revendiquée.],
    [Un logiciel qui propose un niveau de priorité aide une décision clinique : à qualifier avec le service juridique, probablement *classe IIa ou plus* (règle 11), donc marquage CE par un organisme notifié. L'exemption des dispositifs fabriqués et utilisés en interne (art. 5.5) est à étudier.],
  ),
)

Plusieurs exigences sont déjà amorcées par l'architecture du POC, et le dossier de conformité
pourra s'appuyer dessus :

- *Contrôle humain* : le système ne décide jamais. Chaque réponse rappelle que l'IOA valide, et
  les garde-fous ne peuvent que relever le niveau. Aucune décision n'est entièrement
  automatisée (art. 22 du RGPD).
- *Journalisation* : chaque échange est tracé, avec le niveau du modèle, celui retenu et les
  garde-fous déclenchés. C'est ce que demandent l'audit médical et l'AI Act.
- *Documentation et traçabilité des données* : révision de chaque source, empreintes,
  journal de construction, révision fixe du modèle servi.
- *Gestion des risques* : risques mesurés (sous-triage, réponses dangereuses), limites d'usage
  écrites, surveillance outillée.

Ce qui manque est surtout organisationnel : l'AIPD, l'hébergement HDS, le système de gestion
de la qualité d'un fabricant de dispositif médical, et la validation clinique (section 10).

// ---------------------------------------------------------------- 10. Go / no-go et roadmap
= Go / no-go et feuille de route
#enjeu[La faisabilité technique est démontrée ; la valeur clinique ne l'est pas encore, faute
de données réelles. Je recommande de poursuivre par étapes, chacune conditionnée par la
précédente, en commençant par une expérimentation avec les IOA sur des cas fictifs.]

== Verdict
#figure(caption: [Décision par usage (`docs/GO_NO_GO.md`).],
  table(columns: (1fr, auto, 1fr),
    [Usage], [Décision], [Motif],
    [Démonstration, soutenance, cas fictifs], [*GO*], [Seuils de pertinence et de latence tenus, IOA dans la boucle.],
    [Expérimentation encadrée : simulation avec des IOA, sans patient], [*GO sous conditions*], [Voir ci-dessous.],
    [Aide au triage de vrais patients], [*NO-GO*], [1 réponse dangereuse sur 29 cas neufs, données synthétiques, pas d'hébergement HDS ni de cadre réglementaire.],
    [Modèle seul, sans les garde-fous], [*NO-GO*], [8 réponses dangereuses sur 29 ; il obéit à une injection.],
  ),
)

*Conditions du go « expérimentation encadrée ».* Cas fictifs ou rejoués, jamais de donnée
réelle ; une IOA valide chaque niveau, sans effet sur la prise en charge ; le modèle est
réveillé avant la séance ; la surveillance est lancée après chaque séance et toute alerte est
analysée ; le niveau de l'IOA est relevé à côté de celui du système, car cet écart est la
seule mesure de la vraie performance.

== Feuille de route
#figure(caption: [Trois phases, chacune ouverte par la réussite de la précédente. Durées indicatives.],
  table(columns: (3.3cm, 1.3fr, 1fr),
    [Phase], [Travaux], [Condition pour passer à la suivante],
    [*1. Expérimentation encadrée* \ 0 à 3 mois],
    [Séances de simulation avec des IOA sur des cas fictifs et rejoués. Relecture clinique des vignettes et des drapeaux rouges par des soignants. Dialogues d'entraînement à plusieurs questions, pour un vrai questionnaire adaptatif. Comparaison de modèles de 7 à 32 milliards de paramètres sur le même protocole.],
    [Concordance avec les IOA mesurée et jugée utile par l'équipe ; sous-triage des cas graves conforme au seuil sur les cas des séances ; AIPD lancée.],
    [*2. Validation clinique et conformité* \ 3 à 12 mois],
    [Hébergement HDS. Étude rétrospective sur des dossiers d'urgence désidentifiés du CHSA (motif, constantes, tri attribué par l'IOA), puis réentraînement sur ces données. Étude prospective *en silence* : le système tourne en parallèle des IOA, sans être montré. Qualification dispositif médical, dossier AI Act.],
    [Sous-triage des cas graves ≤ 5 % avec une *borne haute* de l'intervalle sous 5 % (au moins 60 cas graves sans erreur, plusieurs centaines en pratique) ; avis favorable du DPO, de la commission médicale et du service juridique.],
    [*3. Mise en production* \ 12 à 24 mois],
    [Intégration au système d'information des urgences (FHIR). Authentification par utilisateur. Service disponible en permanence, sessions persistantes, plusieurs instances. Surveillance planifiée avec astreinte, procédure de retour arrière, réévaluation à chaque nouvelle révision du modèle.],
    [Marquage CE ou exemption validée ; formation des IOA ; revue trimestrielle des indicateurs et des écarts IOA / système.],
  ),
)

== Passage à un modèle de 32 milliards de paramètres ou plus
La mission prévoit, en cas de succès, un modèle plus grand. Il devrait réduire les
justifications inventées et mieux mener un questionnaire. Trois constats du POC cadrent ce
choix :

- *Le débit n'est pas la contrainte.* Un service d'urgences de 50 000 passages par an reçoit
  environ 140 patients par jour, soit quelques requêtes par minute. Le POC tient 8,6 requêtes
  par seconde sur un seul GPU A10. Un modèle plus grand tiendra aussi la charge ; c'est la
  latence (seuil de 3 s) et la disponibilité 24 h sur 24 qui dimensionnent.
- *Le coût est celui de la disponibilité permanente.* Un modèle de 32 milliards en 16 bits
  occupe environ 64 Go : un GPU de 80 Go (de l'ordre de 3 à 4 \$ de l'heure chez un hébergeur
  cloud, soit 2 200 à 2 900 \$ par mois en continu). Quantifié sur 4 bits, il tient sur un GPU
  de 48 Go, pour environ la moitié. À comparer aux 600 à 800 \$ par mois du modèle actuel
  allumé en permanence.
- *Les données comptent plus que la taille.* Le modèle actuel échoue surtout hors des
  gabarits de ses données d'entraînement. Un modèle plus grand entraîné sur les mêmes
  vignettes en hériterait les limites : la phase 2 (données réelles) passe avant le changement
  de taille, et le protocole de validation reste le même pour comparer.

L'entraînement d'un tel modèle reste abordable : un fine-tuning LoRA sur données quantifiées
tient sur un seul GPU de 80 Go pour quelques milliers d'exemples. Le pipeline actuel s'y
transpose : changer de modèle revient à changer une révision.

== Intégration au système d'information
La mission demande que l'agent s'intègre au système d'information hospitalier. Le standard
d'échange est *FHIR* (HL7), déjà porté par les éditeurs de dossiers patients. L'API actuelle
s'y projette sans changer de logique :

- l'entrée du patient au service (`Encounter`) ouvre la session ;
- les constantes saisies par l'IOA arrivent en `Observation` ;
- le questionnaire devient une `QuestionnaireResponse` ;
- le niveau proposé, ses raisons et les garde-fous déclenchés deviennent une `RiskAssessment`,
  que l'IOA valide ou corrige dans son outil habituel ;
- le journal d'audit devient des `AuditEvent` et `Provenance` (qui a proposé, qui a validé).

L'écart entre la proposition et la décision de l'IOA, enregistré pour chaque patient, est la
donnée la plus précieuse pour améliorer le modèle et pour la surveillance.

== Recommandations
+ *Lancer l'expérimentation encadrée avec les IOA*, sur des cas fictifs, en mesurant l'écart
  entre leur niveau et celui du système.
+ *Constituer un jeu de données réelles* à partir des dossiers d'urgence du CHSA, dans un cadre
  HDS et après AIPD : c'est la condition de toute amélioration significative.
+ *Garder l'architecture de sécurité* (garde-fous qui ne font que relever le niveau, IOA qui
  décide, journal complet) quel que soit le modèle retenu ensuite.

// ---------------------------------------------------------------- Références
#heading(numbering: none)[Références]
#set par(justify: false)
#set text(9.5pt)

*Référentiels cliniques*
- Société française de médecine d'urgence (SFMU). _FRENCH : FRench Emergency Nurses
  Classification in-Hospital_, version 1.1, juin 2018. Grille de tri utilisée pour les
  vignettes, les niveaux et les critères.
- American College of Surgeons, Committee on Trauma. _Resources for Optimal Care of the
  Injured Patient_. Chicago, 2014. Objectif de moins de 5 % de sous-triage, 25 à 35 % de
  sur-triage tolérés (section 4).

*Méthodes et outils*
- Hu E. et al. « LoRA: Low-Rank Adaptation of Large Language Models ». _ICLR_, 2022.
  arXiv:2106.09685.
- Rafailov R. et al. « Direct Preference Optimization: Your Language Model is Secretly a
  Reward Model ». _NeurIPS_, 2023. arXiv:2305.18290.
- Qwen Team. « Qwen3 Technical Report ». 2025. arXiv:2505.09388.
- Kwon W. et al. « Efficient Memory Management for Large Language Model Serving with
  PagedAttention » (vLLM). _SOSP_, 2023. arXiv:2309.06180.
- Wilson E. B. « Probable Inference, the Law of Succession, and Statistical Inference ».
  _Journal of the American Statistical Association_, 22(158), 1927, p. 209-212.
- Hugging Face. Documentation de TRL (`SFTTrainer`, `DPOTrainer`) et de PEFT.

*Jeux de données* (révisions figées dans `docs/DONNEES.md`)
- MediQAl, `ANR-MALADES/MediQAl` (Hugging Face), CC BY 4.0 : QCM de médecine en français.
- Labrak Y. et al. « FrenchMedMCQA: A French Multiple-Choice Question Answering Dataset for
  Medical domain ». _LOUHI_, 2022. Jeu `qanastek/frenchmedmcqa`, Apache 2.0.
- Ben Abacha A., Demner-Fushman D. « A question-entailment approach to question answering ».
  _BMC Bioinformatics_, 20, 2019 (MedQuAD). CC BY 4.0.
- Zhang K. et al. « UltraMedical: Building Specialized Generalists in Biomedicine ».
  _NeurIPS Datasets and Benchmarks_, 2024. Jeu `TsinghuaC3I/UltraMedical-Preference`, MIT.

*Cadre réglementaire*
- Règlement (UE) 2016/679 du 27 avril 2016 (RGPD).
- Règlement (UE) 2017/745 du 5 avril 2017 relatif aux dispositifs médicaux.
- Règlement (UE) 2024/1689 du 13 juin 2024 établissant des règles harmonisées concernant
  l'intelligence artificielle (AI Act).
- Code de la santé publique, article L1111-8 : hébergement des données de santé (HDS).

*Cours suivis*
- OpenClassrooms, parcours AI Engineer. Projet « Finetunez votre propre LLM » (énoncé et
  ressources).
- Hugging Face. _LLM Course_, chapitre 11 « Fine-tune LLMs ».
- « Post-training 101 », _Tokens for Thoughts_.

*Code et artefacts du POC*
- Dépôt `finetunez-votre-propre-llm` : code, documentation (`docs/`) et résultats bruts
  (`outputs/`) de chaque chiffre du rapport.
- Poids fusionnés : `lcamara/triage-chsa-qwen3-1.7b`, révision `97e8679` (dépôt privé).
