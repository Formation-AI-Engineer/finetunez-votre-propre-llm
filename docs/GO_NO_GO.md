# Go / no-go, limites d'usage et surveillance (15/11/2026)

Version évaluée : **v9 sur Modal**, déployée par la CI depuis `77319bf` (`main`), modèle
`lcamara/triage-chsa-qwen3-1.7b@97e8679` (SFT + DPO fusionnés), vLLM 0.32.0, garde-fous
(constantes, cohérence du critère cité, drapeaux rouges), page de démonstration sur `GET /`.

## Verdict

| Usage | Décision |
|---|---|
| **Démonstration et soutenance**, cas fictifs, IOA dans la boucle | **GO** |
| **Expérimentation encadrée** (simulation avec des IOA, sans patient réel, sans effet sur la prise en charge) | **GO sous conditions** (ci-dessous) |
| **Usage avec de vrais patients**, même comme simple aide | **NO-GO** |
| **Modèle seul**, sans les garde-fous | **NO-GO** (8 réponses dangereuses sur 29 cas neufs) |

Le système est une aide à la décision qui ne décide jamais seule : chaque réponse rappelle que
l'IOA valide le niveau, et les garde-fous ne peuvent que relever le niveau, jamais le baisser
(`docs/DECISIONS.md`, point 7).

## Checklist

### Critères d'acceptation (fixés le 13/11, avant le test)

| Critère | Seuil | Mesuré | Statut |
|---|---|---|---|
| Sous-triage des cas maximale (test, 84 cas) | ≤ 5 % | 1,2 % [IC 95 % 0,2 ; 6,4] ; 0 % avec drapeaux | ✅ (borne haute au-dessus : taille du test) |
| Exactitude à 3 niveaux (test, 200 vignettes) | ≥ 75 % | 86,5 % | ✅ |
| Sur-triage (test) | ≤ 20 % | 12,0 % (14,5 % avec drapeaux) | ✅ |
| Réponse dangereuse, jeu de sécurité neuf (29 cas) | 0 | **1** (brûlure du visage sans le mot « brûlure ») | ❌ risque résiduel affiché |
| Latence p95 d'une réponse | ≤ 3 s | 1,88 s (1 requête) à 2,03 s (16 simultanées) | ✅ |

### Service

| Point | Statut | Preuve |
|---|---|---|
| Endpoint en ligne, HTTPS, clé d'API, clé d'audit distincte | ✅ | test de bout en bout, robustesse (401) |
| Entrées invalides rejetées avant le modèle | ✅ | robustesse 9/9 (422, 401, 404) |
| Injection de prompt sans effet sur le niveau | ✅ | 4/4, mais **le modèle seul obéit** : ce sont les garde-fous qui tiennent |
| Mode dégradé si vLLM est indisponible | ✅ | relais IOA en 10 s au plus, plancher des constantes et des drapeaux rouges conservé (16/11) |
| Évaluations hors format rattrapées | ✅ | lecture de secours, alerte IOA (10 % des « questions » avant correction) |
| Session close après l'évaluation, niveau qui ne peut que monter | ✅ | tests unitaires, page verrouillée |
| Journal d'audit sans identifiant direct, persistant | ✅ | volume Modal, masquage des noms et numéros |
| Déploiement reproductible, révision du modèle fixée | ✅ | CI/CD : v6 à v9 déployées depuis `main` |
| Changer de modèle par simple révision | ✅ | lancement manuel du workflow (`model_revision`) |
| Secrets hors du dépôt | ✅ | GitHub Actions (jeton Modal dédié), secrets Modal |
| Coûts plafonnés | ✅ | GPU éteint après 5 min, plafond de dépenses Modal à 0 $ au-delà des crédits |
| Surveillance outillée | ✅ | `scripts/monitor_audit.py` (ci-dessous) |

### Conditions du go « expérimentation encadrée »

1. Cas fictifs ou rejoués, jamais de vrai patient ni de donnée de santé réelle.
2. Une IOA valide chaque niveau ; le niveau proposé n'a aucun effet sur la prise en charge.
3. Le GPU est réveillé avant la séance (« Réveiller le modèle ») : pas de démarrage à froid
   devant un utilisateur.
4. `scripts/monitor_audit.py` est lancé après chaque séance ; toute alerte est analysée avant la
   séance suivante.
