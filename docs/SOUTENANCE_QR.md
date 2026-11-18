# Soutenance : réponses pour la discussion (10 minutes)

L'évaluateur joue la Dr Dubois, directrice de l'innovation médicale. Elle n'est pas
ingénieure : **réponse d'abord, en une phrase, puis le chiffre, puis la limite**. Chaque
réponse tient en 30 secondes ; le détail est dans le rapport (renvoi « R § n »).

Quatre thèmes annoncés par l'énoncé : méthodologie et validation, fine-tuning, passage à
l'échelle, déploiement. S'y ajoutent les questions cliniques et réglementaires, les plus
probables pour une directrice médicale.

## Les cinq chiffres à savoir par cœur

| Chiffre | Ce qu'il dit |
|---|---|
| **1,2 %** (1/84), IC 95 % [0,2 ; 6,4] | cas graves manqués au test, seuil 5 % |
| **86,5 %** | exactitude à 3 niveaux, seuil 75 % |
| **12 %** | sur-triage, seuil 20 % |
| **1/29** (modèle seul : 8/29) | réponses dangereuses sur les cas neufs, seuil 0 : **non atteint** |
| **2,03 s** | latence p95 à 16 requêtes simultanées, seuil 3 s |

---

## 1. Méthodologie et validation

**Comment savez-vous que vos chiffres ne sont pas arrangés ?**
Les seuils ont été écrits le 13/11, avant de regarder le test, et le test n'a servi qu'une
fois, sur le système déjà choisi en validation. Je n'ai pas ajouté de vignettes ni corrigé le
cas manqué après coup. Les chiffres du modèle seul sont toujours affichés à côté du système
complet. (R § 5)

**84 cas graves, est-ce suffisant ?**
Non, pour garantir moins de 5 % : avec 1 erreur, l'intervalle monte à 6,4 %. Il faudrait au
moins 60 cas graves sans aucune erreur, plusieurs centaines en pratique, donc des données
réelles. J'ai choisi de comparer le taux mesuré au seuil et d'afficher l'intervalle, plutôt
que d'exiger zéro erreur. (R § 5, § 7)

**Pourquoi des données synthétiques ?**
Aucune des quatre bases imposées ne contient de décision de triage : ce sont des QCM et des
questions-réponses. J'ai généré 1 565 vignettes à partir de FRENCH (61 motifs, 193 critères),
chaque niveau étant vérifié contre le référentiel par un test. Limite assumée : un seul
auteur, pas de relecture par des soignants. (R § 3)

**Le test ne ressemble-t-il pas trop à l'entraînement ?**
Si, c'est pour ça qu'il y a deux jeux de sécurité écrits à la main, hors gabarits. Le second
(29 cas) a été commité avant d'écrire les drapeaux rouges, pour les mesurer honnêtement.
C'est sur ce jeu que le seuil de sécurité n'est pas atteint. (R § 5, § 6)

**Pourquoi le sous-triage comme métrique principale ?**
Un patient grave classé moins grave peut voir sa prise en charge retardée ; un patient
sur-trié attend moins longtemps qu'il ne faudrait, et l'IOA corrige. Repère : l'American
College of Surgeons vise 5 % de sous-triage et juge acceptable 25 à 35 % de sur-triage. Mon
seuil de sur-triage est plus strict : 20 %.

**Y a-t-il une fuite entre entraînement et test ?**
Non vérifiable à 100 %, mais contrôlée : découpage d'abord, puis retrait de toute question
d'entraînement présente dans un jeu d'évaluation, quelle que soit la source (74 MedQuAD,
215 UltraMedical, 48 vignettes). MedQuAD est découpé par document. (R § 3)

**Pourquoi pas un LLM comme juge ?**
Les métriques cliniques sont directes (niveau juste ou non), donc reproductibles sans juge.
Et un juge externe aurait reçu des textes issus d'un jeu contenant de vrais messages de
patients. (R § 5)

## 2. Fine-tuning

**Pourquoi un modèle aussi petit (1,7 milliard) ?**
C'est le modèle imposé, et il permet de valider toute la chaîne à faible coût : 2 GPU T4
gratuits pour l'entraînement, un GPU d'entrée de gamme pour servir, moins de 2 s par
réponse. Le passage à 32 milliards est prévu dans la feuille de route, après les données
réelles.

