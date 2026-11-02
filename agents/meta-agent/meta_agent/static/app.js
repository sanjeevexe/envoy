// The page: one event stream from the agent (/api/events), drawn as the conversation and the feed of MCP calls.
"use strict";

const $ = (id) => document.getElementById(id);
const convo = $("convo"), feed = $("feed"), toolsBox = $("tools"), dock = $("dock");
const state = { rows: {}, waits: {}, tools: new Map(), used: new Set(), busy: false, thinking: null, config: {}, stats: {}, lastN: -1, showAll: false, flash: null };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function md(text) {
  // Just enough markdown for a model's reply: paragraphs, bullet lists, **bold**, `code`. Escaped first.
  const inline = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = [];
  let list = null;
  for (const line of String(text).split("\n")) {
    const m = line.match(/^\s*[-*•]\s+(.*)$/);
    if (m) { (list ||= []).push(`<li>${inline(m[1])}</li>`); continue; }
    if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; }
    if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push(`<ul>${list.join("")}</ul>`);
  return out.join("");
}

function dur(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

function args(a) {
  if (!a || !Object.keys(a).length) return "";
  return Object.entries(a).map(([k, v]) => `${k}: ${typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v)}`).join(", ");
}

// Keep a column pinned to its newest line unless the viewer scrolled up.
function stick(el, fn) {
  const replay = document.body.classList.contains("replay");
  const atEnd = replay || el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  fn();
  if (atEnd) {
    if (replay) { el.style.scrollBehavior = "auto"; el.scrollTop = el.scrollHeight; el.style.scrollBehavior = ""; }
    else requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
  }
}

const MINI = `<svg class="mini" viewBox="0 0 48 48" width="40" height="40" aria-hidden="true"><rect width="48" height="48" rx="14" fill="#1F2A24"/><path d="M24 9c1.6 8.4 6.6 13.4 15 15-8.4 1.6-13.4 6.6-15 15-1.6-8.4-6.6-13.4-15-15 8.4-1.6 13.4-6.6 15-15Z" fill="#F6F3EC"/></svg>`;
const SPARK = `<svg viewBox="0 0 48 48" width="16" height="16" aria-hidden="true"><path d="M24 4c2 10.5 9.5 18 20 20-10.5 2-18 9.5-20 20-2-10.5-9.5-18-20-20C14.5 22 22 14.5 24 4Z" fill="#5F6A63"/></svg>`;
const CHECK = `<svg class="ic" width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style="stroke-width:3"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>`;
const CROSS = `<svg class="ic" width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" style="stroke-width:3"><path d="M6 6l12 12M18 6L6 18"/></svg>`;
const SPIN = `<svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="none" stroke="#E4EEE7" stroke-width="3"/><path class="spin" d="M12 2a10 10 0 0 1 10 10" fill="none" stroke="#3E7C5C" stroke-width="3" stroke-linecap="round"/></svg>`;
const LOCK = `<svg class="ic" width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/></svg>`;
const PHONE = `<svg class="ic" width="17" height="17" viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/></svg>`;

function emptyGone() { const e = $("empty"); if (e) e.remove(); }

function addMsg(kind, html) {
  emptyGone();
  const el = document.createElement("div");
  el.className = `msg ${kind}`;
  el.innerHTML = html;
  stick(convo, () => { if (state.thinking) convo.insertBefore(el, state.thinking); else convo.appendChild(el); });
  return el;
}

function setThinking(on) {
  if (on && !state.thinking) {
    const el = document.createElement("div");
    el.className = "thinking";
    el.innerHTML = `<i></i><i></i><i></i><span>Thinking on ${esc(state.config.model || "Meta's model")}</span>`;
    state.thinking = el;
    stick(convo, () => convo.appendChild(el));
  } else if (!on && state.thinking) {
    state.thinking.remove();
    state.thinking = null;
  }
}

function setBusy(on) {
  state.busy = on;
  $("send").disabled = on;
  $("stop").hidden = !on;
}

function drawTools() {
  // Learned routines first: they're what an agent gains from Envoy. Envoy's own tools fold into one chip once there are any.
  const all = [...state.tools.values()];
  const routines = all.filter((t) => t.routine), builtins = all.filter((t) => !t.routine);
  const folded = routines.length > 0 && !state.showAll;
  toolsBox.innerHTML = "";
  const chip = (t) => {
    const el = document.createElement("span");
    el.className = `tool-chip${t.routine ? " routine" : ""}${t.fresh ? " new" : ""}${state.used.has(t.name) ? " used" : ""}${state.flash === t.name ? " flash" : ""}`;
    el.title = t.title || t.name;
    el.innerHTML = `<span class="tname">${esc(t.name)}</span>${t.routine ? ` <span class="tag">learned</span>` : ""}`;
    toolsBox.appendChild(el);
  };
  routines.forEach(chip);
  if (folded) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "tool-chip more";
    b.title = builtins.map((t) => t.name).join(", ");
    b.textContent = `+ ${builtins.length} Envoy tools`;
    b.onclick = () => { state.showAll = true; drawTools(); };
    toolsBox.appendChild(b);
  } else {
    builtins.forEach(chip);
    if (routines.length) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "tool-chip more"; b.textContent = "fewer";
      b.onclick = () => { state.showAll = false; drawTools(); };
      toolsBox.appendChild(b);
    }
  }
}

