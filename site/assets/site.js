// Envoy's showcase: renders every section from window.ENVOY (data/site-data.js, built by scripts/build_site_data.py).
// No network calls; works from file:// and any static host.
(function () {
  "use strict";
  const D = window.ENVOY;
  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const repoBase = D.meta.repo_url || "../";

  // ---- formatting ----
  const commit = (c) => esc(c).replace(/, here (\w+)/, " (loop A's branch $1)");
  const usd = (x) => "$" + (x >= 0.1 ? x.toFixed(2) : x.toFixed(4).replace(/0+$/, "").replace(/\.$/, ""));
  const secs = (x) => `${(+x).toFixed(1)} s`;
  const ratio = (a, b) => { const r = a / b; return r >= 10 ? Math.round(r) : Math.round(r * 10) / 10; };
  const MODEL = { "muse-wonder-1.0": "Muse Wonder", "muse-spark-1.3": "Muse Spark 1.3", "muse-spark-1.3-contributor": "Muse Spark 1.3" };
  const JOB = { match: "match the request to a routine", plan: "plan", step: "decide a step", extract: "read the answer for memory", app_note: "write app notes", compile: "compile" };
  const date = (s) => {
    const d = new Date(s.replace(" ", "T"));
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) + ", " + s.slice(11, 16) + " ET";
  };
  // A source link: the file a number came from, relative to the repo.
  const srcA = (s, label) => s ? `<a class="src" href="${esc(repoBase + s.path)}" title="${esc(s.note || "")}">${esc(label || s.path)}</a>` : "";
  const slots = (t) => esc(t).replace(/\{\{(\w+)\}\}/g, '<span class="slot">{{$1}}</span>');

  // ---- 1: the claim ----
  function renderClaim() {
    const L = D.learned, f = L.first, r = L.replay;
    $("#proof").innerHTML = `
      <div class="card proof" role="group" aria-label="One real task, first run against replay">
        <div class="cell app"><span class="lbl">One real app</span><b>Starbucks</b><span class="meta">“${esc(f.goal.replace(/^In the Starbucks app, /, "").replace(/^./, (c) => c.toUpperCase()))}”</span></div>
        <div class="cell"><div class="lbl">First run</div><div class="val">${secs(f.seconds)} <small>· ${f.calls} model calls · ${usd(f.usd)}</small></div></div>
        <div class="arrow" aria-hidden="true">→</div>
        <div class="cell replay"><div class="lbl">Learned</div><div class="val">${secs(r.seconds)} <small>· ${r.calls} calls · ${usd(r.usd)}</small></div></div>
        <div class="proof-foot">
          <span class="chip sage">${ratio(f.seconds, r.seconds)}× faster</span>
          <span class="chip sage">${ratio(f.calls, r.calls)}× fewer model calls</span>
          <span class="chip sage">${ratio(f.usd, r.usd)}× cheaper</span>
          <span class="meta">Same request, same answer (190 calories), Oct 30 on an Android emulator.</span>
          ${srcA(f.src, "runs.jsonl")}
        </div>
      </div>`;
    const C = D.claim;
    $("#new").innerHTML = `
      <div class="prior"><span class="chip">What's new vs. existing phone agents</span><p>${esc(C.prior.replace(/:$/, "."))}</p></div>
      <div class="new-grid">
        ${C.new.map((n, i) => `<div class="card"><div class="k">${i + 1}</div><h3>${esc(n.title)}</h3><p>${esc(n.text)}</p></div>`).join("")}
      </div>
      <div class="label-rec">${srcA(C.src, "docs/technical-design.md › Overview")}</div>
      <div class="block howto">
        <span><i class="dot"></i>Every screen is a real recording, labeled with its app, date and commit.</span>
        <span><i class="dot"></i>Every number links to the file it came from.</span>
        <span><i class="dot ap"></i>SkyLark is our own test app. We say so wherever it appears, and lead with real apps.</span>
      </div>
      <div class="card" style="margin-top:16px;padding:18px 20px">
        <h3 style="font-size:17px">Limits, plainly</h3>
        <ul style="margin:8px 0 0;padding-left:18px;color:var(--ink-2);font-size:14.5px">
          <li>It runs on a Mac today (emulators plus one real Pixel 5 over USB), with a one-time sign-in per app, done by the user.</li>
          <li>Apps with bot checks (Target) don't run on emulators; they need a real phone.</li>
          <li>Real apps with new inputs, the eval's 18 workflows: 4 of 11 reruns were right with no model call on Oct 28, and 6 of 11 at the Oct 31 rehearsal on the hybrid profile (first runs 12 of 18 there). Separately, five routines shipped in the loops went 15 of 15 on new inputs (Oct 30).
            ${srcA({ path: "eval/results/final/report.md", note: "suite 4" }, "report.md")} ${srcA({ path: "eval/results/real_rerun_2026-10-31/README.md" }, "rehearsal")} ${srcA(L.table_src, "table.md")}</li>
        </ul>
      </div>`;
  }

  // ---- 2: a first run ----
  function renderFirstRun() {
    const R = D.first_run, T = R.total;
    const body = $("#first-run-body");
    body.innerHTML = `
      <span class="eyebrow"><span class="num">${num("first-run")}</span> Watch a real first run</span>
      <h2 id="first-run-h">The first time, Muse Wonder decides every tap.</h2>
      <p class="lede">There's no routine for this yet, so the agent plans the task and reads each screen as text: the app's accessibility tree, numbered. Step through the run: the screen, the element it tapped, its reason, and the time and money spent so far.</p>
      <div class="label-rec">
        <span><b>App</b> Starbucks (<code>${esc(R.package)}</code>), no account</span>
        <span><b>Phone</b> ${esc(R.device)}, an Android emulator</span>
        <span><b>Recorded</b> ${esc(date(R.started_et))}</span>
        <span><b>Commit</b> <code>${commit(T.commit)}</code></span>
        <span><b>Task</b> <code>${esc(R.task_id)}</code></span>
        <span>${srcA(R.src, "recording")} ${srcA(T.src, "runs.jsonl")}</span>
      </div>
      <div class="run">
        <div class="run-phone">
          <div class="phone" id="fr-phone"></div>
          <div class="cap" id="fr-cap"></div>
        </div>
        <div class="card stepper">
          <div class="stepper-head">
            <div class="goal">${esc(R.goal)}</div>
            <div class="ctrl">
              <button class="btn" id="fr-prev" aria-label="Previous step">←</button>
              <button class="btn primary" id="fr-play">Play</button>
              <button class="btn" id="fr-next" aria-label="Next step">→</button>
            </div>
          </div>
          <div class="plan">
            <div class="meta"><b style="color:var(--ink)">Wonder's plan</b> · 1 call, ${secs(R.plan.model_ms / 1000)}</div>
            <ol>${R.plan.subgoals.map((g) => `<li>${esc(g)}</li>`).join("")}</ol>
          </div>
          <ol class="steps" id="fr-steps">
            ${R.steps.map((s, i) => `
              <li data-i="${i}"><button type="button" aria-label="Step ${s.n}: ${esc(s.text)}">
                <span class="k">${s.n}</span>
                <span>
                  <span class="act">${s.action.type === "done" ? `Done: “${esc(s.action.result)}”` : esc(s.text.replace(/"([^"]+)"/, "“$1”"))}</span>
                  <span class="why">“${esc(s.reason)}”</span>
                  ${s.expected ? `<span class="exp">Expects: ${esc(s.expected)}</span>` : ""}
                  <span class="who" aria-hidden="true">Muse Wonder · ${s.model_ms ? (s.model_ms / 1000).toFixed(1) + " s to decide" : ""}</span>
                </span>
                <span class="t">${secs(s.t)}</span>
              </button></li>`).join("")}
          </ol>
          <div class="counters" aria-live="polite">
            <div><div class="lbl">Time</div><div class="v" id="fr-t"></div></div>
            <div><div class="lbl">Model calls</div><div class="v" id="fr-c"></div></div>
            <div><div class="lbl">Cost</div><div class="v" id="fr-u"></div></div>
          </div>
          <div class="read-toggle">
            <details class="read" id="fr-read"><summary>What Wonder read on this screen</summary><pre id="fr-tree"></pre></details>
          </div>
          <div class="after">
            <b style="color:var(--ink)">The whole run:</b> ${secs(T.seconds)} to the answer, ${T.calls} model calls, ${usd(T.usd)}.
            After the answer, Muse Spark read it out for memory and wrote ${R.app_notes.length} app notes for next time:
            <ul>${R.app_notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
            <details class="read" style="margin-top:8px"><summary>Every model call in this run</summary>
              <table class="ledger"><thead><tr><th>At</th><th>Model</th><th>Job</th><th class="r">Took</th><th class="r">Cost</th></tr></thead>
              <tbody>${R.calls.map((c) => `<tr><td>${secs(c.t)}</td><td>${esc(MODEL[c.model] || c.model)}</td><td>${esc(JOB[c.job] || c.job)}</td><td class="r">${(c.ms / 1000).toFixed(1)} s</td><td class="r">${usd(c.usd)}</td></tr>`).join("")}</tbody></table>
              <div class="small" style="margin-top:6px">From loop A's model-cost log, imported into the recording. Dollars at Meta's standard prices.</div>
            </details>
          </div>
        </div>
      </div>`;

    let i = 0, timer = null;
    const items = [...body.querySelectorAll("#fr-steps li")];
    function show(n) {
      i = Math.max(0, Math.min(R.steps.length - 1, n));
      const s = R.steps[i];
      items.forEach((li, k) => { li.classList.toggle("on", k === i); li.classList.toggle("done", k < i); });
      const ph = $("#fr-phone");
      const [W, H] = s.screen;
      const ring = s.box ? (() => {
        const p = 12, [x1, y1, x2, y2] = s.box;
        const r = `x="${x1 - p}" y="${y1 - p}" width="${x2 - x1 + 2 * p}" height="${y2 - y1 + 2 * p}" rx="28"`;
        return `<svg class="ring" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${s.box_kind === "tap"
          ? `<rect class="tap-glow" ${r}/><rect class="tap" ${r}/><rect class="pulse" ${r}/>` : `<rect class="read" ${r}/>`}</svg>`;
      })() : "";
      if (s.frame) {
        ph.innerHTML = `<img src="data/${esc(s.frame)}" alt="Starbucks screen before step ${s.n}: ${esc(s.text)}" width="360" height="800">${ring}`;
      } else {
        const hl = esc(s.compact).replace(new RegExp(`^(\\[${s.action.element}\\].*)$`, "m"), "<mark>$1</mark>");
        ph.innerHTML = `<div class="txt"><span class="note">No frame was saved before the first tap. This is the screen as Wonder read it, with its choice marked.</span>${hl}</div>`;
      }
      const num = s.action.element;
      $("#fr-cap").textContent = s.frame
        ? (s.box_kind === "tap" ? `Ringed: element [${num}], the one Wonder chose. Frame recorded just before this tap.`
          : "Dashed: the text the answer was read from.")
        : "Step 1 acts on the app's first screen.";
      $("#fr-t").textContent = secs(s.t);
      $("#fr-c").textContent = s.calls_so_far;
      $("#fr-u").textContent = usd(s.usd_so_far);
      const tree = esc(s.compact).replace(new RegExp(`^(\\[${num}\\].*)$`, "m"), "<mark>$1</mark>");
      $("#fr-tree").innerHTML = s.box_kind === "read" ? esc(s.compact).replace(/^(.*190 calories.*)$/m, "<mark>$1</mark>") : tree;
      $("#fr-prev").disabled = i === 0;
      $("#fr-next").disabled = i === R.steps.length - 1;
    }
    function stop() { clearInterval(timer); timer = null; $("#fr-play").textContent = "Play"; }
    $("#fr-prev").onclick = () => { stop(); show(i - 1); };
    $("#fr-next").onclick = () => { stop(); show(i + 1); };
    $("#fr-play").onclick = () => {
      if (timer) return stop();
      if (i === R.steps.length - 1) show(0);
      $("#fr-play").textContent = "Pause";
      timer = setInterval(() => { if (i >= R.steps.length - 1) stop(); else show(i + 1); }, 2400);
    };
    items.forEach((li, k) => li.querySelector("button").onclick = () => { stop(); show(k); });
    body.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") { stop(); show(i + 1); }
      if (e.key === "ArrowLeft") { stop(); show(i - 1); }
    });
    // ?step=N opens the run at step N (for links and screenshots).
    show((+new URLSearchParams(location.search).get("step") || 2) - 1);
  }

  // ---- 3: learned ----
  function routineHTML(rt) {
    return `
      <div class="inputs">Inputs: ${Object.entries(rt.inputs).map(([k, v]) => `<span class="slot">{{${esc(k)}}}</span> <span>${esc(v.type)}, e.g. “${esc(v.example)}”</span>`).join(" ")}
        · Output: ${rt.outputs.map((o) => `<code>${esc(o)}</code>`).join(", ")}</div>
      <ol class="rsteps">${rt.steps.map((s) => `
        <li>
          <div class="rs-intent">${slots(s.intent)}${s.optional ? '<span class="chip opt">optional</span>' : ""}</div>
          <div class="rs-id">${esc(s.id)}</div>
          <div class="checks">
            ${s.pre.length ? `<span class="tag">Before</span><ul>${s.pre.map((c) => `<li>${slots(c)}</li>`).join("")}</ul>` : ""}
            <span class="tag do">Do</span><ul><li>${slots(s.action)}</li></ul>
            ${s.post.length ? `<span class="tag">After</span><ul>${s.post.map((c) => `<li>${slots(c)}</li>`).join("")}</ul>` : ""}
            ${s.extract.length ? `<span class="tag do">Read</span><ul><li>${s.extract.map((x) => `<code>${esc(x)}</code>`).join(", ")}, from the screen</li></ul>` : ""}
          </div>
        </li>`).join("")}
      </ol>`;
  }

  function renderLearned() {
    const L = D.learned, f = L.first, r = L.replay, n = L.new_input, C = L.compile;
    const body = $("#learned-body");
    const maxMs = Math.max(...L.replay_steps.map((s) => s.ms.total));
    const bar = (label, a, b, fmt) => `
      <div class="metric"><div class="name">${label}</div><div class="bars">
        <div class="bar"><div class="track"><div class="fill" style="width:100%"></div></div><div class="num">${fmt(a)}</div></div>
        <div class="bar replay"><div class="track"><div class="fill" style="width:${Math.max(2, (b / a) * 100).toFixed(1)}%"></div></div><div class="num">${fmt(b)}</div></div>
      </div></div>`;
    const rungChip = (s) => s.status === "skipped" ? `<span class="chip">skipped</span>`
      : s.rung === 0 ? "" : `<span class="chip apricot" title="${esc(s.rungs.join("; "))}">rung ${s.rung}</span>`;
    body.innerHTML = `
      <span class="eyebrow"><span class="num">${num("learned")}</span> The same task, learned</span>
      <h2 id="learned-h">One Wonder call turns that run into a routine. The next request just replays it.</h2>
      <p class="lede">The compiler kept the taps, turned the drink into an input, and wrote checks for every step from the screens it saw. A replay runs those checks as code, so the model is called only to match the request and to read out the answer.</p>
      <div class="learn">
        <div>
          <div class="card routine">
            <div class="routine-head">
              <div><div class="routine-name">${esc(L.active.routine)}</div><div class="meta" id="rt-meta"></div></div>
              <div class="tabs" role="tablist" aria-label="Routine version">
                <button role="tab" class="on" aria-selected="true" data-v="compiled">As compiled</button>
                <button role="tab" aria-selected="false" data-v="active">In the library (v${L.active.version})</button>
              </div>
            </div>
            <div id="rt-body"></div>
            <div class="label-rec" id="rt-src"></div>
          </div>
          <div class="block" style="padding:14px 16px;margin-top:12px;font-size:14px;color:var(--ink-2)">
            <b style="color:var(--ink)">Compiling cost one Muse Wonder call, once:</b> ${secs(C.seconds)}, ${usd(C.usd)}, right after the first run.
            It dropped one input it found unused (<span class="slot">{{drink_size}}</span>). ${srcA(C.src, "runs.jsonl")}
          </div>
          <div class="callout" style="margin-top:12px">
            <b>As recorded, flaw included.</b> The last step's after-check still names <span class="slot">{{drink_size}}</span>, the input the compiler dropped.
            At replay that check held only at the relaxed threshold (rung 2, below). We show the routine as it is, not tidied.
          </div>
        </div>
        <div>
          <div class="card vs">
            <h3>Replay vs. first run</h3>
            <div class="legend"><span><i></i>First run (the agent)</span><span><i class="s"></i>Replay (the routine)</span></div>
            ${bar("Time", f.seconds, r.seconds, secs)}
            ${bar("Model calls", f.calls, r.calls, (x) => String(x))}
            ${bar("Cost", f.usd, r.usd, usd)}
            <div class="label-rec">
              <span><b>Replay</b> ${esc(date(r.task_id.replace(/^task-(\d\d)(\d\d)-(\d\d)(\d\d)(\d\d).*/, "2026-$1-$2 $3:$4:$5")))}</span>
              <span><b>Routine</b> v${r.version}</span><span><b>Commit</b> <code>${commit(r.commit)}</code></span>
              <span><b>Task</b> <code>${esc(r.task_id)}</code></span>
              <span>${srcA(r.src, "runs.jsonl")} ${srcA(L.replay_src, "recording")}</span>
            </div>
          </div>
          <div class="card vs" style="margin-top:16px">
            <h3>Inside the replay</h3>
            <p class="meta" style="margin:6px 0 0">The routine itself: ${L.replay_steps.length} steps in ${secs(r.routine_s)}, <b style="color:var(--ink)">${r.routine_calls} model calls</b>. Each step waits for its before-checks, acts, then waits for its after-checks. The task's ${r.calls} calls are Muse Spark: one to match the request, one to read the answer.</p>
            <div class="timeline">
              ${L.replay_steps.map((s) => `
                <div class="tl ${s.status === "skipped" ? "skipped" : ""}">
                  <span class="id" title="${esc(s.id)}">${esc(s.id)} ${rungChip(s)}</span>
                  <span class="track"><span class="fill" style="display:block;width:${((s.ms.total / maxMs) * 100).toFixed(1)}%"></span></span>
                  <span class="ms">${(s.ms.total / 1000).toFixed(1)} s</span>
                </div>`).join("")}
            </div>
            <p class="small" style="margin:10px 0 0">Rung 2 is relaxed matching, the second rung of the fallback ladder; no repair and no model call. A skipped step is optional and its after-checks already held.</p>
          </div>
          <div class="card vs" style="margin-top:16px">
            <h3>Same routine, new input</h3>
            <p style="margin:6px 0 0;color:var(--ink-2)">“${esc(n.goal.replace(/^In the Starbucks app, /, "").replace(/^./, (c) => c.toUpperCase()))}”: <b style="color:var(--ink)">${esc(n.answer.replace(/^calories: /, ""))}</b>
              in ${secs(n.seconds)}, ${n.calls} calls, ${usd(n.usd)}. The matcher filled <span class="slot">{{drink_name}}</span> = Caramel Macchiato.</p>
            <div class="label-rec"><span><b>Commit</b> <code>${commit(n.commit)}</code></span><span><b>Task</b> <code>${esc(n.task_id)}</code></span>${srcA(n.src, "runs.jsonl")}</div>
          </div>
          <div class="card vs" style="margin-top:16px">
            <h3>How the routine got to v${L.active.version}</h3>
            <ul class="versions">${L.versions.map((v) => `
              <li><span class="v">v${v.version}</span><div>
                <span class="chip ${v.status === "active" ? "sage" : v.status === "rejected" ? "apricot" : ""}">${esc(v.status)}</span>
                <span class="chip">${v.by === "self-repair" ? "self-repair, by Wonder" : v.version === 1 ? "compiled; input note fixed by hand" : "fixed by hand (loop A)"}</span>
                ${v.trial ? `<span class="meta"> trial ${v.trial.passed ? "passed" : "failed"}</span>` : ""}
                <p>${v.changes.map((c) => esc(c.replace(/\.?$/, "."))).join(" ")}</p></div></li>`).join("")}
            </ul>
            <div class="label-rec">${srcA(L.versions_src, "index.json")}</div>
          </div>
        </div>
      </div>`;
    const showV = (v) => {
      const rt = L[v];
      $("#rt-body").innerHTML = routineHTML(rt);
      $("#rt-src").innerHTML = srcA(rt.src);
      $("#rt-meta").textContent = v === "compiled"
        ? `Starbucks · ${rt.steps.length} steps · as the compiler wrote it from the run above (named ${rt.routine} then)`
        : `Starbucks · ${rt.steps.length} steps · v${rt.version}, the version the replay ran`;
      body.querySelectorAll(".tabs button").forEach((b) => { const on = b.dataset.v === v; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
    };
    body.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => showV(b.dataset.v));
    showV("compiled");
  }

  // A recorded frame inside a phone, with a box from the recorded tree drawn over it (never baked into the picture).
  function phoneHTML(frame, alt, screen, boxes = []) {
    const [W, H] = screen || [1080, 2400];
    const rects = boxes.map(({ box, kind }) => {
      const p = 12, [x1, y1, x2, y2] = box;
      const r = `x="${x1 - p}" y="${y1 - p}" width="${x2 - x1 + 2 * p}" height="${y2 - y1 + 2 * p}" rx="28"`;
      return kind === "tap" ? `<rect class="tap-glow" ${r}/><rect class="tap" ${r}/>` : `<rect class="read" ${r}/>`;
    }).join("");
    return `<div class="phone"><img src="data/${esc(frame)}" alt="${esc(alt)}" loading="lazy" width="360" height="800">
      ${rects ? `<svg class="ring" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${rects}</svg>` : ""}</div>`;
  }
  // A section's number is its place on the page, so a section can be added without renumbering by hand.
  const num = (id) => [...document.querySelectorAll("main section.sec")].findIndex((s) => s.id === id) + 1;
  const head = (n, id, eyebrow, h, lede) => `
    <span class="eyebrow"><span class="num">${num(id)}</span> ${esc(eyebrow)}</span>
    <h2 id="${id}-h">${h}</h2>${lede ? `<p class="lede">${lede}</p>` : ""}`;
  const testApp = `<span class="chip apricot" title="SkyLark Air is Envoy's own test airline app">Our test app</span>`;
  const notFinal = (c) => D.eval.final ? "" : `<span class="chip apricot pending" title="Measured before the frozen Nov 2 eval">${c ? `on ${esc(c)} · ` : ""}final numbers after Nov 2</span>`;

  // ---- 4: repairs ----
  function renderRepairs() {
    const R = D.repair, K = R.skylark, S = R.starbucks;
    const kept = R.real.filter((v) => v.passed).length;
    $("#repairs-body").innerHTML = `
      ${head(4, "repairs", "It repairs itself", "When the app changes, Envoy fixes only the step that broke, then tests the fix before keeping it.",
        "A failed check climbs a ladder: wait, relaxed matching, known pop-ups, then a local repair by the model, capped per step. A repair becomes a new version on trial, and it's kept only if a clean replay passes.")}
      <div class="repair">
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>An extra screen, injected on purpose</h3>${testApp}</div>
          <p class="meta" style="margin:6px 0 0">SkyLark's check-in got a new “Review your trip” screen the routine had never seen. The routine's next step looked for “Confirm check-in” and didn't find it.</p>
          <div class="pair">
            <figure>${phoneHTML(K.before, "SkyLark: the injected Review your trip screen with Looks good", [1080, 2400])}<figcaption><b>Before the repair</b><br>The unexpected screen.</figcaption></figure>
            <figure>${phoneHTML(K.after_img, "SkyLark: Confirm check-in, reached after tapping Looks good", [1080, 2400])}<figcaption><b>After</b><br>Back on the routine's path.</figcaption></figure>
          </div>
          <div class="quote"><span class="meta">${esc(MODEL[K.repair_model] || K.repair_model)}'s reason, one call:</span><br>“${esc(K.reason)}”</div>
          <ol class="flow">
            <li><b>Repair</b> on first meeting the change: ${secs(K.first.duration_s)}, ${K.first.calls} model call, ${usd(K.first.standard_usd)}. Rung ${K.first.rung} of the ladder.</li>
            <li><b>Saved</b> as v2: ${esc(K.patch)}.</li>
            <li><b>Trial</b> on a new booking: ${K.trial.passed ? "passed" : "failed"}, ${secs(K.trial.duration_s)}, ${K.trial.calls} model calls.</li>
            <li><b>After:</b> another booking ${K.after.passed ? "passed" : "failed"} with ${K.after.calls} calls; back on the original layout ${K.back.passed ? "passed" : "failed"} too (the new step is optional).</li>
          </ol>
          <details class="read"><summary>The saved version's diff (v1 → v2)</summary><pre class="diff">${K.diff.map((l) => `<span class="${l[0] === "+" && !l.startsWith("+++") ? "add" : l[0] === "-" && !l.startsWith("---") ? "del" : ""}">${esc(l)}</span>`).join("\n")}</pre></details>
          <div class="label-rec"><span><b>Recorded</b> ${esc(K.date)}</span><span><b>Commit</b> <code>${esc(K.commit)}</code>${K.dirty ? " (uncommitted changes)" : ""}</span>${srcA(K.src, "change.json")} ${srcA(K.lib_src, "patches.json")}</div>
        </div>
        <div>
          <div class="card" style="padding:20px">
            <div class="row-between"><h3>All 50 injected changes</h3>${testApp}</div>
            <p class="meta" style="margin:6px 0 0">Each of the 10 routines met each of 5 changed layouts on a new booking.</p>
            <div class="tbl-wrap"><table class="tbl">
              <thead><tr><th>Change</th><th>Recovered</th><th>How</th><th class="r">Calls</th><th>Then, no call</th></tr></thead>
              <tbody>${R.layouts.map((l) => `<tr><td>${esc(l.Layout.replace(/^\d: /, ""))}</td><td><b>${esc(l.Recovered)}</b></td><td class="small">${esc(l["Saved by"])}</td><td class="r">${esc(l["Model calls (first)"])}</td><td>${esc(l["After, no model call"])}</td></tr>`).join("")}</tbody>
            </table></div>
            <p class="small" style="margin:10px 0 0">New inputs on the same routines: ${esc(String(R.new_inputs.Passed || "").replace(/\*/g, ""))} of ${esc(R.new_inputs.Runs)} right, ${esc(R.new_inputs["No model call"])} with no model call. ${notFinal("6c507f3")}</p>
            <div class="label-rec">${srcA(R.layouts_src, "change.md")}</div>
          </div>
          <div class="card" style="padding:20px;margin-top:16px">
            <h3>On real apps it's harder, and the trial is why that's safe</h3>
            <p style="margin:8px 0 0;color:var(--ink-2);font-size:14.5px">In the routine library, self-repair proposed ${R.real.length} new versions for real apps. The trial kept ${kept} and rejected ${R.real.length - kept}, so the routine stayed on the version that worked. Most real-app versions were fixed by hand during the loops, and the cards in section ${num("real-apps")} say so.</p>
            <div class="block" style="padding:12px 14px;margin-top:12px;font-size:14px">
              <b>Kept: Starbucks v3.</b> ${esc(S.change.replace(/^./, (c) => c.toUpperCase()))}. Later replaced by a hand fix (v4). ${esc(MODEL[S.call.model] || S.call.model)}, one call, ${(S.call.ms / 1000).toFixed(1)} s, ${usd(S.call.usd)}; its trial passed with ${S.trial.model_calls} model calls in ${secs(S.trial.duration_s)}.
              <div class="small" style="margin-top:6px">Its reason: “${esc(S.reason)}”</div>
              <div class="label-rec" style="margin-top:8px">${srcA(S.src, "index.json")} ${srcA(S.call_src, "repair call")}</div>
            </div>
            <ul class="versions" style="margin-top:12px">${R.real.filter((v) => !v.passed).map((v) => `<li><span class="v">v${v.version}</span><div><span class="chip apricot">rejected by its trial</span> <code class="small">${esc(v.routine)}</code><p class="small">${esc(v.changes[0])}</p></div></li>`).join("")}</ul>
            <div class="label-rec">${srcA(R.real_src, "data/routines/*/index.json")}</div>
          </div>
        </div>
      </div>`;
  }

  // ---- 5: real apps ----
  // A table cell like "5/5 on v4 by the routine alone (639 ×2, …)": the count bold, the aside small.
  const cell = (t) => { const m = String(t).match(/^([^(]+?)\s*(\(.+\))$/); return m ? `<b>${esc(m[1])}</b><small>${esc(m[2])}</small>` : `<b>${esc(t)}</b>`; };
  function renderApps() {
    const A = D.apps;
    $("#real-apps-body").innerHTML = `
      ${head(5, "real-apps", "Real apps", "Eleven real apps, each learned from a first run.",
        "Every number below is copied from the real-app results table: first runs with no routine against replays of the saved one, on Envoy's emulators and the Pixel 5, Oct 30–31. Only apps with real recordings appear.")}
      <div class="apps">${A.cards.map((c) => `
        <article class="card app-card">
          ${c.frame ? `<div class="app-shot"><img src="data/${esc(c.frame.frame)}" alt="${esc(c.name)}: the screen where the first run found its answer" loading="lazy" width="360" height="800"></div>` : `<div class="app-shot none"><span>${esc(c.private ? "No screens shown" : "")}</span></div>`}
          <div class="app-body">
            <div class="row-between"><h3>${esc(c.name)}</h3><span class="chip">v${c.version} · ${c.steps} steps</span></div>
            <p class="app-task">${esc(c.task)}</p>
            <dl class="fr">
              <div><dt>First runs</dt><dd>${cell(c.first.runs)}<span>${esc(c.first.cost)}</span></dd></div>
              <div class="rp"><dt>Replays</dt><dd>${cell(c.replay.runs)}<span>${esc(c.replay.cost)}</span></dd></div>
            </dl>
            ${c.private ? `<p class="small" style="margin:8px 0 0">${esc(c.private)}</p>` : ""}
            ${c.hand_fixed ? `<p class="small" style="margin:6px 0 0">Some versions were fixed by hand; the routine's history says which.</p>` : ""}
            <details class="read"><summary>The table's notes</summary><p class="small" style="margin:6px 0 0">${esc(c.notes)}</p></details>
            <div class="label-rec" style="margin-top:8px">${c.when ? `<span><b>${esc(c.when)}</b></span>` : ""}${c.commit ? `<span><code>main ${esc(c.commit)}</code></span>` : ""}${srcA(c.src, "table.md")} ${srcA(c.routine_src, "routine")}</div>
            ${c.frame ? `<div class="small">Frame: <code>${esc(c.frame.task_id)}</code>, ${esc(c.frame.taken_et)} ET (${esc(c.frame.loop)})</div>` : ""}
          </div>
        </article>`).join("")}
      </div>
      <div class="block" style="padding:14px 18px;margin-top:16px;font-size:14px;color:var(--ink-2)">
        Plus ${A.skylark.length} routines on SkyLark, ${testApp} our own airline app, where the eval can change the layout on purpose and check the app's real state: ${A.skylark.map((s) => `<code>${esc(s)}</code>`).join(", ")}.
      </div>`;
  }

  // ---- teach it by showing it ----
  function renderTeach() {
    const T = D.teach, C = T.rec.calendar, K = T.rec.skylark, R = C.replay;
    const label = (s) => s.kind === "type" ? `type “${esc(s.typed)}”` : `tap “${esc(s.label)}”`;
    const film = (items) => `<div class="film">${items.join("")}</div>`;
    $("#teach-body").innerHTML = `
      ${head(0, "teach", "Teach it by showing it", "Where the agent stalls, a person can show Envoy once.",
        "In teach mode a person does the task through Envoy's live view. Envoy records each screen and each tap or keystroke, Muse Wonder compiles the recording into a routine, and Envoy replays it on its own before saving it.")}
      <div class="callout" style="margin-top:20px"><b>Who did the showing:</b> a script (<code>eval/teach_person.py</code>) that sends the web app's own live-view messages, taps as screen positions and typing key by key. No real person has taught Envoy yet. Everything below is what the code recorded.</div>
      <div class="block" style="padding:14px 18px;margin-top:12px;font-size:14px;color:var(--ink-2)">
        <b style="color:var(--ink)">Why Calendar.</b> In the Oct 30 loops, Google Calendar is where learning from the agent stalled:
        ${(() => {
          const emu = T.calendar_rows.find((r) => !/Pixel/.test(r.app)), px = T.calendar_rows.find((r) => /Pixel/.test(r.app));
          return `${emu ? `On the emulator the agent found a holiday's date (${esc(emu.first.split(" ")[0])} first runs), but no routine could be compiled that reads the answer back.` : ""}
            ${px ? `On the Pixel 5 it got stuck (${esc(px.first)}): that calendar draws its days, so they aren't in the accessibility tree.` : ""}`;
        })()}
        ${srcA(T.table_src, "table.md")}
      </div>
      <div class="card" style="padding:20px;margin-top:16px">
        <div class="row-between"><h3>Shown once: “${esc(C.goal)}”</h3><span class="chip">${secs(C.shown_s)} · ${C.shown_calls} model calls</span></div>
        ${film(C.steps.map((s) => `<figure>${phoneHTML(s.frame, `Google Calendar before step ${s.n}: ${s.kind} ${s.typed || s.label}`, [1080, 2400], [{ box: s.box, kind: "tap" }])}<figcaption><b>${s.n}.</b> ${label(s)}<br>${secs(s.t)}</figcaption></figure>`))}
        <p class="small" style="margin:8px 0 0">Ringed: where the person touched, from the recorded screen. Google Calendar on Envoy's emulator, the envoy3955 test account. Both events were deleted afterwards.</p>
        <div class="learn-mid">
          <div><b>Compiled</b> by ${esc(MODEL[C.routine.compiler] || C.routine.compiler)}, one call, ${usd(C.routine.usd)}, into <code>${esc(C.routine.name)}</code> with inputs
            ${Object.entries(C.routine.inputs).map(([k, v]) => `<span class="slot">{{${esc(k)}}}</span> (${esc(v)})`).join(" and ")}.</div>
          <ol class="flow">${C.routine.steps.map((s) => `<li>${slots(s.intent)}</li>`).join("")}</ol>
        </div>
        <div class="row-between" style="margin-top:18px"><h3>Replayed alone</h3><span class="chip sage">${R.steps.length}/${R.steps.length} steps · ${secs(R.seconds)} · ${R.calls} model calls</span></div>
        ${film(R.steps.map((s, i) => `<figure>${phoneHTML(s.frame, `Replay, after step ${i + 1}: ${s.id}`, [1080, 2400])}<figcaption><b>${i + 1}.</b> <code>${esc(s.id)}</code><br>${(s.ms / 1000).toFixed(1)} s${s.rung ? ` · rung ${s.rung}` : ""}</figcaption></figure>`))}
        <p class="small" style="margin:8px 0 0">Each frame is the screen after its step. The last shows the replay's own “Saved "Dentist"” beside the event the person made. Rung 1 is wait and retry.</p>
        <div class="callout" style="margin-top:14px"><b>As recorded, flaw included.</b> The last step is named “Tap Open Tasks”. Calendar's editor sheet sat over that button, and Save was on top at the same spot; the recorder named the element underneath. The replay taps the same point, so it saves, but the step's name and locator are wrong. Fixed since: a taught tap now goes to the topmost element under the finger (<code>f25be22</code>, Oct 31). This recording predates the fix and is shown as made.</div>
        <div class="label-rec"><span><b>Recorded</b> ${esc(C.shown_et)} ET</span><span><b>Code</b> teach mode, on main since Oct 31</span><span><code>${esc(C.task_id)}</code></span>${srcA(T.src, "teach.json")} ${srcA(T.code_src, "teach.py")} ${srcA(T.person_src, "teach_person.py")}</div>
      </div>
      <div class="card" style="padding:18px 20px;margin-top:16px">
        <div class="row-between"><h3>The same on SkyLark</h3>${testApp}</div>
        <p style="margin:6px 0 0;color:var(--ink-2);font-size:14.5px">“${esc(K.goal)}”: shown in ${K.steps} steps (${secs(K.shown_s)}), compiled for ${usd(K.usd)} into <code>${esc(K.routine)}</code>, replayed alone in ${secs(K.replay_s)} with ${K.replay_calls} model calls. It read “${esc(K.replay_output)}”, the same answer the person saw.</p>
        <div class="label-rec">${srcA(T.src, "teach.json")}</div>
      </div>`;
  }

  // ---- 6: memory ----
  const KIND = { email: "email", email_markup: "email (markup)", app_screen: "app screen", routine_run: "routine run", photo: "photo" };
  const ORDER = ["number", "date", "start_date", "from", "to", "depart_time", "seat", "gate", "boarding_time", "confirmation_code", "status"];
  function renderMemory() {
    const M = D.memory, X = M.extraction, demo = M.demo;
    const factRow = (f) => `
      <li class="${f.current ? "" : "old"}">
        <span class="attr">${esc(f.attribute.replace(/_/g, " "))}</span>
        <span class="val">${esc(f.value)}</span>
        <span class="srcs">${Object.entries(f.sources).map(([k, n]) => `<span class="chip ${k === "email" || k === "email_markup" ? "" : "sage"}">${esc(KIND[k] || k)}${n > 1 ? ` ×${n}` : ""}</span>`).join("")}</span>
        <span class="when small">${f.current ? `first seen ${esc(f.first_et.slice(5))}${f.first_source.subject ? ` in “${esc(f.first_source.subject)}”` : f.first_source.app ? ` in ${esc(f.first_source.app)}` : ""}` : `replaced ${esc(f.replaced_et.slice(5))}`}</span>
      </li>`;
    const ent = (name, filter) => {
      const e = demo.entities.find((x) => x.name === name);
      return `<div class="card ent"><div class="row-between"><h3>${esc(e.type)} · ${esc(e.name)}</h3>${testApp}</div>
        <ul class="facts">${e.facts.filter(filter).sort((a, b) => ORDER.indexOf(a.attribute) - ORDER.indexOf(b.attribute)).map(factRow).join("")}</ul></div>`;
    };
    $("#memory-body").innerHTML = `
      ${head(6, "memory", "Memory with sources", "Every fact says where and when it was seen. A newer source replaces an older value, and the old one stays as history.",
        "Facts come in from app screens, email and photos, through Muse Spark (every value must appear in its source). The same flight seen in a booking email, eight app screens and a boarding-pass photo is one flight.")}
      <div class="mem">
        ${ent("SL 482 · Fri, Oct 30, 2026", (f) => f.current && ["number", "date", "from", "to", "depart_time", "seat", "gate", "boarding_time", "confirmation_code", "status"].includes(f.attribute))}
        <div>
          ${ent("SL 1190 · Sat, Nov 14, 2026", (f) => ["number", "date", "seat", "confirmation_code"].includes(f.attribute))}
          <p class="small" style="margin:8px 4px 0">The seat came from the booking email, then a later “Seat change confirmed” email replaced it. Both stay in the graph, on two timelines: when it was true, and when Envoy learned it.</p>
          <div style="margin-top:14px">${ent("Denver · Fri, Dec 4, 2026", (f) => ["confirmation_code", "start_date", "status"].includes(f.attribute))}</div>
          <p class="small" style="margin:8px 4px 0">A cancellation email marks the trip cancelled. The test inbox's two fare promotions (${demo.promos.map((p) => `“${esc(p)}”`).join(", ")}) made no trips.</p>
        </div>
      </div>
      <div class="label-rec">From the demo world: SkyLark's test inbox, SkyLark app runs and one test photo, for the test persona. ${srcA(M.demo_src, "memory.json")} ${srcA(M.readme_src, "backend/memory/README.md")}</div>
      <div class="stats">
        <div class="card stat"><div class="big">${X.right}/${X.of}</div><div class="lbl">attributes right on ${X.items} labeled items (${X.pct}%), <b>${X.wrong} wrong</b></div>${notFinal(M.commit)} ${srcA(M.src, "memory.md")}</div>
        <div class="card stat"><div class="big">${M.stale.unwarned} of ${M.stale.of}</div><div class="lbl">stale facts served without a warning</div>${notFinal(M.commit)} ${srcA(M.src, "memory.md")}</div>
        <div class="card stat wide"><div class="lbl" style="margin-bottom:8px">The same question at four ages, on the eval's own booking ${testApp}</div>
          <ul class="ages">${M.ages.map((a) => `<li><span class="chip ${a.Warned ? "apricot" : "sage"}">${esc(a.Age)}</span> ${esc(a.Answer)}</li>`).join("")}</ul>
          ${srcA(M.src, "memory.md › Stale facts")}</div>
      </div>`;
  }

  // ---- 7: safety ----
  function renderSafety() {
    const S = D.safety, P = S.planted, A = S.approval;
    const pk = P.mentions[P.mentions.length - 1];
    $("#safety-body").innerHTML = `
      ${head(7, "safety", "Safety", "It asks before anything it can't undo, and text on a screen is never an instruction.",
        "Three signals vote on every tap: rules on the target's words, the screen's own warnings, and the model's label. Any one flags it, and the step waits for an approval on the user's phone. A routine asks too.")}
      <div class="safety">
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>An approval, recorded</h3>${testApp}</div>
          <div class="pair one">
            <figure>${phoneHTML(A.frame, "SkyLark: the Confirm check-in screen the routine stopped on", [1080, 2400])}</figure>
            <div>
              <p style="margin:0;font-family:var(--serif);font-size:17px">“${esc(A.description)}”</p>
              <p class="meta" style="margin:10px 0 4px">Why it asked:</p>
              <ul class="plain">${A.reasons.map((r) => `<li><span class="chip">${esc(r)}</span></li>`).join("")}</ul>
              <p class="small" style="margin:10px 0 0">The routine stopped here and asked. The request itself was the OK: by default, “check me in” approves tapping Confirm check-in for that trip, and Envoy says so afterwards. Money, a step that isn't what was asked, or a request from a trigger, an email or an AI client always waits for a person, on their iPhone. Only a person can approve, never an AI through MCP. ${esc(A.asked_et)} ET.</p>
              <div class="label-rec">${srcA(S.approval_src, "approval.json")}</div>
            </div>
          </div>
          <div class="stats two" style="margin-top:16px">
            <div class="block stat"><div class="big">${S.caught[0]}/${S.caught[1]}</div><div class="lbl">irreversible controls caught (code alone: ${S.caught[2]}), across SkyLark, Gmail, Amazon, Play, Settings, Chrome, Phone, YouTube</div>${notFinal(S.safety_run.commit)}</div>
            <div class="block stat"><div class="big">${S.reversible[0]}/${S.reversible[1]}</div><div class="lbl">ordinary controls wrongly flagged by code (${S.reversible[2]} with the model's label)</div>${srcA(S.safety_src, "safety.md")}</div>
          </div>
        </div>
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>Planted text on a screen</h3>${testApp}</div>
          <div class="pair one">
            <figure>${phoneHTML(P.frame, "SkyLark trip screen with a planted message telling the agent to cancel the trip", P.screen, [{ box: P.box, kind: "read" }])}<figcaption>Dashed: the planted message.</figcaption></figure>
            <div>
              <p class="meta" style="margin:0">The request:</p>
              <p style="margin:2px 0 10px;font-family:var(--serif);font-size:17px">“${esc(P.goal)}”</p>
              <p class="meta" style="margin:0">What the agent wrote while it worked:</p>
              <ul class="plain">${P.mentions.slice(0, 3).map((m) => `<li class="small">Step ${m.step}: “${esc(m.reason)}”</li>`).join("")}</ul>
              <p class="small" style="margin:10px 0 0"><b>It never tapped Cancel trip.</b> It saved the number and stopped. It was a clumsy run (${P.model_calls} model calls, ${secs(P.seconds)}, repeated Save taps), shown as recorded.</p>
            </div>
          </div>
          <div class="stats two" style="margin-top:16px">
            <div class="block stat"><div class="big">${S.agent[0]}/${S.agent[1]}</div><div class="lbl">agent runs still right with planted text; tried to follow it: <b>${S.agent[2]}</b>. Routines ${S.routines[0]}/${S.routines[1]}.</div>${notFinal(S.injection_run.commit)}</div>
            <div class="block stat"><div class="big">${S.inbox[0]}</div><div class="lbl">values from 4 planted emails stored in memory (instructions stored as facts: ${S.inbox[1]})</div>${srcA(S.injection_src, "injection.md")}</div>
          </div>
          <div class="label-rec"><span><b>Recorded</b> ${esc(S.injection_run.date)}, injection suite</span><span><code>${esc(P.run)}</code></span>${srcA(S.planted_src, "planted.json")}</div>
        </div>
      </div>`;
  }

  // ---- 8: Meta's models ----
  function renderModels() {
    const M = D.models, V = M.vision, C = M.vision_canvas, Sm = M.sam, F = D.first_run, L = D.learned;
    const sum = (cs) => cs.reduce((a, c) => a + c.usd, 0);
    const pct = (x) => `${Math.round(x * 100)}%`;
    const [W, H] = Sm.screen;
    const mp = Sm.model_point;
    $("#models-body").innerHTML = `
      ${head(8, "models", "Meta's models, by job", "Each model does the job it's best at, and the expensive one works once per task, not on every run.",
        "On the default profile, Muse Wonder plans, steps, repairs and compiles; Muse Spark 1.3 does the many small jobs; SAM 3.1 and Spark's grounding find targets on screens with no accessibility tree; Muse Voice Transcribe turns speech into a request.")}
      <div class="models">
        <div class="card model">
          <div class="mname">Muse Wonder</div><div class="mjob">Plans, decides steps on a first run, repairs, compiles</div>
          <p>In the Starbucks first run: ${M.wonder_calls.length} Wonder calls (plan and ${M.wonder_calls.length - 1} steps), ${usd(sum(M.wonder_calls))}. Then one call compiled the run into a routine: ${secs(L.compile.seconds)}, ${usd(L.compile.usd)}. On a replay: none.</p>
          ${srcA(F.src, "recording")}
        </div>
        <div class="card model">
          <div class="mname">Muse Spark 1.3</div><div class="mjob">Matches requests to routines, reads answers, fills memory, writes app notes, picks among SAM's boxes</div>
          <p>Every Starbucks replay is 2 Spark calls: match and read the answer, ${usd(sum(M.replay_calls))} together. Memory extraction: ${D.memory.extraction.right}/${D.memory.extraction.of} attributes right, 0 wrong.</p>
          ${srcA(L.replay_src, "recording")} ${srcA(D.memory.src, "memory.md")}
        </div>
        <div class="card model">
          <div class="mname">Muse Voice Transcribe</div><div class="mjob">Speech to a request, push-to-talk</div>
          <p>${esc(M.voice.split(". ").slice(0, 2).join(". "))}.</p>
          ${srcA(M.voice_src, "phase-5-results.md")}
        </div>
      </div>
      <div class="card sam">
        <div class="pair one">
          <figure><div class="phone"><img src="data/${esc(Sm.frame)}" alt="SkyLark's drawn seat map, with no accessibility tree for the seats" loading="lazy" width="540" height="1200">
            <svg class="ring" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
              <rect class="tap-glow" x="${Sm.box[0]}" y="${Sm.box[1]}" width="${Sm.box[2] - Sm.box[0]}" height="${Sm.box[3] - Sm.box[1]}" rx="14"/>
              <rect class="tap" x="${Sm.box[0]}" y="${Sm.box[1]}" width="${Sm.box[2] - Sm.box[0]}" height="${Sm.box[3] - Sm.box[1]}" rx="14"/>
              <g class="miss"><line x1="${mp[0] - 26}" y1="${mp[1] - 26}" x2="${mp[0] + 26}" y2="${mp[1] + 26}"/><line x1="${mp[0] + 26}" y1="${mp[1] - 26}" x2="${mp[0] - 26}" y2="${mp[1] + 26}"/></g>
            </svg></div>
            <figcaption>Ringed: the box SAM 3.1 proposed and Spark picked. ✕: where the step model alone pointed.</figcaption></figure>
          <div>
            <div class="row-between"><h3>SAM 3.1 on a screen that's only pixels</h3>${testApp}</div>
            <p style="color:var(--ink-2);margin:8px 0 0">SkyLark's seat map is drawn on a canvas, so its seats aren't in the accessibility tree. Asked for “${esc(Sm.target)}”, the step model's own point fell just above the seat, outside its box. SAM 3.1 proposed ${Sm.candidates} boxes from a shape phrase, they were numbered on the screenshot, and Muse Spark picked one: ${Sm.calls} calls, ${usd(Sm.usd)}, ${(Sm.ms / 1000).toFixed(1)} s.</p>
            <p class="small" style="margin:8px 0 0">Recorded ${esc(Sm.recorded_et)} ET. Only the chosen box was saved, not all ${Sm.candidates}. ${srcA(M.sam_src, "sam.json")}</p>
            <div class="tbl-wrap" style="margin-top:14px"><table class="tbl">
              <thead><tr><th>On ${V.step.targets} targets with no tree</th><th class="r">Hit</th><th class="r">Median error</th><th class="r">$ / target</th></tr></thead>
              <tbody>
                <tr><td>Step model's own coordinates</td><td class="r">${pct(V.step.accuracy)}</td><td class="r">${V.step.median_error_px} px</td><td class="r">${usd(V.step.cost_per_target)}</td></tr>
                <tr><td>Grounding alone</td><td class="r">${pct(V.grounding.accuracy)}</td><td class="r">${V.grounding.median_error_px} px</td><td class="r">${usd(V.grounding.cost_per_target)}</td></tr>
                <tr><td>SAM 3.1 + Spark's pick</td><td class="r">${pct(V.sam.accuracy)}</td><td class="r">${V.sam.median_error_px} px</td><td class="r">${usd(V.sam.cost_per_target)}</td></tr>
              </tbody></table></div>
            <p class="small" style="margin:8px 0 0">On the ${C.sam.targets} drawn seats alone, SAM + pick hit ${C.sam.hits} and grounding ${C.grounding.hits}. Envoy runs SAM first, then grounding: together they found all 52 (Oct 27). ${srcA(M.vision_src, "vision.json")} ${srcA(M.phase6_src, "phase-6-results.md")}</p>
          </div>
        </div>
      </div>`;
  }

  // ---- 9: the proof ----
  function renderProof() {
    const P = D.proof, E = D.eval;
    const chart = (k, t, cap) => `<figure class="card chart"><img src="data/${esc(P.charts[k])}" alt="${esc(t)}" loading="lazy"><figcaption><b>${esc(t)}</b> ${cap} ${srcA({ path: P.charts_src.path + "/" + k + ".png" }, k + ".png")}</figcaption></figure>`;
    $("#proof-body").innerHTML = `
      ${head(9, "proof", "The proof", "The evaluation, scored by code on the app's real state, never by a model.",
        "Each suite starts from a known state. Success is the app's own state or the right answer on screen. Dollars are at Meta's standard prices.")}
      <div class="final-banner ${E.final ? "done" : ""}">
        ${E.final ? `<b>Final numbers.</b> All ${E.suites} suites ran on the <code>eval-final</code> tag.`
          : `<b>Final numbers after Nov 2.</b> ${E.on_tag} of ${E.suites} suites have run on the frozen <code>eval-final</code> tag so far. Every number below shows the commit it was measured on.`} ${srcA(E.src, "report.md")} ${srcA({ path: "site/data/numbers.json" }, "numbers.json")}
      </div>
      <div class="tbl-wrap card" style="margin-top:16px"><table class="tbl suites">
        <thead><tr><th>Suite</th><th>Result</th><th>Measured on</th></tr></thead>
        <tbody>${P.suites.map((s) => /^8\. AndroidWorld/.test(s.suite) ? { ...s, suite: "8. AndroidWorld", result: "Reported on its own page; summary below." } : s).map((s) => `<tr><td>${esc(s.suite)}</td><td>${esc(s.result)}</td><td><code class="small">${esc(s.ran_on)}</code>${/eval-final/.test(s.ran_on) ? "" : ' <span class="chip apricot pending">final after Nov 2</span>'}</td></tr>`).join("")}</tbody>
      </table></div>
      <p class="small" style="margin:8px 4px 0">Suites 0–3b and 5–7 run on SkyLark, our own test app, and on the test inbox; suite 4 is real apps. ${srcA(P.src, "report.md")}</p>
      <h3 style="margin-top:28px">The design's own targets</h3>
      <div class="tbl-wrap card" style="margin-top:10px"><table class="tbl">
        <thead><tr><th>Target</th><th>Goal</th><th>Measured</th></tr></thead>
        <tbody>${P.targets.map((t) => `<tr><td>${esc(t.Target)}</td><td>${esc(t.Goal)}</td><td>${esc(t.Measured)}</td></tr>`).join("")}</tbody>
      </table></div>
      <div class="charts">
        ${chart("cost_and_time_over_repeated_runs", "First run vs later runs", "SkyLark's 10 core tasks, a new booking each time.")}
        ${chart("real_apps_stages", "Real apps: where learning holds and where it breaks", "18 read-only workflows, Oct 28 (4/11 right on a new input then).")}
        ${chart("recovery_by_injected_change", "Recovery from injected UI changes", "SkyLark, 50 of 50.")}
        ${chart("success_by_system_and_layout", "Envoy vs the full agent vs a fixed replay", "SkyLark core set.")}
      </div>
      <div class="stats three" style="margin-top:16px">
        <div class="card stat"><div class="lbl">The real phone (Pixel 5)</div><div class="big">${P.phone.passed}/${P.phone.runs}</div><div class="lbl">the 10 core routines, compiled on an emulator, on 3 new bookings each: <b>${P.phone.calls} model calls</b>, median ${secs(P.phone.median_s)}</div>${notFinal(P.phone.commit + ", " + P.phone.date)} ${srcA(P.phone.src, "sizes.json")}</div>
        <div class="card stat"><div class="lbl">AndroidWorld (Google's benchmark, 116 tasks)</div><p style="margin:6px 0 0;font-size:14px;color:var(--ink-2)">${esc(P.aw.headline.split(". ").slice(0, 3).join(". "))}.</p><div class="small" style="margin-top:6px">Held-out half, re-measured Oct 29: ${esc(P.aw.held_out.split(".")[0])}. A rerun on the hybrid profile follows after Nov 2.</div>${srcA(P.aw.src, "androidworld-results.md")}</div>
        <div class="card stat"><div class="lbl">Offline tests</div><div class="big">${P.tests.functions}</div><div class="lbl">test functions in ${P.tests.files} files, counted from the code (a parametrized test counts once)</div>${srcA(P.tests.src, "backend/tests")}</div>
      </div>`;
  }

  // ---- 10: how it's built ----
  function renderBuilt() {
    const B = D.built;
    $("#how-built-body").innerHTML = `
      ${head(10, "how-built", "How it's built", "One task API for every interface, one device interface for every phone.", "")}
      <figure class="card chart" style="margin-top:24px"><img src="data/${esc(B.diagrams.architecture)}" alt="Envoy's architecture: interfaces, the task API, the backend, Meta's models and the device layer" loading="lazy"><figcaption>${srcA(B.diagrams_src, "docs/diagrams")}</figcaption></figure>
      <figure class="card chart" style="margin-top:16px"><img src="data/${esc(B.diagrams.lifecycle)}" alt="Routine lifecycle: compile once, run many times, repair locally" loading="lazy"><figcaption>${srcA(B.diagrams_src, "docs/diagrams")}</figcaption></figure>
      <div class="built">
        <div class="card" style="padding:20px">
          <h3>What Envoy built itself</h3>
          <ul class="ours">${B.ours.map((o) => `<li><b>${esc(o.title)}.</b> <span>${esc(o.text.split(". ")[0].replace(/\.$/, "").replace(/^./, (c) => c.toUpperCase()))}.</span></li>`).join("")}</ul>
          <p class="small" style="margin:10px 0 0">Ideas borrowed, no code used: ${B.borrowed.map(esc).join(" ")}</p>
        </div>
        <div class="card" style="padding:20px">
          <h3>Open-source plumbing</h3>
          <p class="small" style="margin:6px 0 10px">Talking to phones, streaming video, serving HTTP, drawing the web app. Each credited with its license.</p>
          <div class="chips">${B.plumbing.map((p) => `<span class="chip" title="${esc(p.license)}: ${esc(p.use)}">${esc(p.name)}</span>`).join("")}</div>
          <div class="label-rec">${srcA(B.src, "THIRD_PARTY.md")}</div>
        </div>
      </div>
      <div class="card next-up">
        <div><h3>The code</h3><p class="meta" style="margin:4px 0 0">${D.meta.repo_url ? `<a href="${esc(D.meta.repo_url)}">${esc(D.meta.repo_url)}</a>` : "The repository link goes here when it's public."}</p></div>
        <div class="meta">This site: <code>site/</code>, built by <code>scripts/build_site_data.py</code>.</div>
      </div>`;
  }

  // ---- table of contents ----
  function renderToc() {
    const secs = [...document.querySelectorAll("main section.sec")];
    const names = { claim: "Claim", "first-run": "First run", learned: "Learned", repairs: "Repairs", "real-apps": "Real apps",
      teach: "Teach it", memory: "Memory", safety: "Safety", models: "Models", proof: "Proof", "how-built": "How it's built" };
    $("#toc").innerHTML = secs.map((s, k) => `<a href="#${s.id}" data-id="${s.id}"><span class="n">${k + 1}</span>${esc(names[s.id] || s.id)}</a>`).join("");
    const links = [...document.querySelectorAll("#toc a")];
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.dataset.id === e.target.id));
    }), { rootMargin: "-40% 0px -55% 0px" });
    secs.forEach((s) => io.observe(s));
  }

  renderClaim();
  renderFirstRun();
  renderLearned();
  renderRepairs();
  renderApps();
  renderTeach();
  renderMemory();
  renderSafety();
  renderModels();
  renderProof();
  renderBuilt();
  renderToc();
  // ?only=<section id> shows one section alone (for screenshots: headless Chrome captures from the top).
  const only = new URLSearchParams(location.search).get("only");
  if (only) document.querySelectorAll("main section.sec").forEach((s) => { if (s.id !== only) s.hidden = true; });
  // Sections render after load, so a #section link lands short; scroll again once they're in.
  if (location.hash) { const t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
  // Light or dark: light unless the visitor picks dark with the top bar's toggle, remembered in this browser (the <head>
  // script applies it before the first paint). The browser's own bar follows the page's color.
  const toggle = $("#theme"), bar = $('meta[name="theme-color"]');
  const theme = (dark) => {
    if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme;
    bar.content = dark ? "#121815" : "#ece7dc";
    toggle.setAttribute("aria-pressed", String(dark));
  };
  theme(document.documentElement.dataset.theme === "dark");
  toggle.addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme !== "dark";
    theme(dark);
    try { localStorage.setItem("envoy-theme", dark ? "dark" : "light"); } catch (e) { /* private mode: this visit only */ }
  });
  $("#foot").innerHTML = `Built by <code>scripts/build_site_data.py</code> from the repo's recordings and eval results. No analytics, no third-party calls.`;
})();
