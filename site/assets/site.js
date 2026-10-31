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
          <li>Real apps with new inputs: 4 of 11 reruns were right on Oct 28. After that week's fixes, five shipped routines went 15 of 15 on new inputs (Oct 30).
            ${srcA({ path: "eval/results/final/report.md", note: "suite 4" }, "report.md")} ${srcA(L.table_src, "table.md")}</li>
        </ul>
      </div>`;
  }

  // ---- 2: a first run ----
  function renderFirstRun() {
    const R = D.first_run, T = R.total;
    const body = $("#first-run-body");
    body.innerHTML = `
      <span class="eyebrow"><span class="num">2</span> Watch a real first run</span>
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
    show((+new URLSearchParams(location.search).get("step") || 1) - 1);
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
      <span class="eyebrow"><span class="num">3</span> The same task, learned</span>
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

  // ---- table of contents ----
  function renderToc() {
    const secs = [...document.querySelectorAll("main section.sec")];
    const names = { claim: "The claim", "first-run": "A first run", learned: "Learned" };
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
  renderToc();
  // ?only=<section id> shows one section alone (for screenshots: headless Chrome captures from the top).
  const only = new URLSearchParams(location.search).get("only");
  if (only) document.querySelectorAll("main section.sec").forEach((s) => { if (s.id !== only) s.hidden = true; });
  // Sections render after load, so a #section link lands short; scroll again once they're in.
  if (location.hash) { const t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
  $("#foot").innerHTML = `Built by <code>scripts/build_site_data.py</code> from the repo's recordings and eval results. No analytics, no third-party calls.`;
})();