**Pourquoi LoRA ?**
On n'entraîne que 0,37 % des poids (6,4 millions), ce qui tient sur un T4 de 16 Go en 2 h 18.
Le modèle de base reste intact, et l'adaptateur se fusionne ensuite dans les poids pour le
service.

**Pourquoi un DPO après le SFT ?**
Le SFT apprend le format et le triage, mais manquait encore 10,6 % des cas graves en
validation. Le DPO montre des paires « bon niveau / niveau trop bas » : 1,5 % de cas graves
manqués après. Il ne demande ni modèle de récompense ni apprentissage par renforcement.

**Le DPO a fait monter le sur-triage, est-ce un problème ?**
C'est le prix accepté, de 0,7 % à 10 % en validation (12 % au test). Toutes mes paires de
triage opposaient le bon niveau à un niveau plus bas : le modèle a aussi appris « dans le
doute, monter ». Correction possible : ajouter des paires contre le sur-triage, ou tirer les
paires des vraies erreurs du modèle.

**Quel a été le problème le plus difficile ?**
Au premier essai, 40 réponses sur 40 ne s'arrêtaient jamais. Dans Qwen3-Base, les jetons de
fin de tour n'ont jamais été entraînés : leurs plongements sont identiques. LoRA ne touche pas
cette table ; j'ai entraîné ces 4 lignes en plus, puis contourné une optimisation de TRL qui
les ignorait. Depuis, un contrôle du format précède tout run GPU. (R § 4)

**Le modèle a-t-il perdu ses connaissances médicales ?**
Non : 44 % sur FrenchMedMCQA, comme après le SFT. Les QCM sont dans le mélange d'entraînement
pour cela.

**Les paires DPO sont-elles validées cliniquement ?**
Non. Les 2 000 paires UltraMedical sont en anglais et jugées surtout par un modèle ; les 300
paires de triage sont générées. C'est une limite écrite, et la relecture clinique est dans la
phase 1 de la feuille de route.

## 3. Passage à l'échelle

**Faut-il un modèle de 32 milliards ?**
Peut-être, mais pas d'abord. Le modèle actuel échoue surtout hors des gabarits de ses données ;
un modèle plus grand entraîné sur les mêmes vignettes en garderait les limites. L'ordre que je
propose : données réelles, puis comparaison de modèles de 7 à 32 milliards sur le même
protocole.

