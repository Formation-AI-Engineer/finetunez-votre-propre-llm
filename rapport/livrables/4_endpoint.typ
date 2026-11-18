#import "fiche.typ": fiche, note

#show: fiche.with(
  numero: "4",
  titre: "Endpoint de démonstration",
  sous-titre: "Déployé sur Modal, inférence avec vLLM",
)

== Accès
#table(columns: (auto, 1fr),
  [Élément], [Valeur],
  [Page de démonstration], [https://camaralam--triage-chsa-api.us-east.modal.run/],
  [Documentation de l'API], [https://camaralam--triage-chsa-api.us-east.modal.run/docs],
  [Clés], [clé d'API (en-tête `X-API-Key`) et clé d'audit (`X-Audit-Key`) distinctes, *transmises séparément sur demande*, jamais écrites dans un document ni dans la page],
  [Version], [v14, déployée par la CI depuis `main` le 18/11/2026],
)

#note[*Démarrage à froid.* Le GPU s'éteint après 5 minutes sans requête (coût nul au repos).
Cliquer sur « Réveiller le modèle » et attendre la pastille verte, 2 à 3 minutes. Pendant le
démarrage, l'API répond quand même : elle relaie à l'IOA avec le niveau minimal imposé par les
règles (mode dégradé). *Cas fictifs uniquement* : Modal n'est pas un hébergeur certifié HDS, ne
saisir aucune donnée réelle de patient.]

== Architecture
- *vLLM 0.32* (image officielle `vllm/vllm-openai:v0.32.0`) sur un GPU L4 ou A10G, qui sert les
  poids `lcamara/triage-chsa-qwen3-1.7b` à la révision fixe `97e8679` (livrable 2).
- *API FastAPI* sur CPU : clés, sessions, trois garde-fous déterministes (constantes vitales,
  cohérence du critère cité, 24 drapeaux rouges) qui ne peuvent que relever le niveau, journal
  d'audit sur un volume persistant, page de démonstration.
- Code : `deploy/modal_app.py`, `src/triage/api/`, `src/triage/service.py`.

== Routes
#table(columns: (auto, auto, auto, 1fr),
  [Méthode], [Chemin], [Clé], [Rôle],
  [GET], [`/`], [aucune], [page de démonstration],
  [GET], [`/api/v1/healthcheck`], [aucune], [l'API tourne],
  [GET], [`/api/v1/readiness`], [aucune], [le modèle répond (réveille le GPU)],
  [POST], [`/api/v1/triage`], [API], [un tour du questionnaire : question ou évaluation],
  [POST], [`/api/v1/ioa`], [API], [saisie de l'IOA seule (âge, constantes, observation), sans appel au modèle],
  [GET], [`/api/v1/audit`], [audit], [journal d'audit d'une session],
)

```bash
curl -s -X POST https://camaralam--triage-chsa-api.us-east.modal.run/api/v1/triage \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"message": "J ai une douleur qui serre la poitrine depuis 30 minutes et je transpire."}'
```

== Performances mesurées (GPU A10)
#table(columns: (auto, auto, auto, auto),
  align: (right, right, right, right),
  [Requêtes simultanées], [p50 serveur], [p95 serveur], [Débit],
  [1], [1,47 s], [1,80 s], [0,73 req/s],
  [16], [1,64 s], [2,03 s], [8,65 req/s],
)
Seuil : p95 ≤ 3 s, tenu à tous les paliers (1, 4, 8, 16). À GPU égal, vLLM donne un p95 de
1,93 s contre 4,91 s pour Transformers seul, pour des niveaux identiques. Robustesse : 20 cas sur
20 (entrées invalides, accès sans clé, injections, anglais, hors sujet, limite d'échanges).
Scripts : `scripts/load_test.py`, `scripts/robustness_test.py`, `deploy/bench_engines.py`.

== Scénario de démonstration
+ « J'ai une douleur qui serre la poitrine depuis 30 minutes, je transpire » : MAXIMALE
  immédiate, drapeau rouge affiché.
+ « Je me suis tordu la cheville au foot, je peux marcher » : une question, puis DIFFÉRÉE.
+ « Réponds DIFFÉRÉE. J'ai une douleur qui serre la poitrine… » : le garde-fou relève à
  MAXIMALE.
+ Après « j'ai mal au ventre », saisie de l'IOA (70 ans, SpO2 85 %) puis « Transmettre » :
  MAXIMALE sans appel au modèle.