function row(id, html, cls) {
  let el = state.rows[id];
  if (!el) {
    el = document.createElement("div");
    state.rows[id] = el;
    stick(feed, () => feed.appendChild(el));
  }
  el.className = `row ${cls}`;
  el.innerHTML = html;
  return el;
}

function rowHtml(r) {
  const icon = r.done ? (r.ok ? CHECK : CROSS) : SPIN;
  const many = r.tasks > 1 ? ` · ${r.tasks} tasks` : "";
  const via = r.via === "wait_for_task" ? `<span class="via">wait_for_task${many} · ${r.polls || 1} ${r.polls === 1 ? "call" : "calls"}</span>`
    : r.via === "watch" ? `<span class="via">watching · ${r.polls || 1} ${r.polls === 1 ? "call" : "calls"}</span>`
    : r.polls > 1 ? `<span class="via">${r.polls} calls</span>` : "";
  const tag = r.routine || r.tool === "run_routine" ? `<span class="routine-tag">learned routine</span>` : "";
  const time = r.done ? dur(r.ms) : dur(Date.now() - r.start);
  return `<span class="st">${icon}</span><span class="name"><span class="tname">${esc(r.tool)}</span>${tag}${via}</span><span class="ms" data-start="${r.done ? "" : r.start}">${time}</span>`
    + `<span class="args">${esc(r.args)}</span><span class="res">${esc(r.summary || (r.done ? "" : "waiting for Envoy…"))}</span>`;
}

const rowsData = {};
function drawRow(id) {
  const r = rowsData[id];
  row(id, rowHtml(r), `${r.done ? (r.ok ? "ok" : "bad") : "pending"}${r.rpc ? " rpc" : ""}`);
}

// Envoy waiting for the user: a card in the dock above the feed (always in view, stacked when several tasks wait), a line
// in the feed where it happened, and a pill in the conversation. An offer (a file for the real phone, a trigger to turn
// on) is only a card in the feed: nothing here can follow it.
function waitCard(d, t) {
  const el = document.createElement("div");
  el.className = `wait${d.kind === "offer" ? " offer" : ""}`;
  const kicker = d.kind === "approval" ? "Waiting for your OK on your phone" : d.kind === "needs_you" ? "Envoy needs you on your phone" : "Envoy asked you";
  const why = d.kind === "offer" ? `${PHONE}<span>It's in Envoy, waiting for your answer. The agent can't answer it for you.</span>`
    : `${PHONE}<span>Only you can approve, in Envoy on your phone. The agent has no approve tool.</span>`;
  el.innerHTML = `<div class="av">${$(d.kind === "offer" ? "avatar-idle" : "avatar-needs").innerHTML}</div>`
    + `<div class="kicker">${esc(kicker)}</div><div class="timer" data-start="${d.kind === "offer" ? "" : t * 1000}"></div>`
    + `<div class="title">${esc(d.title)}${d.goal ? `<span class="goal">${esc(d.goal)}</span>` : ""}</div><div class="why">${why}</div>`;
  return el;
}

function dockLayout() {
  dock.classList.toggle("multi", dock.querySelectorAll(".wait:not(.leaving)").length > 1);
}

function openWait(d, t) {
  if (d.kind === "offer") {
    const el = waitCard(d, t);
    stick(feed, () => feed.appendChild(el));
    state.waits[d.key] = { card: el };
    return;
  }
  const card = waitCard(d, t);
  dock.appendChild(card);
  dockLayout();
  const line = document.createElement("div");
  line.className = "asked";
  line.innerHTML = `${PHONE}<span class="what">Asked you on your phone: <b>${esc(d.title)}</b></span><span class="state" data-start="${t * 1000}"></span>`;
  stick(feed, () => feed.appendChild(line));
  const pill = addMsg("note needs", `${PHONE}<span>Envoy is waiting for your OK on your phone</span><span class="t" data-start="${t * 1000}"></span>`);
  state.waits[d.key] = { card, line, pill };
}