**Combien coûterait un 32 milliards ?**
La charge n'est pas le problème : 50 000 passages par an, c'est quelques patients par minute,
et le POC tient 8,7 requêtes par seconde sur un seul GPU. Le coût vient de la disponibilité
24 h sur 24 : un GPU de 80 Go, de l'ordre de 2 200 à 2 900 $ par mois, la moitié en version
quantifiée. Le modèle actuel allumé en permanence : 600 à 800 $ par mois. (R § 10 ; ordres de
grandeur à confirmer auprès d'un hébergeur HDS)

**Comment l'intégrer au système d'information ?**
Par FHIR, le standard déjà porté par les éditeurs de dossiers patients : l'admission ouvre la
session (`Encounter`), les constantes arrivent en `Observation`, le niveau proposé devient
une `RiskAssessment` que l'IOA valide dans son outil, le journal devient des `AuditEvent`.
L'API actuelle s'y projette sans changer de logique. (R § 10)

**Comment améliorer le questionnaire adaptatif ?**
Seuls 8 % des exemples apprenaient à poser une question, jamais plus d'une. Il faut des
dialogues d'entraînement à plusieurs questions, idéalement rédigés ou relus par des IOA.

**Que faudrait-il pour la production ?**
Validation clinique, hébergement HDS, AIPD, dossier AI Act et dispositif médical,
intégration FHIR, authentification par utilisateur, sessions persistantes sur plusieurs
instances, surveillance avec astreinte. C'est la phase 3, à 12-24 mois.

## 4. Déploiement et exploitation

**Pourquoi vLLM ?**
Mesuré, pas supposé : sur le même GPU, p95 de 1,93 s contre 4,91 s avec Transformers seul,
pour des niveaux identiques sur 60 requêtes. vLLM est le seul des deux qui tient le seuil de
3 s, et il traite les requêtes simultanées en continu.

**Et si le GPU est éteint ou en panne ?**
Le GPU s'éteint après 5 minutes sans requête, pour un coût nul au repos ; il redémarre en 2 à
3 minutes. Pendant ce temps, l'API relaie le patient à l'IOA en 10 s au plus, avec le niveau
minimal imposé par les constantes et les drapeaux rouges, qui ne passent pas par le modèle.
La saisie de l'IOA fonctionne aussi sans modèle.

**Comment déployez-vous une nouvelle version ?**
Par la CI GitHub Actions : lint et 206 tests, construction de l'image, test de l'image sans
modèle et avec un faux vLLM, publication, déploiement sur Modal depuis `main`, contrôle en
ligne. 14 versions déployées ainsi. Le modèle est chargé à une révision fixe : revenir en
arrière, c'est relancer avec la révision précédente.

**Comment surveillez-vous le service ?**
Un script lit le journal d'audit et alerte sur 6 indicateurs : relais pour modèle
indisponible, latence p95, évaluations hors format, niveau relevé par un garde-fou, part de
MAXIMALE, messages en anglais. Les seuils sont des points de départ à réviser.

**Et la sécurité informatique ?**
Deux clés distinctes, l'une pour le triage, l'autre pour le journal ; aucun secret dans le
dépôt ni dans la page ; une clé par défaut est refusée hors développement. Les entrées sont
validées avant le modèle ; les injections testées sont neutralisées par les garde-fous, pas
par le modèle.

**Qu'avez-vous appris du déploiement ?**
Que le vrai service révèle ce que les tests ne voient pas : neuf défauts, tous corrigés. Le
plus parlant : face à une injection, le niveau était bien relevé à MAXIMALE, mais le message
affiché disait encore DIFFÉRÉE. (R § 7)

## 5. Questions cliniques et réglementaires

**Quelle est la valeur clinique ?**
Elle n'est pas encore démontrée, et je ne prétends pas le contraire. Le POC montre un
potentiel sur des cas fictifs. La vraie mesure, c'est l'écart entre le niveau de l'IOA et
celui du système sur des cas réels : c'est l'objet de la phase 1.

**Que se passe-t-il si le modèle se trompe ?**
Trois protections : les garde-fous déterministes qui ne peuvent que relever le niveau, l'IOA
qui valide chaque niveau, et le journal qui permet de retrouver chaque erreur. Le cas que
rien ne rattrape aujourd'hui : un signe grave formulé autrement que prévu (« eau bouillante
sur le visage »).

**Qui est responsable en cas d'erreur ?**
L'IOA décide, le système ne fait que proposer : aucune décision n'est entièrement automatisée
(art. 22 du RGPD). En production, le fabricant porterait la responsabilité du dispositif
médical, d'où le marquage CE.

**Est-ce que les IOA ne vont pas lui faire trop confiance ?**
C'est un vrai risque (biais d'automatisation). Réponses : l'avis rappelle toujours que l'IOA
décide, les garde-fous déclenchés sont affichés avec leur raison, et la formation des IOA est
une condition de la phase 3. Les justifications parfois inventées doivent être dites aux IOA.

**Quel cadre réglementaire ?**
- RGPD : AIPD obligatoire, base légale de mission d'intérêt public et de prise en charge.
- Hébergement HDS : Modal ne l'est pas ; démonstration sur cas fictifs uniquement.
- AI Act : le triage des patients aux urgences est un système à haut risque (annexe III).
- Dispositifs médicaux : probablement classe IIa ou plus, donc marquage CE ; l'exemption
  pour un usage interne est à étudier avec le service juridique. (R § 9)

**Les données des patients sont-elles protégées ?**
Aucune donnée du CHSA n'a été utilisée. Les corpus publics sont désidentifiés (Presidio), et
publiés en dépôts privés, car désidentifié n'est pas anonyme. Le journal masque noms et
numéros avant écriture, mais ce masquage ne garantit pas l'anonymat : en production, il faut
l'hébergement HDS.

**Pourquoi le recommander s'il n'atteint pas le seuil de sécurité ?**
Je ne le recommande pas pour de vrais patients : c'est un NO-GO en l'état. Je recommande une
expérimentation sans patient, avec les IOA, parce que c'est peu coûteux et que c'est la seule
façon de savoir s'il vaut la peine d'aller plus loin.