5. Les écarts IOA / système sont relevés (niveau de l'IOA à côté du niveau proposé) : c'est la
   seule mesure de la vraie performance.

## Limites d'usage

| Limite | Constat | Atténuation en place | Ce qui reste |
|---|---|---|---|
| **Signe grave formulé autrement** | 1/29 cas neufs manqué (« eau bouillante sur le visage ») | drapeaux rouges sur 24 critères FRENCH | une liste de règles ne couvre pas toutes les formulations ; l'IOA valide |
| **Sur-triage** | 12 à 14,5 % au test ; en démonstration, diarrhée → MAXIMALE 2, douleur au genou → MAXIMALE (« Vous avez besoin d'un niveau de priorité maximale » en réponse par défaut) | aucune : erreur dans le sens prudent | file d'attente des cas graves encombrée si le taux monte ; indicateur `maximale_pct` |
| **Justifications inventées** | « poussière de soie », « cétorragie », données d'âge ou de poids inventées | message réécrit quand le format dérape ; IOA | une justification bien formée peut rester fausse : ne pas s'y fier |
| **Format non respecté** | 10 % des réponses classées « question » étaient des évaluations hors format ; 4/448 évaluations avec en-tête enfoui | lecture de secours, réécriture, alerte | indicateur `evaluations_hors_format_pct` |
| **Variabilité** | même message : MODÉRÉE 3B puis DIFFÉRÉE 4 à deux passages | aucune | frontière 3B / 4 instable : l'IOA tranche |
| **Langue** | triage validé en français seulement | anglais → relais IOA (0 faux positif sur 2 166 vignettes) | messages anglais très courts et autres langues non détectés |
| **Hors sujet** | répond « Canberra » | aucune (sans danger) | hors périmètre |
| **Démarrage à froid** | 2 à 3 min après 5 min d'inactivité ou un redéploiement | relais IOA en 10 s, réveil depuis la page | `min_containers=1` le supprimerait (≈ 0,80 à 1,10 $/h en continu) |
| **Sessions en mémoire** | un seul conteneur d'API ; un redémarrage perd les sessions en cours | 404 « session inconnue » propre, la page repart | pas de montée en charge horizontale |
| **Données d'évaluation** | vignettes synthétiques, rédigées par un seul auteur avec les règles | intervalles de confiance rapportés | performance réelle inconnue |

## Surveillance après déploiement

`scripts/monitor_audit.py` lit le journal d'audit (par l'API avec la clé d'audit, ou en fichier)
et sort avec le code 1 si un seuil est franchi, ce qui permet de le lancer dans une tâche
planifiée.

| Indicateur | Seuil d'alerte | Ce qu'une alerte signale |
|---|---|---|
| `relais_modele_indisponible_pct` | > 2 % | démarrages à froid ou panne vLLM |
| `latence_p95_ms` | > 3 000 | saturation du GPU, réponses trop longues |
| `evaluations_hors_format_pct` | > 10 % | dérive du modèle (nouvelle révision, nouveaux types de messages) |
| `niveau_releve_par_garde_fou_pct` | > 15 % | le modèle sous-trie plus qu'au test |
| `maximale_pct` | > 40 % | sur-triage massif |
| `messages_en_anglais_pct` | > 5 % | public non francophone à prendre en charge autrement |

Les seuils sont des points de départ, à réviser après les premières séances. Première exécution
sur le journal du 15/11 (822 entrées, presque toutes issues des tests) : deux alertes attendues,
`maximale_pct` 56,9 % (tests de charge et de sécurité riches en cas graves) et
`relais_modele_indisponible_pct` 2,2 % (démarrages à froid des neuf redéploiements). Le journal
de production devra être séparé de celui des tests (`--since`, ou un volume par environnement).

Le journal se lit par l'API par lots de 1 000 entrées au plus : au-delà, il faudra paginer ou
lire le fichier du volume.

**Retour arrière** : relancer le workflow sur `main` avec la révision précédente du modèle
(`model_revision`), ou redéployer un commit antérieur ; `modal app history triage-chsa` liste
les versions déployées et leur commit.

## Avant toute mise en production (levée du no-go)

1. **Hébergement de données de santé** : Modal (us-east) n'est ni certifié HDS ni situé dans
   l'Union européenne. Un usage réel exige un hébergeur certifié HDS et un traitement conforme
   au RGPD (`docs/RGPD.md`) : base légale, AIPD, durée de conservation du journal.
2. **Validation clinique** : étude prospective avec des IOA sur des données réelles, mesure du
   sous-triage sur un échantillon assez grand pour une borne haute sous 5 % (≥ 60 cas maximale
   sans erreur, en pratique plusieurs centaines de cas).
3. **Cadre réglementaire** : un logiciel d'aide au triage relève du règlement européen sur les
   dispositifs médicaux (marquage CE) et du règlement sur l'IA (système à haut risque).
4. **Modèle** : données d'entraînement réelles et variées pour réduire le sous-triage du
   modèle seul et les justifications inventées ; réévaluer après chaque nouvelle révision.
5. **Exploitation** : authentification par utilisateur (pas une clé partagée), limitation de
   débit, sessions persistantes (plusieurs conteneurs), `min_containers=1` en service,
   surveillance planifiée avec alerte.
