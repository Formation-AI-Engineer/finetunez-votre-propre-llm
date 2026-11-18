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