## Pièges à éviter

- Ne pas dire « le modèle est fiable » : dire « le système atteint les seuils sur des cas
  fictifs ».
- Ne pas cacher le 1/29 : en parler avant qu'on le demande (diapositive 9).
- Ne pas promettre de date de production : les phases sont conditionnées par leurs résultats.
- Ne pas présenter les prix des GPU et les points réglementaires comme vérifiés auprès d'un
  fournisseur ou d'un juriste : ce sont des ordres de grandeur et des pistes.
- Question inconnue : « Je ne l'ai pas mesuré ; voici comment je le mesurerais. »

---

# Partie 2 : liste d'entraînement (questions possibles, non officielles)

Réponses dans l'ordre de la liste. « Voir Q » renvoie à la partie 1 quand la réponse y est
déjà.

## 1. Objectif et périmètre du POC

**Quel besoin du personnel soignant ?**
Aider l'IOA à l'accueil des urgences saturées : recueillir les symptômes pendant l'attente,
proposer un niveau de priorité FRENCH expliqué, et signaler tout de suite un signe de gravité.
L'IOA garde la décision ; le système lui fait gagner du temps et sert de filet de sécurité.

**Pourquoi le fine-tuning plutôt qu'un prompt ou un RAG ?**
Mesuré, pour le prompt : le modèle de base avec 3 exemples dans le prompt apprend le format
(97 % de réponses lisibles) mais pas le triage (44 % d'exactitude, 70 % des cas graves
manqués) ; après SFT, 94,7 % et 10,6 %. Un RAG apporte des connaissances (le texte de FRENCH),
pas une décision ni un format de sortie stable. Limite honnête : je n'ai pas comparé avec un
modèle *Instruct* plus grand + RAG sur FRENCH, l'énoncé imposant le modèle Base. C'est une
comparaison à faire en phase 1, sur le même protocole.

**Comment recueille-t-il les symptômes et adapte-t-il ses questions ?**
Le modèle répond soit par une question, soit par une évaluation. Il a appris à poser la
question clé du motif (dans 8 % des exemples, une seule question). Le service borne
l'échange : 8 échanges au plus, puis relais à l'IOA, et arrêt immédiat des questions dès
qu'un signe de gravité (constante ou drapeau rouge) apparaît. Adaptation réelle mais limitée :
c'est l'attente « partielle » de la mission.

**Comment éviter qu'il se substitue à une décision clinique ?**
Par construction : chaque réponse dit que l'IOA valide ; les garde-fous ne peuvent que
relever le niveau ; aucun diagnostic, aucune posologie, aucun « rentrez chez vous » (0 sur
8 questions hors périmètre) ; l'interface s'appelle aide à la décision ; le journal permet de
comparer proposition et décision. Aucune décision entièrement automatisée.

## 2. Données et annotations

**Comment avez-vous sélectionné les sources ?**
Les quatre corpus sont imposés par l'énoncé : MediQAl et FrenchMedMCQA (français), MedQuAD
et UltraMedical (anglais). J'ai ajouté le référentiel FRENCH de la SFMU, seule source de
niveaux de tri. Deux écarts de l'énoncé corrigés : lien FrenchMedMCQA cassé (dépôt de
remplacement sous licence explicite), « MediQA » qui pointait vers MediQAl.

**Comment avez-vous vérifié fiabilité et licences ?**
Chaque source est figée à une révision, avec l'empreinte SHA-256 de chaque fichier
(`data/raw/MANIFEST.json`). Licences : CC BY 4.0, Apache 2.0, MIT. J'ai pris MedQuAD dans le
dépôt d'origine (CC BY 4.0) plutôt qu'un miroir sans licence, et ignoré les sous-corpus dont
les réponses ont été retirées pour copyright. Fiabilité : corrigés officiels pour les QCM,
sources NIH pour MedQuAD ; UltraMedical est jugé par GPT-4, donc marqué `model_judged`.