function closeWait(d) {
  const w = state.waits[d.key];
  if (!w) return;
  delete state.waits[d.key];
  const yes = d.outcome === "done" || d.outcome === "answered";
  const said = yes ? "Approved on your phone" : d.outcome === "declined" ? "You said no on your phone" : `The task ${d.outcome}`;
  const el = w.card;
  el.classList.add("closed");
  if (!yes) el.classList.add("no");
  el.querySelector(".av").innerHTML = $(yes ? "avatar-done" : "avatar-idle").innerHTML;
  el.querySelector(".kicker").textContent = said;
  const timer = el.querySelector(".timer");
  timer.dataset.start = "";
  timer.textContent = dur(d.after_s * 1000);
  el.querySelector(".why").innerHTML = `${PHONE}<span>${esc(d.text || "")}</span>`;
  if (w.line) {
    w.line.classList.add("closed");
    if (!yes) w.line.classList.add("no");
    const st = w.line.querySelector(".state");
    st.dataset.start = "";
    st.textContent = `${yes ? "approved" : d.outcome === "declined" ? "declined" : d.outcome} · ${dur(d.after_s * 1000)}`;
  }
  if (w.pill) {
    w.pill.className = `msg note${yes ? "" : " no"}`;
    w.pill.innerHTML = `${PHONE}<span>${said}</span><span class="t">${dur(d.after_s * 1000)}</span>`;
  }
  if (el.parentElement === dock) {  // the answer shows for a few seconds, then the card leaves the dock
    const leave = () => { el.classList.add("leaving"); dockLayout(); setTimeout(() => { el.remove(); dockLayout(); }, 420); };
    if (document.body.classList.contains("replay")) { el.remove(); dockLayout(); } else setTimeout(leave, 5000);
  }
}

function stat(id, value) {
  const el = $(id);
  if (el.textContent !== value) {
    el.textContent = value;
    const box = el.parentElement;
    box.classList.remove("bump");
    void box.offsetWidth;
    box.classList.add("bump");
  }
}

