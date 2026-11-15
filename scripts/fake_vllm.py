"""Faux serveur vLLM (API au format OpenAI) pour le test de fumée de l'image en CI.

Bibliothèque standard seulement. Répond toujours la même évaluation « DIFFÉRÉE », pour vérifier
dans le conteneur toute la chaîne : appel au modèle, garde-fou qui relève le niveau, message
réécrit, journal d'audit. Vérifie aussi que l'API envoie bien la clé et l'arrêt sur <|im_end|>.

Usage : python scripts/fake_vllm.py 9000 <clé attendue>
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

ANSWER = (
    "Niveau de priorité : DIFFÉRÉE (tri FRENCH 5)\n"
    "Motif de recours : Douleur thoracique\n"
    "Éléments déterminants : x. Critère FRENCH : « x ».\n"
    "Cet avis est une aide à la décision : l'infirmier ou l'infirmière d'accueil valide le "
    "niveau de tri."
)


class Handler(BaseHTTPRequestHandler):
    key = ""

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.key}"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/models" and self._authorized():
            self._send(200, {"object": "list", "data": [{"id": "triage-chsa"}]})
        else:
            self._send(401, {"error": "clé"})

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/v1/chat/completions" or not self._authorized():
            return self._send(401, {"error": "clé"})
        if body.get("stop_token_ids") != [151645, 151643]:
            return self._send(400, {"error": "stop_token_ids attendus"})
        self._send(200, {"choices": [{"message": {"role": "assistant", "content": ANSWER}}]})


if __name__ == "__main__":
    Handler.key = sys.argv[2]
    HTTPServer(("0.0.0.0", int(sys.argv[1])), Handler).serve_forever()