**Comment avez-vous construit les 5 000 paires ?**
Script unique (`scripts/build_dataset.py`) : filtrage, découpage, retrait des fuites, tirage
stratifié (graine 42), anonymisation, journal. 5 065 exemples SFT : 2 300 QCM français,
1 200 questions-réponses anglaises, 1 565 vignettes de triage. Même prompt système à
l'entraînement et en service. (R § 3)

**Comment avez-vous contrôlé la qualité des annotations ?**
Vignettes : chaque niveau est vérifié contre la table FRENCH extraite, et un test échoue
sinon ; les règles sur les constantes garantissent qu'aucun niveau attendu n'est moins grave
que les seuils. Sur les 1 850 réponses de référence, les 1 315 critères reconnus redonnent tous
le niveau de la vignette. Limite : aucune relecture par un soignant.

**Comment avez-vous anonymisé et documenté le RGPD ?**
Presidio (spaCy français et anglais, plus des motifs pour téléphones, e-mails, IBAN) sur tous
les textes non synthétiques. Rappel 22/22 sur un corpus annoté, environ 80 % sur des messages
réels relus : un prénom isolé sur cinq échappe. Le jeu est donc dit *désidentifié*, pas
anonyme, et publié en privé. Démarche écrite dans `docs/RGPD.md`. (R § 3, § 9)

**Doublons et fuites ?** Voir Q « Y a-t-il une fuite entre entraînement et test ? ». Plus :
doublons internes retirés sur la question normalisée, identifiants stables par empreinte.

**Comment avez-vous équilibré langues, situations et niveaux ?**
Niveaux : tirage à parts égales entre maximale, modérée et différée, puis motif et critère.
Situations : 61 motifs, 193 critères, trois formes (note d'IOA 40 %, récit 35 %, dialogue
25 %), 5 % de constantes critiques dans un motif bénin. Langues : SFT à environ 75 % en
français, pour garder l'anglais médical ; DPO surtout anglais (2 000 paires contre 300),
déséquilibre assumé faute de paires françaises. Les vrais motifs ne sont pas équiprobables :
cette répartition ne reflète pas la population des urgences.

## 3. Modèle, SFT et LoRA

**Quelles caractéristiques de Qwen3-1.7B-Base ont compté ?**
- C'est un modèle *Base* : il ne connaît pas le format de conversation, et ses jetons de tour
  (`<|im_end|>`…) n'ont jamais été entraînés. D'où le bug des réponses sans fin, corrigé en
  entraînant ces lignes.
- Le mode « réflexion » de Qwen3 est désactivé : un bloc `<think></think>` vide, le même à
  l'entraînement et en service (`enable_thinking=False`), contrôlé avant tout run GPU.
- 1,7 milliard : réponse courte et structurée, 1 024 jetons au plus par exemple.
- Le T4 n'a pas de bf16 : fp16, après un contrôle qu'il ne dégrade pas le modèle.

**Que modifie le SFT ?**
Il apprend au modèle à imiter la réponse attendue : le format (niveau, motif, critère,
explication, conduite), la correspondance entre symptômes et niveau, et quand poser une
question. La perte ne porte que sur la réponse, pas sur la question.

**Principe de LoRA et compromis ?**
Les poids d'origine sont gelés ; on ajoute à chaque projection de l'attention le produit de
deux petites matrices de rang 16, seules entraînées. Gain : 0,37 % des paramètres, moins de
mémoire, adaptateurs légers et échangeables. Coût : moins de capacité qu'un fine-tuning
complet, et la table des plongements n'est pas touchée (d'où l'entraînement explicite des
4 jetons).

**Comment avez-vous choisi modules, rang et hyperparamètres ?**
Valeurs classiques du cours, puis comparaison : projections q, k, v, o de l'attention, rang 16
(le cours conseille 4 à 32), α = 32 (deux fois le rang), dropout 0,05, 3 époques (1 à 3
conseillées). Deux taux comparés, 2·10⁻⁴ et 1·10⁻⁴ : 2·10⁻⁴ retenu (meilleur sous-triage et
perte plus basse). Piste non testée : cibler aussi les couches MLP.

**Comment avez-vous suivi le surapprentissage ?**
Perte de validation tous les 100 pas : de 0,611 à 0,397, elle plafonne sans remonter. Le
meilleur checkpoint est gardé automatiquement. Avant le run, un sur-apprentissage *volontaire*
de 100 exemples vérifie que la chaîne apprend. Et surtout les métriques métier en génération
sur la validation, car la perte ne dit pas si le niveau est juste.

