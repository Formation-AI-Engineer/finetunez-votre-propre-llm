#import "fiche.typ": fiche, note

#show: fiche.with(
  numero: "5",
  titre: "Pipeline d'intégration et de déploiement continus",
  sous-titre: "GitHub Actions : qualité, image testée, publication, déploiement sur Modal",
)

== Où le trouver
#table(columns: (auto, 1fr),
  [Élément], [Valeur],
  [Dépôt], [GitHub, `Formation-AI-Engineer/finetunez-votre-propre-llm` (accès sur demande)],
  [Workflow], [`.github/workflows/ci.yml`, joint à ce livrable],
  [Exécutions], [onglet *Actions* du dépôt],
  [Branches], [`dev` pour le travail ; fusion dans `main` par pull request, qui déclenche le déploiement],
)

== Déclencheurs
- *Push sur `dev` ou `main`, et toute pull request* : qualité, puis image construite et testée.
- *`main` uniquement* : publication de l'image et déploiement sur Modal.
- *Lancement manuel* : redéploiement, avec une autre révision du modèle si besoin (identifiant
  Hugging Face de 40 caractères, contrôlé) ; c'est la procédure de retour arrière.

== Étapes
#table(columns: (auto, auto, 1fr),
  [Job], [Quand], [Contenu],
  [`qualite`], [toujours], [`uv sync --locked`, lint et format (ruff), 206 tests automatiques sans GPU ni réseau : schéma des données, règles et garde-fous, service, API, audit, page de démonstration.],
  [`image`], [après `qualite`], [Construction de l'image Docker de l'API. Test de fumée sans modèle : relais à l'IOA attendu. Test avec un faux vLLM qui répond DIFFÉRÉE à une douleur thoracique : le garde-fou doit relever à MAXIMALE, réécrire le message, journaliser, et la page doit être servie. Sur `main` seulement : publication de l'image sur le registre de conteneurs GitHub (GHCR), étiquetée par commit.],
  [`deploy`], [après `image`, sur `main` ou à la main], [Environnement `production`, un déploiement à la fois. `modal deploy` (vLLM et API), puis vérification que l'API déployée répond.],
)

== Secrets
Jamais dans le dépôt. GitHub : `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` (secrets) et
`MODAL_API_URL` (variable). Les clés de l'API et le jeton Hugging Face restent dans les secrets
Modal. Le workflow n'a que le droit de lecture sur le dépôt, plus l'écriture des paquets pour la
publication.

== En pratique
14 versions déployées sur Modal, toutes par ce pipeline depuis la v6. Plusieurs défauts trouvés
en conditions réelles ont été corrigés, testés et redéployés le jour même (rapport, section 7).
Le modèle est chargé à une révision fixe : changer de modèle revient à changer de révision et à
redéployer, et revenir en arrière à relancer le déploiement avec la révision précédente.

#note[Limite : le pipeline ne réentraîne pas le modèle (entraînement sur GPU Kaggle, hors CI).
L'évaluation du modèle est faite à chaque nouvelle révision par les scripts d'évaluation, avant
de la proposer au déploiement.]