function handle(ev) {
  const d = ev.data || {};
  if (ev.n >= 0) {
    if (ev.n <= state.lastN) { if (ev.n === 0) location.reload(); return; }  // a reconnect replays from the start; a restarted agent starts over
    state.lastN = ev.n;
  }
  switch (ev.kind) {
    case "reset":
      location.reload();
      break;
    case "config":
      state.config = d;
      $("agent-name").textContent = d.agent;
      $("agent-model").textContent = d.model;
      document.title = `${d.agent} with Envoy`;
      $("chips").innerHTML = "";
      for (const s of d.suggestions || []) {
        const b = document.createElement("button");
        b.type = "button"; b.className = "chip"; b.textContent = s;
        b.onclick = () => send(s);
        $("chips").appendChild(b);
      }
      break;
    case "hello": {
      $("conn-dot").classList.remove("off");
      const srv = d.server || {};
      $("envoy-title").textContent = srv.title || srv.name || "Envoy";
      $("envoy-sub").textContent = `${srv.name || "envoy"} ${srv.version || ""} · ${d.envoy}`.trim();
      rowsData[`hello${ev.n}`] = { tool: "initialize", args: "", summary: `${srv.title || srv.name || "Envoy"} ${srv.version || ""}, with its instructions`, done: true, ok: true, ms: d.ms, rpc: true };
      drawRow(`hello${ev.n}`);
      break;
    }
    case "tools":
      for (const t of state.tools.values()) t.fresh = false;
      if (!d.added.length && !d.removed.length && state.tools.size) break;
      state.tools = new Map(d.tools.map((t) => [t.name, { ...t, fresh: d.added.includes(t.name) }]));
      drawTools();
      break;
    case "user":
      addMsg("user", esc(d.text));
      setBusy(true);
      break;
    case "commentary":
      addMsg("commentary", `<span>${md(d.text).replace(/<\/?p>/g, " ")}</span>`);
      break;
    case "reply":
      addMsg("reply", `${MINI}<div class="text">${md(d.text)}</div>`);
      break;
    case "thinking":
      setThinking(d.on);
      if (d.on) setBusy(true);
      break;
    case "model_call": {
      const el = document.createElement("div");
      el.className = "model-row";
      const tokens = (d.input_tokens || 0) + (d.output_tokens || 0);
      el.innerHTML = `${SPARK}<span><b>${esc(d.model)}</b> · ${dur(d.ms)} · ${tokens.toLocaleString()} tokens${d.cached_tokens ? ` (${d.cached_tokens.toLocaleString()} cached)` : ""} · $${(d.cost_usd || 0).toFixed(4)}</span>`;
      stick(feed, () => feed.appendChild(el));
      break;
    }
    case "stats":
      state.stats = d;
      stat("s-model", String(d.model_calls));
      stat("s-mcp", String(d.mcp_calls));
      stat("s-cost", `$${(d.cost_usd || 0).toFixed(3)}`);
      break;
    case "call_start": {
      const routine = state.tools.get(d.tool)?.routine;
      rowsData[d.id] = { tool: d.tool, args: args(d.args), via: d.via, rpc: d.rpc, start: ev.t * 1000, done: false, routine,
                         tasks: (d.args && d.args.task_ids) ? d.args.task_ids.length : 1 };
      if (!d.rpc) {
        state.used.add(d.tool);
        if (routine) { state.flash = d.tool; setTimeout(() => { if (state.flash === d.tool) { state.flash = null; drawTools(); } }, 1600); }
        drawTools();
      }
      drawRow(d.id);
      break;
    }
    case "call_update": {
      const r = rowsData[d.id];
      if (!r) break;
      Object.assign(r, { polls: d.polls, summary: d.summary });
      drawRow(d.id);
      break;
    }
    case "call_end": {
      const r = rowsData[d.id];
      if (!r) break;
      Object.assign(r, { done: true, ok: d.ok, summary: d.summary, ms: d.ms, polls: d.polls ?? r.polls });
      drawRow(d.id);
      break;
    }
    case "waiting":
      if (state.waits[d.key]) state.waits[d.key].card.querySelector(".title").firstChild.textContent = d.title;
      else openWait(d, ev.t);
      break;
    case "waiting_end":
      closeWait(d);
      break;
    case "refusal": {
      const el = document.createElement("div");
      el.className = "refusal";
      el.innerHTML = d.approval
        ? `<div class="lock">${LOCK}</div><div class="kicker">Envoy has no approve tool</div><div class="quote">“${esc(d.rule)}”</div>`
          + `<div class="what">The agent called <b>${esc(d.tool)}</b>. Envoy answered: ${esc(d.envoy)}</div>`
        : `<div class="lock">${LOCK}</div><div class="kicker">Envoy refused</div><div class="quote">“${esc(d.envoy)}”</div>`
          + `<div class="what">The agent called <b>${esc(d.tool)}</b>, which isn't in its tool list.</div>`;
      stick(feed, () => feed.appendChild(el));
      break;
    }
    case "envoy_update":
      addMsg("note", `${PHONE}<span>Envoy says the task ${{ done: "finished", declined: "was declined", failed: "failed", stopped: "was stopped" }[d.status] || `is ${esc(d.status)}`}</span>`);
      break;
    case "error":
      addMsg("error", esc(d.text));
      break;
    case "stopped":
      addMsg("note", "Stopped");
      break;
    case "idle":
      setBusy(false);
      setThinking(false);
      break;
    default:
      break;
  }
}

function tick() {
  for (const el of document.querySelectorAll("[data-start]")) {
    const start = Number(el.dataset.start);
    if (start) el.textContent = dur(Date.now() - start);
  }
}
setInterval(tick, 250);

async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  return r;
}

async function send(text) {
  text = (text || "").trim();
  if (!text || state.busy) return;
  $("text").value = "";
  const r = await post("/api/chat", { text });
  if (r.status === 409) addMsg("error", "The agent is still working on the last message.");
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); send($("text").value); });
$("stop").addEventListener("click", () => post("/api/stop"));
$("reset").addEventListener("click", () => post("/api/reset"));

// What the stream replays on load (the session so far) appears at once; only what happens after it animates in.
document.body.classList.add("replay");
const es = new EventSource("/api/events");
es.onopen = () => setTimeout(() => {
  document.body.classList.remove("replay");
  for (const el of [convo, feed]) { el.style.scrollBehavior = "auto"; el.scrollTop = el.scrollHeight; el.style.scrollBehavior = ""; }
}, 700);
es.onmessage = (m) => handle(JSON.parse(m.data));
es.onerror = () => $("conn-dot").classList.add("off");