**Quelles contraintes GPU ?**
Kaggle : 2 T4 de 16 Go, gratuits, sessions de 12 h. fp16 au lieu de bf16 ; lot de 4 avec
2 pas d'accumulation (lot effectif de 8) ; gradient checkpointing ; exemples de plus de 1 024
jetons retirés plutôt que tronqués ; reprise après interruption testée. Run SFT : 2 h 18,
11,3 Gio. Un adaptateur perdu a été réentraîné à l'identique, à un cas près.

## 4. Alignement par DPO

**Pourquoi un DPO après le SFT ?** Voir Q « Pourquoi un DPO après le SFT ? ».

**Comment avez-vous construit les paires ?**
- 300 paires de triage françaises : la préférée donne le bon niveau ; la rejetée est la même
  réponse sous-triée d'une catégorie (maximale → modérée, modérée → différée), qui ignore
  les éléments déterminants.
- 2 000 paires UltraMedical, à parts égales entre les types `easy`, `hard` et `length` ; les
  paires `length` corrigent le biais « la réponse longue gagne » (préférée plus longue dans
  38 % des cas, contre 90 % pour `easy`).

**Selon quels critères cliniques une réponse était-elle préférée ?**
Pour le triage, un seul critère, le plus important : ne pas sous-estimer la gravité. La
préférée suit le niveau FRENCH du critère présent. Pour UltraMedical, le jugement de GPT-4 sur
la qualité médicale, non validé cliniquement.

**DPO ou modèle de récompense ?**
Le RLHF entraîne d'abord un modèle de récompense, puis optimise le modèle par apprentissage par
renforcement (PPO) sous contrainte de rester proche de la référence. Le DPO obtient le même
objectif en une perte directe sur les paires, sans modèle de récompense ni génération pendant
l'entraînement : plus simple et plus stable, mais limité aux paires fournies. β = 0,1 règle
l'écart toléré à la référence (le modèle SFT).

**Comment avez-vous vérifié le gain sans perte ailleurs ?**
Sur la validation : cas graves manqués de 10,6 % à 1,5 % ; QCM inchangés (FrenchMedMCQA 48 %,
MediQAl 35 % → 34,7 %) ; justesse des paires médicales stable (77 %). Sur le jeu de sécurité
n° 1, 13 réponses dangereuses contre 15 (modèle seul). Le prix visible : sur-triage de 0,7 % à
10 %.

**Et si les préférences étaient incohérentes ou biaisées ?**
Le DPO amplifie ce que disent les paires, y compris leurs biais. Je l'ai observé : toutes mes
paires opposaient le bon niveau à un niveau plus bas, et le modèle a appris « dans le doute,
monter » (sur-triage). Avec des paires incohérentes, la marge entre préférée et rejetée ne
progresse pas et le modèle apprend du bruit. Parades : paires symétriques (contre le
sur-triage aussi), paires tirées des vraies erreurs, relecture clinique, suivi de la marge.

## 5. Évaluation et validation clinique

**Comment comparez-vous base, SFT et DPO ?**
Mêmes scripts, mêmes jeux, mêmes réglages de génération : modèle de base sans et avec
3 exemples, SFT, DPO, chacun seul puis avec les garde-fous. Validation pour choisir, test une
seule fois, jeux de sécurité pour les formulations libres. (R § 6)

**Quelles métriques, et que ne mesurent-elles pas ?**
Cas graves manqués (principale), exactitude, sur-triage, réponses dangereuses, latence, QCM.
Elles ne mesurent pas : la pertinence des questions posées, la justesse des explications, la
compréhension par le patient, le temps gagné par l'IOA, la performance sur la vraie
population des urgences.

**Comment évaluez-vous questionnaire, niveau et explications ?**
Le niveau : par les métriques ci-dessus. Les explications : seulement le critère cité, relu
par le garde-fou de cohérence, plus une lecture manuelle. Le questionnaire : pas de mesure
chiffrée, seulement les essais de démonstration. Ce sont deux trous de l'évaluation, à
combler en phase 1 avec des IOA.

