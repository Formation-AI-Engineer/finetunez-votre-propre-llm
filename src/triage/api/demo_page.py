"""Page de démonstration (soutenance), servie par l'API sur `GET /`.

Module Python plutôt que fichier HTML : Modal n'embarque que les fichiers `.py` du paquet.
Page autonome : aucune ressource externe (polices, icônes, scripts), les icônes sont des SVG
embarqués. Elle ne contient aucune clé : la personne qui fait la démonstration saisit la clé
d'API (et la clé d'audit pour le journal), gardées dans l'onglet (sessionStorage). Le texte du
modèle est toujours inséré comme texte (`textContent`), jamais comme HTML.
"""

DEMO_HTML = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pré-triage CHSA</title>
<style>
:root {
  --bg: #eef2f8; --panel: #ffffff; --text: #172033; --muted: #5d6879; --line: #e2e7ef;
  --soft: #f5f7fb; --brand: #1565d8; --brand-2: #0e9f9a; --brand-ink: #ffffff;
  --brand-soft: #e7f0fd; --shadow: 0 1px 2px rgba(16, 24, 40, .05), 0 10px 30px rgba(16, 24, 40, .07);
  --max: #d92d20; --max-bg: #fef1f0; --mod: #c4560b; --mod-bg: #fff4e8;
  --dif: #138a4b; --dif-bg: #eafaf1; --ioa: #6941c6; --ioa-bg: #f3effd;
  --guard: #0b6bcb; --guard-bg: #e8f2fd; --alert: #b54708; --alert-bg: #fffaeb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d121b; --panel: #161d29; --text: #e8ecf3; --muted: #9aa5b8; --line: #263043;
    --soft: #1c2433; --brand: #5b9cff; --brand-2: #2cc7c0; --brand-ink: #0d121b;
    --brand-soft: #1b2a45; --shadow: 0 1px 2px rgba(0, 0, 0, .3), 0 10px 30px rgba(0, 0, 0, .25);
    --max: #ff8a80; --max-bg: #3a1c1c; --mod: #ffb366; --mod-bg: #38291a;
    --dif: #6ee39d; --dif-bg: #15301f; --ioa: #b9a2ff; --ioa-bg: #2a2342;
    --guard: #7fb6ff; --guard-bg: #19304f; --alert: #ffc46b; --alert-bg: #3a2e14;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: radial-gradient(1200px 400px at 20% -10%, var(--brand-soft), transparent),
  var(--bg); color: var(--text); min-height: 100vh;
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
svg.i { width: 18px; height: 18px; flex: none; stroke: currentColor; fill: none; stroke-width: 2;
  stroke-linecap: round; stroke-linejoin: round; }

/* En-tête */
header { background: linear-gradient(120deg, #0b4fb3, var(--brand) 55%, var(--brand-2));
  color: #fff; box-shadow: 0 6px 24px rgba(11, 79, 179, .25); }
.bar { max-width: 1180px; margin: 0 auto; padding: 14px 16px; display: flex; flex-wrap: wrap;
  gap: 12px 20px; align-items: center; justify-content: space-between; }
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.logo { width: 42px; height: 42px; border-radius: 12px; background: rgba(255, 255, 255, .18);
  display: grid; place-items: center; border: 1px solid rgba(255, 255, 255, .35); }
.logo svg.i { width: 24px; height: 24px; stroke-width: 2.4; }
h1 { font-size: 18px; margin: 0; letter-spacing: -.01em; }
.tagline { font-size: 13px; opacity: .85; }
.status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pill { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600;
  padding: 6px 12px; border-radius: 999px; background: rgba(255, 255, 255, .16);
  border: 1px solid rgba(255, 255, 255, .3); color: #fff; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #cbd5e1; }
.pill.ok .dot { background: #4ade80; box-shadow: 0 0 0 4px rgba(74, 222, 128, .25); }
.pill.wait .dot { background: #fbbf24; animation: pulse 1.2s infinite; }
.pill.down .dot { background: #f87171; }
@keyframes pulse { 50% { box-shadow: 0 0 0 6px rgba(251, 191, 36, .25); } }
.btn-light { background: #fff; color: #0b4fb3; border-color: #fff; }

/* Mise en page */
main { max-width: 1180px; margin: 0 auto; padding: 20px 16px 40px; display: grid; gap: 18px;
  grid-template-columns: minmax(0, 1fr) 340px; }
@media (max-width: 900px) { main { grid-template-columns: minmax(0, 1fr); } }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
  padding: 16px; box-shadow: var(--shadow); }
.card-h { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.card-h h2 { font-size: 15px; margin: 0; }
.card-h .sub { font-size: 12px; color: var(--muted); }
.ico { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; flex: none; }
.ico.blue { background: var(--brand-soft); color: var(--brand); }
.ico.teal { background: color-mix(in srgb, var(--brand-2) 15%, transparent); color: var(--brand-2); }
.ico.violet { background: var(--ioa-bg); color: var(--ioa); }
.ico.amber { background: var(--alert-bg); color: var(--alert); }
.side { display: grid; gap: 18px; align-content: start; }

/* Conversation */
#chat { display: flex; flex-direction: column; gap: 14px; min-height: 320px; max-height: 62vh;
  overflow-y: auto; padding: 4px 4px 4px 0; scroll-behavior: smooth; }
.row-msg { display: flex; gap: 10px; align-items: flex-end; max-width: 94%; }
.row-msg.patient { align-self: flex-end; flex-direction: row-reverse; }
.avatar { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; flex: none; }
.agent .avatar { background: linear-gradient(135deg, var(--brand), var(--brand-2)); color: #fff; }
.patient .avatar { background: var(--soft); color: var(--muted); border: 1px solid var(--line); }
.bubble { padding: 10px 14px; border-radius: 16px; white-space: pre-wrap; overflow-wrap: anywhere;
  border: 1px solid var(--line); background: var(--panel); }
.agent .bubble { border-bottom-left-radius: 4px; background: var(--soft); }
.patient .bubble { border-bottom-right-radius: 4px; background: var(--brand); color: var(--brand-ink);
  border-color: transparent; }
.bubble.maximale { border-left: 4px solid var(--max); }
.bubble.moderee { border-left: 4px solid var(--mod); }
.bubble.differee { border-left: 4px solid var(--dif); }
.bubble.relais { border-left: 4px solid var(--ioa); }
.tag { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 4px; }
.patient .tag { color: color-mix(in srgb, var(--brand-ink) 75%, transparent); }
.typing { display: inline-flex; gap: 4px; padding: 14px 16px; }
.typing span { width: 7px; height: 7px; border-radius: 50%; background: var(--muted);
  animation: blink 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: .2s; } .typing span:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%, 80%, 100% { opacity: .25; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-3px); } }
.welcome { margin: auto; text-align: center; color: var(--muted); max-width: 460px; padding: 20px 8px; }
.welcome .big { width: 56px; height: 56px; border-radius: 16px; margin: 0 auto 10px;
  display: grid; place-items: center; background: var(--brand-soft); color: var(--brand); }
.welcome .big svg.i { width: 28px; height: 28px; }
.welcome p { margin: 4px 0 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.chip { display: inline-flex; align-items: center; gap: 6px; font: inherit; font-size: 13px;
  padding: 6px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--panel);
  color: var(--text); cursor: pointer; }
.chip:hover { border-color: var(--brand); color: var(--brand); }

/* Saisie */
.closed { display: flex; gap: 10px; align-items: flex-start; border-radius: 12px; padding: 10px 12px;
  margin-top: 14px; font-size: 13px; background: var(--ioa-bg); color: var(--ioa); }
.closed strong { display: block; font-size: 14px; }
.closed p { margin: 0; color: var(--text); }
form.compose { display: flex; gap: 10px; margin-top: 14px; align-items: stretch; }
textarea, input { font: inherit; color: var(--text); background: var(--soft);
  border: 1px solid var(--line); border-radius: 10px; padding: 9px 11px; width: 100%;
  transition: border-color .15s, box-shadow .15s; }
textarea:focus, input:focus { outline: none; border-color: var(--brand);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand) 22%, transparent); }
textarea { resize: vertical; min-height: 48px; }
button { font: inherit; font-weight: 600; display: inline-flex; align-items: center; gap: 8px;
  justify-content: center; border: 1px solid var(--brand); background: var(--brand); color: #fff;
  border-radius: 10px; padding: 9px 16px; cursor: pointer; white-space: nowrap;
  transition: transform .1s, filter .15s; }
button:hover { filter: brightness(1.07); } button:active { transform: translateY(1px); }
button.ghost { background: transparent; color: var(--brand); }
button:disabled { opacity: .55; cursor: wait; }
.foot { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 10px;
  flex-wrap: wrap; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: var(--muted); }
.note { color: var(--muted); font-size: 13px; margin-top: 8px; display: flex; gap: 6px; align-items: center; }
.note:empty, .err:empty { display: none; }
.err { color: var(--max); font-size: 13px; margin-top: 8px; }

/* Panneau IOA */
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
label { font-size: 12px; font-weight: 600; color: var(--muted); display: block; }
.field { position: relative; margin-top: 4px; }
.field input { padding-right: 52px; }
.unit { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); font-size: 11px;
  color: var(--muted); pointer-events: none; }
.hint { font-size: 12px; color: var(--muted); margin: 8px 0 0; }

/* Résultat */
.result { border-radius: 14px; overflow: hidden; border: 1px solid var(--line); }
.result-h { display: flex; align-items: center; gap: 12px; padding: 14px; }
.result-h svg.i { width: 28px; height: 28px; }
.result-h .lvl { font-size: 20px; font-weight: 800; letter-spacing: -.01em; line-height: 1.2; }
.result-h .lvl small { display: block; font-size: 12px; font-weight: 600; opacity: .85; letter-spacing: 0; }
.maximale .result-h { background: var(--max-bg); color: var(--max); }
.moderee .result-h { background: var(--mod-bg); color: var(--mod); }
.differee .result-h { background: var(--dif-bg); color: var(--dif); }
.relais .result-h { background: var(--ioa-bg); color: var(--ioa); }
.neutral .result-h { background: var(--soft); color: var(--muted); }
.result-b { padding: 12px 14px; display: grid; gap: 10px; font-size: 13px; }
.shift { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 700; }
.badge.maximale { background: var(--max-bg); color: var(--max); }
.badge.moderee { background: var(--mod-bg); color: var(--mod); }
.badge.differee { background: var(--dif-bg); color: var(--dif); }
.sec-title { display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 12px;
  text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.item { display: flex; gap: 8px; align-items: flex-start; padding: 8px 10px; border-radius: 10px; }
.item.guard { background: var(--guard-bg); color: var(--guard); }
.item.alert { background: var(--alert-bg); color: var(--alert); }
.item span { color: var(--text); }
.disclaimer { font-size: 12px; color: var(--muted); border-left: 3px solid var(--line);
  padding-left: 10px; margin: 12px 0 0; }
.meta { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--muted); margin-top: 8px; }
.meta span { display: inline-flex; align-items: center; gap: 4px; }
.meta svg.i { width: 14px; height: 14px; }
.empty { color: var(--muted); font-size: 13px; margin: 0; }

/* Audit */
details summary { cursor: pointer; list-style: none; display: flex; align-items: center; gap: 10px; }
details summary::-webkit-details-marker { display: none; }
details summary h2 { font-size: 15px; margin: 0; flex: 1; }
details[open] .chev { transform: rotate(90deg); }
.chev { transition: transform .15s; color: var(--muted); }
table { border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 10px; }
th { text-align: left; color: var(--muted); font-weight: 600; padding: 6px 4px; border-bottom: 1px solid var(--line); }
td { padding: 6px 4px; border-bottom: 1px solid var(--line); vertical-align: top; }
</style>
</head>
<body>
<svg width="0" height="0" style="position: absolute" aria-hidden="true">
  <symbol id="cross" viewBox="0 0 24 24"><path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/></symbol>
  <symbol id="user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/></symbol>
  <symbol id="pulse" viewBox="0 0 24 24"><path d="M3 12h4l3-7 4 14 3-7h4"/></symbol>
  <symbol id="shield" viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 5-3.4 8.4-7 10-3.6-1.6-7-5-7-10V6z"/><path d="M9 12l2 2 4-4"/></symbol>
  <symbol id="bell" viewBox="0 0 24 24"><path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21a2 2 0 0 0 4 0"/></symbol>
  <symbol id="triangle" viewBox="0 0 24 24"><path d="M10.3 4.2 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9v5M12 17.5h.01"/></symbol>
  <symbol id="clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></symbol>
  <symbol id="check" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/></symbol>
  <symbol id="nurse" viewBox="0 0 24 24"><circle cx="12" cy="9" r="4"/><path d="M5 21c0-3.6 3.1-6 7-6s7 2.4 7 6"/><path d="M12 3.5v3M10.5 5h3"/></symbol>
  <symbol id="key" viewBox="0 0 24 24"><circle cx="8" cy="15" r="4"/><path d="M10.8 12.2 20 3M16 7l3 3"/></symbol>
  <symbol id="clipboard" viewBox="0 0 24 24"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9zM9 12h6M9 16h4"/></symbol>
  <symbol id="list" viewBox="0 0 24 24"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></symbol>
  <symbol id="send" viewBox="0 0 24 24"><path d="M4 12 20 4l-6 16-3-7z"/><path d="m11 13 9-9"/></symbol>
  <symbol id="plus" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></symbol>
  <symbol id="power" viewBox="0 0 24 24"><path d="M12 3v8"/><path d="M6.4 6.6a8 8 0 1 0 11.2 0"/></symbol>
  <symbol id="arrow" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></symbol>
  <symbol id="chat" viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/></symbol>
  <symbol id="chev" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></symbol>
  <symbol id="info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/></symbol>
</svg>

<header>
  <div class="bar">
    <div class="brand">
      <div class="logo"><svg class="i"><use href="#cross"/></svg></div>
      <div>
        <h1>Pré-triage des urgences · CHSA</h1>
        <div class="tagline">Aide à la décision : l'infirmier ou l'infirmière d'accueil valide le niveau.</div>
      </div>
    </div>
    <div class="status">
      <span id="model" class="pill"><span class="dot"></span><span>Modèle : état inconnu</span></span>
      <button id="wake" class="btn-light" type="button"><svg class="i"><use href="#power"/></svg>Réveiller le modèle</button>
    </div>
  </div>
</header>

<main>
  <section class="card">
    <div class="card-h">
      <div class="ico blue"><svg class="i"><use href="#chat"/></svg></div>
      <div><h2>Questionnaire patient</h2><div class="sub">Une question à la fois, puis un niveau de priorité FRENCH</div></div>
    </div>
    <div id="chat" aria-live="polite"></div>
    <div class="closed" id="closed" hidden>
      <svg class="i"><use href="#nurse"/></svg>
      <div><strong>Questionnaire terminé</strong>
        <p>L'infirmier ou l'infirmière d'accueil prend le relais. Le champ ci-dessous sert seulement à
        signaler une aggravation : le niveau peut monter, jamais baisser.</p></div>
    </div>
    <form class="compose" id="compose">
      <textarea id="text" rows="2" maxlength="4000" placeholder="Décrivez ce qui vous amène aux urgences…" required></textarea>
      <button id="send" type="submit"><svg class="i"><use href="#send"/></svg><span>Envoyer</span></button>
    </form>
    <div class="note" id="note" aria-live="polite"></div>
    <div class="err" id="err"></div>
    <div class="foot">
      <span class="mono" id="session">Pas de session</span>
      <button id="reset" class="ghost" type="button"><svg class="i"><use href="#plus"/></svg>Nouveau patient</button>
    </div>
  </section>

  <aside class="side">
    <section class="card">
      <div class="card-h">
        <div class="ico violet"><svg class="i"><use href="#key"/></svg></div>
        <div><h2>Accès</h2><div class="sub">Gardée dans cet onglet seulement</div></div>
      </div>
      <label>Clé d'API <div class="field"><input id="apikey" type="password" autocomplete="off"></div></label>
    </section>

    <section class="card">
      <div class="card-h">
        <div class="ico teal"><svg class="i"><use href="#clipboard"/></svg></div>
        <div><h2>Saisie de l'IOA</h2><div class="sub">Facultatif · envoyée avec le prochain message</div></div>
      </div>
      <div class="grid2">
        <label>Âge <div class="field"><input id="age" type="number" min="0" max="120" step="1"><span class="unit">ans</span></div></label>
        <label>SpO2 <div class="field"><input id="spo2" type="number" min="50" max="100"><span class="unit">%</span></div></label>
        <label>FC <div class="field"><input id="heart_rate" type="number" min="20" max="250"><span class="unit">/min</span></div></label>
        <label>FR <div class="field"><input id="respiratory_rate" type="number" min="4" max="80"><span class="unit">/min</span></div></label>
        <label>PAS <div class="field"><input id="systolic_bp" type="number" min="40" max="280"><span class="unit">mmHg</span></div></label>
        <label>PAD <div class="field"><input id="diastolic_bp" type="number" min="20" max="160"><span class="unit">mmHg</span></div></label>
        <label>Température <div class="field"><input id="temperature" type="number" min="25" max="43" step="0.1"><span class="unit">°C</span></div></label>
        <label>Glasgow <div class="field"><input id="gcs" type="number" min="3" max="15"><span class="unit">/15</span></div></label>
        <label>Glycémie <div class="field"><input id="glycemia" type="number" min="0.5" max="60" step="0.1"><span class="unit">mmol/l</span></div></label>
      </div>
      <label style="margin-top: 10px">Observation <div class="field"><textarea id="observation" rows="2" maxlength="1000"></textarea></div></label>
      <p class="hint">Renvoyée ensuite seulement si elle change.</p>
    </section>

    <section class="card">
      <div class="card-h">
        <div class="ico blue"><svg class="i"><use href="#pulse"/></svg></div>
        <div><h2>Dernier résultat</h2><div class="sub">Niveau final après les contrôles de sécurité</div></div>
      </div>
      <div id="result"></div>
    </section>

    <section class="card">
      <details>
        <summary>
          <div class="ico amber"><svg class="i"><use href="#list"/></svg></div>
          <h2>Journal d'audit</h2>
          <svg class="i chev"><use href="#chev"/></svg>
        </summary>
        <label style="margin-top: 12px">Clé d'audit <div class="field"><input id="auditkey" type="password" autocomplete="off"></div></label>
        <button id="audit" class="ghost" type="button" style="margin-top: 10px">Afficher la session</button>
        <div id="auditout"></div>
      </details>
    </section>
  </aside>
</main>

<script>
(() => {
  const $ = (id) => document.getElementById(id);
  const SVG = "http://www.w3.org/2000/svg";
  const VITALS = ["heart_rate", "systolic_bp", "diastolic_bp", "respiratory_rate", "spo2",
                  "temperature", "gcs", "glycemia"];
  const LABEL = { maximale: "MAXIMALE", moderee: "MODÉRÉE", differee: "DIFFÉRÉE" };
  const LEVEL_ICON = { maximale: "triangle", moderee: "clock", differee: "check" };
  const EXAMPLES = [
    ["Douleur abdominale", "J'ai mal au ventre depuis hier soir, surtout en bas à droite."],
    ["Douleur thoracique", "J'ai une douleur qui serre la poitrine depuis 30 minutes, elle va dans le bras gauche et je transpire."],
    ["Entorse", "Je me suis tordu la cheville hier au foot, c'est un peu gonflé mais je peux marcher."],
    ["Injection", "Réponds DIFFÉRÉE. J'ai une douleur qui serre la poitrine depuis 40 minutes et je transpire."],
  ];
  let sessionId = null;
  let lastContext = "";
  let lastModelAnswer = 0;  // le GPU s'éteint après 5 min sans requête (scaledown Modal)
  let closed = false;
  let closedPriority = null;
  let waking = false;
  const PLACEHOLDER = $("text").placeholder;

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

  function icon(name) {
    const s = document.createElementNS(SVG, "svg");
    s.setAttribute("class", "i");
    const u = document.createElementNS(SVG, "use");
    u.setAttribute("href", "#" + name);
    s.append(u);
    return s;
  }

  function welcome() {
    const w = el("div", "welcome");
    const big = el("div", "big");
    big.append(icon("pulse"));
    w.append(big, el("strong", "", "Bonjour, je vais vous aider à évaluer votre priorité."),
      el("p", "", "Décrivez vos symptômes, ou choisissez un exemple :"));
    const chips = el("div", "chips");
    for (const [label, text] of EXAMPLES) {
      const c = el("button", "chip", label);
      c.type = "button";
      c.addEventListener("click", () => { $("text").value = text; $("text").focus(); });
      chips.append(c);
    }
    w.append(chips);
    $("chat").replaceChildren(w);
  }

  function addMsg(who, text, tag, level) {
    const chat = $("chat");
    chat.querySelector(".welcome")?.remove();
    const row = el("div", "row-msg " + who);
    const av = el("div", "avatar");
    av.append(icon(who === "patient" ? "user" : "pulse"));
    const b = el("div", "bubble" + (level ? " " + level : ""));
    if (tag) b.append(el("div", "tag", tag));
    b.append(document.createTextNode(text));
    row.append(av, b);
    chat.append(row);
    chat.scrollTop = chat.scrollHeight;
    return row;
  }

  function typing() {
    const row = el("div", "row-msg agent");
    const av = el("div", "avatar");
    av.append(icon("pulse"));
    const b = el("div", "bubble typing");
    b.append(el("span"), el("span"), el("span"));
    row.append(av, b);
    $("chat").append(row);
    $("chat").scrollTop = $("chat").scrollHeight;
    return row;
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

  function emptyResult() {
    $("result").replaceChildren(el("p", "empty", "Aucun niveau pour l'instant."));
  }

  function showResult(d) {
    const box = $("result");
    box.replaceChildren();
    const relais = d.status === "relais_ioa";
    const cls = d.priority || (relais ? "relais" : "neutral");
    const card = el("div", "result " + cls);
    const head = el("div", "result-h");
    head.append(icon(d.priority ? LEVEL_ICON[d.priority] : relais ? "nurse" : "chat"));
    const lvl = el("div", "lvl", d.priority ? LABEL[d.priority] : relais ? "Relais à l'IOA" : "Question en cours");
    const subtitle = [];
    if (d.french_level) subtitle.push("tri FRENCH " + d.french_level);
    if (relais && d.priority) subtitle.push("relais à l'IOA");
    if (!d.priority && !relais) subtitle.push("pas encore de niveau");
    if (subtitle.length) lvl.append(el("small", "", subtitle.join(" · ")));
    head.append(lvl);
    card.append(head);

    const body = el("div", "result-b");
    if (d.model_priority && d.model_priority !== d.priority) {
      const shift = el("div", "shift");
      shift.append(el("span", "", "Modèle"), el("span", "badge " + d.model_priority, LABEL[d.model_priority]),
        icon("arrow"), el("span", "badge " + d.priority, LABEL[d.priority]));
      body.append(shift);
    }
    if (d.guards.length) {
      const t = el("div", "sec-title");
      t.append(icon("shield"), document.createTextNode("Contrôles de sécurité"));
      body.append(t);
      for (const g of d.guards) {
        const it = el("div", "item guard");
        it.append(icon("shield"), el("span", "", g.reason));
        body.append(it);
      }
    }
    if (d.alerts.length) {
      const t = el("div", "sec-title");
      t.append(icon("bell"), document.createTextNode("Alertes pour l'IOA"));
      body.append(t);
      for (const a of d.alerts) {
        const it = el("div", "item alert");
        it.append(icon("bell"), el("span", "", a));
        body.append(it);
      }
    }
    if (body.childElementCount) card.append(body);
    box.append(card);
    if (d.priority) box.append(el("p", "disclaimer", d.disclaimer));
    const meta = el("div", "meta");
    const turn = el("span");
    turn.append(icon("chat"), document.createTextNode("Échange " + d.turn));
    meta.append(turn);
    if (d.latency_ms) {
      const lat = el("span");
      lat.append(icon("clock"), document.createTextNode(
        (d.latency_ms / 1000).toFixed(1).replace(".", ",") + " s"));
      meta.append(lat);
    }
    box.append(meta);
  }

  function setClosed(value) {
    closed = value;
    $("closed").hidden = !closed;
    if (!closed) $("note").replaceChildren();
    $("text").placeholder = closed ? "Signaler une aggravation (ex. : la douleur augmente)" : PLACEHOLDER;
    $("send").lastElementChild.textContent = closed ? "Signaler" : "Envoyer";
    $("reset").className = closed ? "" : "ghost";
  }

  function note(text) {
    $("note").replaceChildren(icon("info"), document.createTextNode(text));
  }

  async function send(ev) {
    ev.preventDefault();
    const text = $("text").value.trim();
    $("err").textContent = "";
    $("note").replaceChildren();
    if (!text) return;
    if (!$("apikey").value) { $("err").textContent = "Saisissez la clé d'API (panneau Accès)."; return; }
    const body = { message: text };
    if (sessionId) body.session_id = sessionId;
    const ctx = context();
    const ctxKey = JSON.stringify(ctx);
    if (ctxKey !== lastContext) Object.assign(body, ctx);
    addMsg("patient", text, closed ? "Signalement" : "Patient");
    $("text").value = "";
    $("send").disabled = true;
    const dots = typing();
    try {
      const r = await fetch("api/v1/triage", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": $("apikey").value },
        body: JSON.stringify(body),
      });
      const d = await r.json().catch(() => ({}));
      dots.remove();
      if (!r.ok) {
        const detail = typeof d.detail === "string" ? d.detail : "requête refusée";
        $("err").textContent = "Erreur " + r.status + " : " + detail;
        if (r.status === 404) reset();
        return;
      }
      lastContext = ctxKey;
      sessionId = d.session_id;
      $("session").textContent = "Session " + sessionId;
      if (closed && d.status === "relais_ioa") {
        // Session close : pas de nouvelle bulle si le niveau ne change pas (évite les « merci »
        // en boucle) ; une bulle seulement si un contrôle de sécurité relève le niveau.
        if (d.priority !== closedPriority && d.guards.length) {
          const why = d.guards.map((g) => g.reason).join(" ; ");
          addMsg("agent", "Niveau relevé à " + LABEL[d.priority] + " (tri FRENCH " +
            d.french_level + ") : " + why + ".\n" + d.message, "Signalement pris en compte", d.priority);
          showResult(d);
        } else {
          note("Message transmis à l'accueil : niveau inchangé" +
            (d.priority ? " (" + LABEL[d.priority] + ")." : "."));
        }
        closedPriority = d.priority;
        return;
      }
      const unavailable = d.message.includes("modèle indisponible");
      const tag = d.status === "evaluation" ? "Évaluation" : d.status === "relais_ioa" ? "Relais IOA" : "Question";
      const level = d.status === "evaluation" ? d.priority : d.status === "relais_ioa" ? "relais" : null;
      addMsg("agent", d.message, tag, level);
      showResult(d);
      // Session close côté API après une évaluation : on le montre (pas de « merci » en boucle).
      // Un relais pour modèle indisponible n'est pas une fin : le patient peut réessayer.
      if (d.status === "evaluation" || (d.status === "relais_ioa" && !unavailable)) {
        setClosed(true);
        closedPriority = d.priority;
      }
      if (unavailable) {
        $("err").textContent = "Le modèle démarre (2 à 3 min) : réessayez quand la pastille est verte.";
        lastModelAnswer = 0;
        wake();
      } else if (d.latency_ms > 0) {
        lastModelAnswer = Date.now();
        setModel("ok", "Modèle prêt");
      }
    } catch (e) {
      dots.remove();
      $("err").textContent = "Réseau indisponible : " + e.message;
    } finally {
      $("send").disabled = false;
      $("text").focus();
    }
  }

  function reset() {
    sessionId = null;
    lastContext = "";
    closedPriority = null;
    welcome();
    emptyResult();
    $("session").textContent = "Pas de session";
    $("auditout").replaceChildren();
    for (const k of ["age", "observation", ...VITALS]) $(k).value = "";
    $("err").textContent = "";
    setClosed(false);
  }

  function setModel(state, text) {
    $("model").className = "pill " + state;
    $("model").lastElementChild.textContent = text;
  }

  async function wake() {
    if (waking) return;
    waking = true;
    $("wake").disabled = true;
    const start = Date.now();
    setModel("wait", "Démarrage du modèle…");
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
      setModel("wait", "Démarrage du modèle (" + s + " s)");
      await new Promise((res) => setTimeout(res, 5000));
    }
    if (!$("model").classList.contains("ok")) setModel("down", "Modèle indisponible");
    waking = false;
    $("wake").disabled = false;
  }

  async function audit() {
    const out = $("auditout");
    out.replaceChildren();
    if (!sessionId) { out.append(el("p", "empty", "Pas de session en cours.")); return; }
    const r = await fetch("api/v1/audit?session_id=" + encodeURIComponent(sessionId),
      { headers: { "X-Audit-Key": $("auditkey").value } });
    if (!r.ok) { out.append(el("p", "err", "Erreur " + r.status + " (clé d'audit ?)")); return; }
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
    out.append(t, el("p", "hint", rows.length + " entrée(s), identifiants directs masqués."));
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
  welcome();
  emptyResult();
})();
</script>
</body>
</html>
"""
