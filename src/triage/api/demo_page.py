"""Page de démonstration (soutenance), servie par l'API sur `GET /`.

Module Python plutôt que fichier HTML : Modal n'embarque que les fichiers `.py` du paquet.
La page ne contient aucune clé : la personne qui fait la démonstration saisit la clé d'API (et la
clé d'audit pour le journal), gardées dans l'onglet (sessionStorage). Le texte du modèle est
toujours inséré comme texte (`textContent`), jamais comme HTML.
"""

DEMO_HTML = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pré-triage CHSA</title>
<style>
:root {
  --bg: #f6f7f9; --panel: #ffffff; --text: #1d2330; --muted: #5b6475; --line: #dde1e8;
  --accent: #2456c7; --patient: #e8eefc; --agent: #ffffff;
  --max: #c62828; --max-bg: #fde8e8; --mod: #b25e00; --mod-bg: #fff1dc;
  --dif: #1f7a3d; --dif-bg: #e3f4e8; --ioa: #5a3fa8; --ioa-bg: #ece7fa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151b; --panel: #1b1f27; --text: #e7eaf0; --muted: #9aa3b5; --line: #2c3240;
    --accent: #7ea2ff; --patient: #23304d; --agent: #1b1f27;
    --max: #ff8a80; --max-bg: #3d1d1d; --mod: #ffb74d; --mod-bg: #3a2b14;
    --dif: #7bd88f; --dif-bg: #16301e; --ioa: #b9a6ff; --ioa-bg: #2a2342;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header { padding: 14px 16px; border-bottom: 1px solid var(--line); background: var(--panel);
  display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; justify-content: space-between; }
h1 { font-size: 18px; margin: 0; }
.sub { color: var(--muted); font-size: 13px; }
main { max-width: 1100px; margin: 0 auto; padding: 16px; display: grid; gap: 16px;
  grid-template-columns: minmax(0, 1fr) 320px; }
@media (max-width: 860px) { main { grid-template-columns: minmax(0, 1fr); } }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; }
.panel h2 { font-size: 14px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--muted); }
#chat { display: flex; flex-direction: column; gap: 10px; min-height: 260px; max-height: 60vh;
  overflow-y: auto; padding-right: 4px; }
.msg { padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line); white-space: pre-wrap;
  max-width: 92%; overflow-wrap: anywhere; }