**Comment repérez-vous hallucinations et recommandations dangereuses ?**
Une réponse est dangereuse si elle propose un niveau plus bas que le plancher du cas,
conseille de rentrer chez soi ou donne une posologie : mesuré sur 69 cas écrits à la main.
Hallucinations relevées en lisant les réponses : critères FRENCH inventés, références
fantaisistes. Le garde-fou de cohérence ne réagit pas à un critère inventé ; en service, la
part de niveaux relevés par un garde-fou est surveillée.

**Comment évaluez-vous les conséquences d'une sous-estimation ?**
Par l'asymétrie des seuils (5 % de cas graves manqués contre 20 % de sur-triage), une
métrique dédiée aux cas de priorité maximale, des paires DPO qui pénalisent le sous-triage, et
une sécurité qui ne repose pas sur le modèle seul. Je n'ai pas de modèle de coût clinique :
le pondérer avec des médecins serait plus juste.

**Quelle validation humaine ou clinique ?**
Aucune validation clinique. J'ai écrit et relu les vignettes, les 69 cas de sécurité et les
réponses ; seules les 163 paires `human` d'UltraMedical, en test, sont annotées par des
humains. C'est la limite principale, et la phase 1 sert à la lever.

**Et si les informations sont insuffisantes ou contradictoires ?**
Insuffisantes : le modèle pose une question ; au-delà de 8 échanges, relais à l'IOA avec le
niveau minimal des règles. Contradictoires (« ça va » avec une SpO2 à 85 %) : les garde-fous
prennent le plus grave, quoi que dise le modèle. Message hors sujet ou injection : recentrage.
Anglais : relais direct. Limite : la frontière MODÉRÉE / DIFFÉRÉE reste instable d'un passage
à l'autre.

## 6. Déploiement et sécurité

**Rôles de FastAPI et de vLLM ?**
vLLM sert le modèle sur GPU, au format de l'API OpenAI, avec le traitement continu des
requêtes simultanées. FastAPI, sur CPU, porte tout le reste : clés, sessions, garde-fous,
réécriture des messages, journal d'audit, page de démonstration, mode dégradé. Le modèle peut
changer sans toucher à la logique de sécurité.

**Comment avez-vous intégré le modèle et les adaptateurs LoRA ?**
Les deux adaptateurs (SFT puis DPO) sont fusionnés dans les poids, contrôlés (99,83 % de
jetons prédits identiques, mêmes résultats de sécurité), puis publiés en privé à une révision
fixe (`97e8679`). vLLM charge cette révision, sans adaptateur à l'exécution : plus simple et
plus rapide. vLLM sait aussi servir des adaptateurs LoRA séparés, utile pour comparer
plusieurs versions.

**Comment Docker aide-t-il la reproductibilité ?**
L'image de l'API fige Python (3.12.8), uv et les dépendances au fichier de verrouillage ;
elle tourne sans droits administrateur, avec un contrôle de santé. La CI la construit, la
teste, puis la publie sur le registre GitHub. vLLM tourne dans son image officielle à version
fixe (`v0.32.0`). `docker compose` lance les deux en local avec un GPU.

**Quels tests la CI automatise-t-elle ?** Voir Q « Comment déployez-vous une nouvelle
version ? » : lint, format, 206 tests, image testée sans modèle (relais attendu) et avec un faux
vLLM qui répond DIFFÉRÉE à une douleur thoracique (garde-fou, réécriture, audit, page servie).

**Comment avez-vous mesuré latence et robustesse ?**
`scripts/load_test.py` sur le service réel : 60 requêtes par palier de 1, 4, 8 et 16 requêtes
simultanées, p50 et p95 côté serveur et client. `scripts/robustness_test.py` : 20 cas avec un
critère de réussite écrit avant (entrées invalides, sans clé, messages extrêmes, injections,
anglais, hors sujet, limite d'échanges) : 18/20 au premier passage, 20/20 après corrections.

**Comment protégez-vous secrets et journaux ?**
Secrets dans GitHub et Modal, jamais dans le dépôt ni dans la page ; clés locales hors du
dépôt ; clé par défaut refusée hors développement ; comparaison des clés en temps constant.
Dans le journal, e-mails, téléphones, numéros de sécurité sociale, dates et noms après une
formule sont masqués avant écriture ; sa lecture exige une clé distincte.

**Traçabilité sans conserver trop de données personnelles ?**
Session à identifiant aléatoire, sans lien avec le patient ; pas de nom ni de numéro de
dossier ; textes masqués ; constantes et niveaux gardés, car ce sont eux qu'on audite. Limite
honnête : la durée de conservation n'est pas encore appliquée, et le masquage ne garantit pas
l'anonymat. En production : durée fixée dans l'AIPD, hébergement HDS.

## 7. Reproductibilité et passage à l'échelle

**Qu'est-ce qui permet de reproduire vos expériences ?**
Dépendances verrouillées (`uv.lock`) ; sources à révision fixe avec empreintes ; construction
scriptée avec graine et journal ; dataset publié à une révision ; configurations YAML
versionnées ; notebook Kaggle unique qui clone le dépôt ; chaque étape est un script ; README
qui décrit la reproduction de bout en bout.

**Comment reliez-vous dataset, configuration, checkpoint et résultats ?**
La configuration nomme la révision du dataset (`7dffce7`). Chaque run écrit sa
configuration, la révision du dataset, le commit Git et ses courbes (W&B), et ses résultats
dans `outputs/`. Le modèle servi est une révision fixe du dépôt de poids (`97e8679`), notée
dans le rapport et dans le déploiement.

**Quels critères go / no-go avant une mise à l'échelle ?**
Les seuils écrits avant le test (5 % de cas graves manqués, 75 % d'exactitude, 20 % de
sur-triage, 0 réponse dangereuse, 3 s de p95), puis les conditions de passage de chaque phase
de la feuille de route : concordance avec les IOA, borne haute sous 5 % sur données réelles,
avis du DPO et de la commission médicale, marquage CE ou exemption. (R § 10)

**Quelles limites empêchent un usage clinique réel ?** Voir Q « Que faudrait-il pour la
production ? » : sécurité non atteinte (1/29), données synthétiques, aucune validation
clinique, hébergement non HDS, cadre AI Act et dispositif médical non traité.

**Quelle amélioration prioriser ?**
Des données réelles : des dossiers d'urgence du CHSA désidentifiés, avec le tri attribué par
l'IOA, et des dialogues à plusieurs questions. C'est ce qui manque le plus, avant un modèle
plus grand.

## Questions de relance

**« Comment prouvez-vous que vos exemples sont représentatifs ? »**
Je ne le prouve pas, et je le dis. Ils couvrent systématiquement les critères de FRENCH, mais
ni la fréquence réelle des motifs, ni la façon dont les patients parlent. C'est pour cela que
j'ai ajouté des cas écrits hors gabarits, où le modèle seul se dégrade nettement (8/29). La
preuve viendra d'une étude rétrospective sur des dossiers du CHSA (phase 2).

**« La loss diminue : pourquoi cela ne suffit-il pas ? »**
La perte mesure l'imitation mot à mot de la réponse de référence, explication comprise : le
mot du niveau pèse autant qu'un autre. Elle ne dit pas si le niveau est juste, ni ce que fait
le modèle face à une formulation nouvelle. Exemple : perte de validation basse et stable, mais
8 réponses dangereuses sur 29 cas neufs.

**« Plus performant en moyenne, moins sûr sur certains cas : que décidez-vous ? »**
J'ai eu ce cas : le SFT avec garde-fous avait la meilleure exactitude (96,5 % contre 86,5 %),
mais 12 réponses dangereuses contre 9 pour le DPO sur le jeu de sécurité n° 1. J'ai choisi le
DPO : la sécurité passe avant la moyenne, et un sur-triage se corrige par l'IOA alors qu'un
sous-triage peut retarder une urgence vitale. Le choix et le repli sont écrits dans
`docs/DECISIONS.md`.

**« Comment distinguez-vous un gain réel d'un effet du jeu de test ? »**
Seuils et système fixés avant le test, une seule évaluation, intervalles de confiance
affichés, même tendance en validation et au test (le DPO réduit le sous-triage sur les deux),
et un second jeu de sécurité écrit avant les règles qu'il mesure. Limite : tous ces jeux ont
le même auteur ; seule une évaluation sur des données externes, réelles, tranche
définitivement.