.msg.patient { align-self: flex-end; background: var(--patient); }
.msg.agent { align-self: flex-start; background: var(--agent); }
.msg .meta { display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.empty { color: var(--muted); font-style: italic; }
form.compose { display: flex; gap: 8px; margin-top: 12px; }
textarea, input { font: inherit; color: var(--text); background: var(--bg);
  border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; width: 100%; }
textarea { resize: vertical; min-height: 44px; }
button { font: inherit; border: 1px solid var(--accent); background: var(--accent); color: #fff;
  border-radius: 8px; padding: 8px 14px; cursor: pointer; white-space: nowrap; }
button.ghost { background: transparent; color: var(--accent); }
button:disabled { opacity: .55; cursor: wait; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
label { font-size: 13px; color: var(--muted); display: block; }
label input, label textarea { margin-top: 2px; }
.pill { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; padding: 3px 10px;
  border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.pill.ok .dot { background: var(--dif); } .pill.wait .dot { background: var(--mod); }
.pill.down .dot { background: var(--max); }
.result { border-radius: 10px; padding: 12px; margin-top: 4px; border: 1px solid var(--line); }
.result .level { font-size: 20px; font-weight: 700; }
.maximale { background: var(--max-bg); color: var(--max); border-color: var(--max); }
.moderee { background: var(--mod-bg); color: var(--mod); border-color: var(--mod); }
.differee { background: var(--dif-bg); color: var(--dif); border-color: var(--dif); }
.relais { background: var(--ioa-bg); color: var(--ioa); border-color: var(--ioa); }
.result ul { margin: 6px 0 0; padding-left: 18px; color: var(--text); }
.small { font-size: 12px; color: var(--muted); }
.disclaimer { font-size: 13px; color: var(--muted); border-left: 3px solid var(--line);
  padding-left: 8px; margin-top: 10px; }
details summary { cursor: pointer; font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 8px; }
th, td { border-bottom: 1px solid var(--line); padding: 4px; text-align: left; vertical-align: top; }
.closed { border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin-top: 12px;
  font-size: 13px; background: var(--bg); }
.closed strong { display: block; }
.err { color: var(--max); font-size: 13px; margin-top: 6px; min-height: 1em; }
</style>
</head>
<body>
<header>
  <div>
    <h1>Pré-triage des urgences — CHSA</h1>
    <div class="sub">Démonstration : aide à la décision, l'infirmier ou l'infirmière d'accueil valide le niveau.</div>
  </div>
  <div class="row">
    <span id="model" class="pill"><span class="dot"></span><span>Modèle : état inconnu</span></span>
    <button id="wake" class="ghost" type="button">Réveiller le modèle</button>
  </div>
</header>

<main>
  <section class="panel">
    <h2>Questionnaire patient</h2>
    <div id="chat" aria-live="polite"><p class="empty">Décrivez ce qui vous amène aux urgences.</p></div>
    <div class="closed" id="closed" hidden>
      <strong>Questionnaire terminé</strong>
      L'infirmier ou l'infirmière d'accueil prend le relais. Le champ ci-dessous sert seulement à
      signaler une aggravation : le niveau peut monter, jamais baisser.
    </div>
    <form class="compose" id="compose">
      <textarea id="text" rows="2" maxlength="4000" placeholder="Ex. : J'ai mal au ventre depuis hier soir, surtout en bas à droite." required></textarea>
      <button id="send" type="submit">Envoyer</button>
    </form>
    <div class="err" id="err"></div>
    <div class="row" style="justify-content: space-between">
      <span class="small" id="session">Pas de session</span>
      <button id="reset" class="ghost" type="button">Nouveau patient</button>
    </div>
  </section>

  <aside style="display: grid; gap: 16px; align-content: start">
    <section class="panel">
      <h2>Accès</h2>
      <label>Clé d'API <input id="apikey" type="password" autocomplete="off"></label>
    </section>

    <section class="panel">
      <h2>Saisie de l'IOA (facultatif)</h2>
      <div class="grid2">
        <label>Âge (ans) <input id="age" type="number" min="0" max="120" step="1"></label>
        <label>SpO2 (%) <input id="spo2" type="number" min="50" max="100"></label>
        <label>FC (/min) <input id="heart_rate" type="number" min="20" max="250"></label>
        <label>FR (/min) <input id="respiratory_rate" type="number" min="4" max="80"></label>
        <label>PAS (mmHg) <input id="systolic_bp" type="number" min="40" max="280"></label>
        <label>PAD (mmHg) <input id="diastolic_bp" type="number" min="20" max="160"></label>
        <label>T° (°C) <input id="temperature" type="number" min="25" max="43" step="0.1"></label>
        <label>Glasgow <input id="gcs" type="number" min="3" max="15"></label>
        <label>Glycémie (mmol/l) <input id="glycemia" type="number" min="0.5" max="60" step="0.1"></label>
      </div>
      <label style="margin-top: 8px">Observation <textarea id="observation" rows="2" maxlength="1000"></textarea></label>
      <p class="small">Envoyées avec le prochain message, puis seulement si elles changent.</p>
    </section>

    <section class="panel">
      <h2>Dernier résultat</h2>
      <div id="result"><p class="empty">Aucun pour l'instant.</p></div>
    </section>

    <section class="panel">
      <details>
        <summary>Journal d'audit de la session</summary>
        <label style="margin-top: 8px">Clé d'audit <input id="auditkey" type="password" autocomplete="off"></label>
        <button id="audit" class="ghost" type="button" style="margin-top: 8px">Afficher</button>
        <div id="auditout"></div>
      </details>
    </section>
  </aside>
</main>

<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const VITALS = ["heart_rate", "systolic_bp", "diastolic_bp", "respiratory_rate", "spo2",
                  "temperature", "gcs", "glycemia"];
  const LABEL = { maximale: "MAXIMALE", moderee: "MODÉRÉE", differee: "DIFFÉRÉE" };
  let sessionId = null;
  let lastContext = "";
  let lastModelAnswer = 0;
  const PLACEHOLDER = $("text").placeholder;

  function setClosed(closed) {
    $("closed").hidden = !closed;
    $("text").placeholder = closed ? "Signaler une aggravation (ex. : la douleur augmente)" : PLACEHOLDER;
    $("send").dataset.label = closed ? "Signaler" : "Envoyer";
    $("send").textContent = $("send").dataset.label;
    $("reset").className = closed ? "" : "ghost";
  }  // le GPU s'éteint après 5 min sans requête (scaledown Modal)

  const store = {
    get(k) { try { return sessionStorage.getItem(k) || ""; } catch { return ""; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch {} },
  };
  for (const k of ["apikey", "auditkey"]) {
    $(k).value = store.get(k);
    $(k).addEventListener("change", () => store.set(k, $(k).value));
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function addMsg(who, text, meta) {
    const chat = $("chat");
    chat.querySelector(".empty")?.remove();
    const m = el("div", "msg " + who);
    if (meta) m.append(el("span", "meta", meta));
    m.append(document.createTextNode(text));
    chat.append(m);
    chat.scrollTop = chat.scrollHeight;
  }

  function context() {
    const body = {};
    const age = $("age").value;
    if (age !== "") body.age_years = Number(age);
    const vitals = {};
    for (const k of VITALS) if ($(k).value !== "") vitals[k] = Number($(k).value);
    if (Object.keys(vitals).length) body.vitals = vitals;
    const obs = $("observation").value.trim();
    if (obs) body.observation = obs;
    return body;
  }

  function showResult(d) {
    const box = $("result");
    box.replaceChildren();
    if (d.status === "question" && !d.alerts.length) {
      box.append(el("p", "empty", "Question en cours : pas encore de niveau."));
      return;
    }
    const cls = d.status === "relais_ioa" ? "relais" : (d.priority || "relais");
    const card = el("div", "result " + cls);
    if (d.status === "relais_ioa") card.append(el("div", "level", "Relais à l'IOA"));
    if (d.priority) {
      card.append(el("div", "level",
        LABEL[d.priority] + (d.french_level ? " · tri FRENCH " + d.french_level : "")));
    } else if (d.status === "question") {
      card.append(el("div", "level", "Question en cours"));
    }
    if (d.model_priority && d.model_priority !== d.priority) {
      card.append(el("div", "small", "Modèle : " + LABEL[d.model_priority] +
        " → relevé par un contrôle de sécurité"));
    }
    if (d.guards.length) {
      card.append(el("strong", "", "Garde-fous déclenchés"));
      const ul = el("ul");
      for (const g of d.guards) ul.append(el("li", "", g.name + " : " + g.reason));
      card.append(ul);
    }
    if (d.alerts.length) {
      card.append(el("strong", "", "Alertes pour l'IOA"));
      const ul = el("ul");
      for (const a of d.alerts) ul.append(el("li", "", a));
      card.append(ul);
    }
    box.append(card);
    box.append(el("p", "disclaimer", d.disclaimer));
    box.append(el("p", "small", "Échange " + d.turn + " · réponse du modèle en " +
      (d.latency_ms / 1000).toFixed(1).replace(".", ",") + " s · " + d.model_id));
  }

  async function send(ev) {
    ev.preventDefault();
    const text = $("text").value.trim();
    $("err").textContent = "";
    if (!text) return;
    if (!$("apikey").value) { $("err").textContent = "Saisissez la clé d'API."; return; }
    const body = { message: text };
    if (sessionId) body.session_id = sessionId;
    const ctx = context();
    const ctxKey = JSON.stringify(ctx);
    if (ctxKey !== lastContext) Object.assign(body, ctx);
    addMsg("patient", text, "Patient");
    $("text").value = "";
    $("send").disabled = true;
    $("send").textContent = "…";
    try {
      const r = await fetch("api/v1/triage", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": $("apikey").value },
        body: JSON.stringify(body),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        const detail = typeof d.detail === "string" ? d.detail : "requête refusée";
        $("err").textContent = "Erreur " + r.status + " : " + detail;
        if (r.status === 404) reset();
        return;
      }
      lastContext = ctxKey;
      sessionId = d.session_id;
      $("session").textContent = "Session " + sessionId;
      addMsg("agent", d.message, d.status === "evaluation" ? "Évaluation" :
        d.status === "relais_ioa" ? "Relais IOA" : "Question");
      showResult(d);
      // Session close côté API après une évaluation : on le montre (pas de « merci » en boucle).
      // Un relais pour modèle indisponible n'est pas une fin : le patient peut réessayer.
      const unavailable = d.message.includes("modèle indisponible");
      if (d.status === "evaluation" || (d.status === "relais_ioa" && !unavailable)) setClosed(true);
      if (unavailable) {
        $("err").textContent = "Le modèle démarre (2 à 3 min) : réessayez quand la pastille est verte.";
        lastModelAnswer = 0;
        wake();
      } else if (d.latency_ms > 0) {
        lastModelAnswer = Date.now();
        setModel("ok", "Modèle prêt");
      }
    } catch (e) {
      $("err").textContent = "Réseau indisponible : " + e.message;
    } finally {
      $("send").disabled = false;
      $("send").textContent = $("send").dataset.label || "Envoyer";
      $("text").focus();
    }
  }

  function reset() {
    sessionId = null;
    lastContext = "";
    $("chat").replaceChildren(el("p", "empty", "Décrivez ce qui vous amène aux urgences."));
    $("result").replaceChildren(el("p", "empty", "Aucun pour l'instant."));
    $("session").textContent = "Pas de session";
    $("auditout").replaceChildren();
    for (const k of ["age", "observation", ...VITALS]) $(k).value = "";
    setClosed(false);
    $("err").textContent = "";
  }

  function setModel(state, text) {
    $("model").className = "pill " + state;
    $("model").lastElementChild.textContent = text;
  }

  let waking = false;
  async function wake() {
    if (waking) return;
    waking = true;
    $("wake").disabled = true;
    const start = Date.now();
    setModel("wait", "Modèle : démarrage…");
    while (Date.now() - start < 6 * 60 * 1000) {
      try {
        const r = await fetch("api/v1/readiness");
        if (r.ok) {
          setModel("ok", "Modèle prêt");
          lastModelAnswer = Date.now();
          break;
        }
      } catch {}
      const s = Math.round((Date.now() - start) / 1000);
      setModel("wait", "Modèle : démarrage (" + s + " s)");
      await new Promise((res) => setTimeout(res, 5000));
    }
    if (!$("model").classList.contains("ok")) setModel("down", "Modèle indisponible");
    waking = false;
    $("wake").disabled = false;
  }

  async function audit() {
    const out = $("auditout");
    out.replaceChildren();
    if (!sessionId) { out.append(el("p", "small", "Pas de session en cours.")); return; }
    const r = await fetch("api/v1/audit?session_id=" + encodeURIComponent(sessionId),
      { headers: { "X-Audit-Key": $("auditkey").value } });
    if (!r.ok) { out.append(el("p", "err", "Erreur " + r.status)); return; }
    const rows = await r.json();
    const t = el("table");
    const head = el("tr");
    for (const h of ["Éch.", "Statut", "Modèle", "Final", "ms"]) head.append(el("th", "", h));
    t.append(head);
    for (const e of rows) {
      const tr = el("tr");
      for (const v of [e.turn, e.status, e.model_priority || "—", e.priority || "—", e.latency_ms])
        tr.append(el("td", "", String(v)));
      t.append(tr);
    }
    out.append(t);
    out.append(el("p", "small", rows.length + " entrée(s), identifiants directs masqués."));
  }

  $("compose").addEventListener("submit", send);
  $("text").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("compose").requestSubmit(); }
  });
  $("reset").addEventListener("click", reset);
  $("wake").addEventListener("click", wake);
  $("audit").addEventListener("click", audit);
  setInterval(() => {
    if (lastModelAnswer && Date.now() - lastModelAnswer > 5 * 60 * 1000 && !waking) {
      lastModelAnswer = 0;
      setModel("wait", "Modèle en veille probable");
    }
  }, 30000);
  // Pas d'appel au chargement : vérifier l'état réveille le GPU (facturé). Sur clic seulement.
})();
</script>
</body>
</html>
"""
