// Envoy's showcase: renders every section from window.ENVOY (data/site-data.js, built by scripts/build_site_data.py).
// No network calls; works from file:// and any static host.
(function () {
  "use strict";
  const D = window.ENVOY;
  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const repoBase = D.meta.repo_url || "../";

  // ---- formatting ----
  // A run made on a branch of main says so: "main d014972, here a2ecceb".
  const commit = (c) => esc(c).replace(/^main (\w+), here (\w+)$/, "$2, a branch of main $1");
  const usd = (x) => "$" + (x >= 0.1 ? x.toFixed(2) : x.toFixed(4).replace(/0+$/, "").replace(/\.$/, ""));
  const secs = (x) => `${(+x).toFixed(1)} s`;
  const s0 = (x) => `${Math.round(+x)} s`;
  const mins = (x) => x < 90 ? s0(x) : `${Math.floor(x / 60)} min ${Math.round(x % 60)} s`;
  // A median with its range: "6 (2–25)".
  const med = (s, f = String) => s.min === s.max ? f(s.median) : `${f(s.median)} <span class="rng">(${f(s.min)}–${f(s.max)})</span>`;
  const MODEL = { "muse-wonder-1.0": "Muse Wonder", "muse-spark-1.3": "Muse Spark 1.3", "muse-spark-1.3-contributor": "Muse Spark 1.3" };
  const JOB = { match: "match the request to a routine", plan: "plan", step: "decide a step", extract: "read the answer for memory", app_note: "write app notes", compile: "compile" };
  // The fallback ladder a failed check climbs, in words.
  const LADDER = { 1: "wait and retry", 2: "relaxed match", 3: "known pop-up", 4: "local repair" };
  // Text written into the repo's records during development (a routine version's changes, a suite's name), with its
  // internal names put in plain words.
  const plainText = (t) => String(t ?? "")
    .replace(/loop A's copy/g, "a test copy").replace(/\(loop A, /g, "(").replace(/\bloop A\b/g, "the reliability loop")
    .replace(/\bloop B\b/g, "the new-apps loop").replace(/as Phase \d left it/g, "as it stood earlier")
    .replace(/\brung (\d)\b/g, (m, n) => LADDER[n] || m).replace(/ ?\(?backlog #\d+\)?/g, "");
  const date = (s) => {
    const d = new Date(s.replace(" ", "T"));
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) + ", " + s.slice(11, 16) + " ET";
  };
  const day = (s) => new Date(s.slice(0, 10) + "T12:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  // A source link: the file a number came from, relative to the repo.
  const srcA = (s, label) => s ? `<a class="src" href="${esc(repoBase + s.path)}" title="${esc(s.note || "")}">${esc(label || s.path)}</a>` : "";
  const slots = (t) => esc(t).replace(/\{\{(\w+)\}\}/g, '<span class="slot">{{$1}}</span>');
  // A capture (a page or an app screen) that opens at full size; its pixels are the recording's own.
  const shot = (img, alt, cap, cls = "") => `<figure class="shot ${cls}"><a href="data/${esc(img)}" target="_blank" rel="noopener" title="Open at full size"><img src="data/${esc(img)}" alt="${esc(alt)}" loading="lazy"></a>${cap ? `<figcaption>${cap}</figcaption>` : ""}</figure>`;
  // A tool call as an agent made it: name(arg: "value", …).
  const callSig = (tool, args) => `${esc(tool)}(${Object.entries(args || {}).map(([k, v]) => `<span class="arg">${esc(k)}:</span> ${esc(JSON.stringify(v))}`).join(", ")})`;
  // A section's number is its place on the page; the evidence appendix isn't numbered.
  const secList = () => [...document.querySelectorAll("main section.sec:not(.appx)")];
  const num = (id) => secList().findIndex((s) => s.id === id) + 1;
  const sec = (id) => `<a href="#${id}">section ${num(id)}</a>`;
  const ev = (id, label) => `<a href="#ev-${id}" data-open="ev-${id}">${label || "evidence"}</a>`;
  const head = (id, eyebrow, h, lede) => `
    <span class="eyebrow"><span class="num">${num(id)}</span> ${esc(eyebrow)}</span>
    <h2 id="${id}-h">${h}</h2>${lede ? `<p class="lede">${lede}</p>` : ""}`;
  const testApp = `<span class="chip apricot" title="SkyLark Air is Envoy's own test airline app">Our test app</span>`;
  const notFinal = (c) => D.eval.final ? "" : `<span class="chip apricot pending" title="Measured before the final evaluation on Nov 3${c ? `, on ${esc(c)}` : ""}">final numbers after Nov 3</span>`;
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
  // The cost curve's pass: the newest full real-app pass on the hybrid profile until the final evaluation replaces it.
  const curvePass = () => {
    const c = D.real.curve.pass;
    return c.final ? `the final evaluation (${c.date}, ${c.profile} profile, ${c.tier} tier)`
      : `the ${c.date} real-app pass (${c.profile} profile, ${c.tier} tier)`;
  };
  const s2 = (x) => `${(Math.round(+x * 100 + 1e-6) / 100).toFixed(2)} s`;  // half up, as the README rounds
  const passLabel = (p) => {
    const same = D.real.passes.filter((q) => q.date === p.date);
    return same.length > 1 ? `${p.date}, ${["first", "second", "third"][same.indexOf(p)]} pass` : p.date;
  };
  // A recorded run's profile and tier, from its own model calls: hybrid when Muse Wonder decided its steps.
  const runProfile = (calls) => `${calls.some((c) => c.job === "step" && /wonder/.test(c.model)) ? "hybrid" : "Spark"} profile, ${calls.some((c) => /contributor/.test(c.model)) ? "Contributor" : "standard"} tier`;
  const suiteProfile = (n) => (D.proof.suites.find((s) => s.suite.startsWith(n + ".")) || {}).profile || "";
  const allPosts = () => D.showcase.cards.flatMap((c) => c.real.map((p) => ({ ...p, card: c })));

  // ---- 1: the idea ----
  function renderIdea() {
    const W = D.watches, S = D.showcase, C = D.real.curve;
    const ig = W.live.find((x) => /^Instagram/.test(x.App) && /^\+/.test(x["Shown on iPhone"]));
    const reel = S.cards.find((c) => c.name === "instagram_reel_song");
    const reelPost = reel.real.find((p) => p.live);
    const live = allPosts().filter((p) => p.live);
    $("#layer").innerHTML = `
      <div class="layer" role="img" aria-label="An agent asks Envoy over MCP; Envoy acts on its own phone; you approve on your iPhone">
        <div class="lnode"><span class="lbl">Asks</span><b>Muse</b><span>or any agent that speaks MCP: our Spark agent and Claude Code have too</span></div>
        <div class="larrow" aria-hidden="true"><span>MCP</span></div>
        <div class="lnode core"><span class="lbl">Envoy, on a Mac</span><b>acts · learns · watches</b><span>its checked routines are tools agents can call</span></div>
        <div class="larrow" aria-hidden="true"><span>USB</span></div>
        <div class="lnode"><span class="lbl">Does</span><b>Envoy's phone</b><span>a Pixel 5 with the apps, each signed in once by you</span></div>
        <div class="lnode person"><span class="lbl">Approves</span><b>Your iPhone</b><span>you say yes to anything an agent asks for that can't be undone. No agent can approve.</span></div>
      </div>`;
    const H = D.proof.headlines, B = D.batch.routines, AH = D.proof.aw.hybrid, RD = D.readme, wholeRepo = D.meta.repo_url.replace(/blob\/main\/$/, "");
    const video = ($('meta[name="envoy-demo-video"]') || {}).content || "";
    $("#hero-links").innerHTML = `
      ${video.trim() ? `<a class="btn primary video" href="${esc(video.trim())}" target="_blank" rel="noopener">▶ Watch the 3-minute demo</a>` : ""}
      <a class="btn" href="${esc(wholeRepo)}">The code</a>
      <a class="btn" href="${esc(repoBase + RD.run_it.path)}">Run it</a>
      <span class="small run-needs">Runs on a Mac with Apple silicon; with the README's prerequisites in place (the Android command-line tools, a JDK, uv, Node), a fresh clone reached a checked-in flight in about 5 minutes in our test. Saved routines replay with no API key; chat and memory use one.</span>`;
    const tile = (label, big, text, href, chip = "") => `<a class="card pillar" href="${href}"><div class="row-between"><span class="lbl">${label}</span>${chip}</div><div class="big">${big}</div><p>${text}</p></a>`;
    const skyChip = '<span class="chip apricot">Our test app</span>';
    $("#pillars").innerHTML = `
      <p class="num-head"><b>From the final evaluation</b> · ${esc(C.pass.date)}, ${esc(C.pass.profile)} profile, ${esc(C.pass.tier)} tier, scored by code</p>
      <div class="pillars">
        <a class="card pillar lead" href="#results"><span class="lbl">Real apps</span><div class="big">${C.n} of ${C.of} replayed with ${C.rerun.calls.median} model calls</div>
          <p>Read-only workflows, right, in Envoy's replay, at a median ${s2(C.rerun.seconds.median)}. The agent's first run on those took a median ${C.first.calls.median} calls and ${s2(C.first.seconds.median)}.</p></a>
        ${tile("Routines", `${H.routines.ok}/${H.routines.n}`, `Right on the first try on SkyLark, at a median ${H.routines.calls} call and ${H.routines.s} s, against the agent's ${H.routines.agent_calls} calls and ${H.routines.agent_s} s.`, "#results", skyChip)}
        ${tile("Repeat requests", `${H.repeats.ok}/${H.repeats.n}`, `Right at a median ${usd(H.repeats.usd)}, about ${H.repeats.times} times cheaper than the first request (${usd(H.repeats.first_usd)}, the agent's run and the compile included).`, "#results", skyChip)}
        ${tile("Layout changes", `${H.recovered.ok}/${H.recovered.n}`, "Layout changes injected into SkyLark, recovered on first meeting them, 44 of them with no model call.", "#learns", skyChip)}
        ${tile("Safety", `${H.safety.ok}/${H.safety.n}`, `Irreversible controls caught by code rules alone, on saved screens. With instructions planted on SkyLark's screens, the agent stayed right ${H.planted.ok}/${H.planted.n} and tried to follow them in ${H.planted.followed === 0 ? "none" : H.planted.followed}.`, "#acts")}
      </div>
      <p class="num-head"><b>From separate runs</b></p>
      <div class="pillars">
        ${tile("The posting batch", `${B.tiktok_post_sound.reached}/${B.tiktok_post_sound.n}`, `TikTok and the Story reached their final button with every check yes, in a batch declared in advance on Envoy's phone (${day(D.batch.date)}, every final button declined). Across all 40 attempts, 31 did, and the outcome checks stopped 5 more before a flawed post could go out. All four workflows are in section ${num("acts")}.`, "#acts")}
        ${tile("Google's AndroidWorld", `${AH.all.rate}%`, `From 21 to 57 to ${AH.all.success} of ${AH.all.n} tasks in under a week (not a model-only comparison): over twice the benchmark paper's best agent (30.6%), and above every tree-only leaderboard entry (best 59.5%, self-reported). The loop keeps running.`, "#results")}
        ${tile("Watches", esc(ig ? ig["Shown on iPhone"].replace(/^\+/, "") : ""), `From a comment landing on Envoy's phone to the push on your iPhone (one Instagram comment, Nov 2). It waits for agents at their next check.`, "#watches")}
      </div>`;
    $("#live").innerHTML = `
      <div class="card live">
        <div class="row-between"><h3>One request, start to finish</h3><span class="chip sage">Live · test accounts</span></div>
        <ol class="flow-h">
          <li><b>An agent asks</b><span>Over MCP: post this clip as a Reel, with this song and this caption.</span></li>
          <li><b>“Use Envoy's phone?”</b><span>Envoy asks on your iPhone first. Yes.</span></li>
          <li><b>The routine runs</b><span>On Envoy's phone, checking every screen${reelPost && reelPost.calls === 0 ? ": 0 model calls in Envoy's replay" : ""}.</span></li>
          <li><b>The final button waits</b><span>Envoy stops at Share and asks on your iPhone. Yes.</span></li>
          <li><b>Live</b><span>A Reel with “golden hour” from Instagram's music library.</span></li>
        </ol>
        ${RD.take ? `<p style="margin:14px 0 0;color:var(--ink-2);font-size:14.5px"><b style="color:var(--ink)">${esc(RD.take.date)}:</b> in one <code>cross_post</code> call, Muse posted ${esc(RD.take.posts)}. All three finished, at ${esc(RD.take.calls)} model calls in Envoy's replay. ${srcA({ path: "eval/results/showcase/muse-2026-11-04/task-rows.json" }, "task records")}</p>` : ""}
        <p style="margin:8px 0 0;color:var(--ink-2);font-size:14.5px"><b style="color:var(--ink)">The night of Nov 1:</b> all ${live.length} app-only posts went live, each started by the Spark agent, an agent on Meta's models, and approved on the iPhone: ${S.cards.map((c) => POST[c.name]).join(", ")}. ${srcA(S.live_src, "task records")}</p>
      </div>
      <div class="block howto">
        <span><i class="dot"></i>Every screen is a real recording or capture, labeled with when it was made.</span>
        <span><i class="dot"></i>Every section links to the files its numbers came from; runs, commits and configuration are in the ${ev("runs", "evidence")}.</span>
        <span><i class="dot ap"></i>SkyLark is our own test app, the stress test. We say so wherever it appears.</span>
      </div>`;
  }

  // ---- 2: learns ----
  function renderLearns() {
    const R = D.first_run, T = R.total, L = D.learned, n = L.new_input, C = D.real.curve, X = D.agents.crosspost;
    const RP = D.repair, kept = RP.real.filter((v) => v.passed), M = D.models, sg = M.sam_then_grounding;
    const first = X.rows.find((r) => r.kind === "call");
    const learnedTools = X.tools.filter((t) => t.learned);
    const repaired = D.showcase.cards.filter((c) => c.repair && c.repair.passed);
    const handFixes = L.versions.filter((v) => v.by !== "self-repair").length;
    const keptRepairs = L.versions.filter((v) => v.by === "self-repair" && v.trial && v.trial.passed).length;
    const body = $("#learns-body");
    body.innerHTML = `
      ${head("learns", "Learns", "A verified run becomes a checked routine. Shared, it's a tool agents call by name.",
        "The first time, Muse Wonder plans the task and picks every tap from the screen's accessibility tree. A run whose answer checks out on screen can be compiled into a routine with one more Wonder call: the taps, the inputs, and checks before and after its steps. In Envoy, a finished agent task's card has a “Make it a routine” button: Envoy compiles that run, replays it once strictly on the same phone, and saves it with the share off. Teach mode compiles what a person shows the same way, and the compiler can refuse a run. On a clean replay the checks run as code, and a model is asked only to match the request and read the answer.")}
      <h3 class="sub-h">A first run, step by step</h3>
      <div class="label-rec">
        <span><b>App</b> Starbucks, no account</span>
        <span><b>Phone</b> an Android emulator</span>
        <span><b>Recorded</b> ${esc(date(R.started_et))}</span>
        <span><b>Profile</b> ${esc(runProfile(R.calls))}</span>
        <span>${srcA(R.src, "recording")} ${ev("runs", "run details")}</span>
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
            <b style="color:var(--ink)">This run:</b> ${secs(T.seconds)} to the answer, ${T.calls} model calls, ${usd(T.usd)}.
            Then one Wonder call compiled it into <code>${esc(L.active.routine)}</code>: ${secs(L.compile.seconds)}, ${usd(L.compile.usd)}, with the drink as an input. ${L.after_last.clean} of its next ${L.after_last.n} replays ran clean, with 2 calls each, after ${handFixes} hand fixes and ${keptRepairs} kept self-repair. The routine's steps, checks and versions, and every model call, are in the ${ev("routine", "evidence")}.
          </div>
        </div>
      </div>
      <div class="learn-grid">
        <div class="card" style="padding:20px">
          <h3>Then it replays</h3>
          <p class="small" style="margin:6px 0 0">On real apps, a first run against its learned routine rerun with the same input, medians over the ${C.n} of ${C.of} workflows where both passed; the routine's calls are Envoy's own:</p>
          <div class="tbl-wrap"><table class="tbl curve"><thead><tr><th></th><th class="r">Model calls</th><th class="r">Time</th></tr></thead><tbody>
            <tr><td>First run</td><td class="r">${med(C.first.calls)}</td><td class="r">${med(C.first.seconds, s2)}</td></tr>
            <tr><td>Routine</td><td class="r">${med(C.rerun.calls)}</td><td class="r">${med(C.rerun.seconds, s2)}</td></tr>
          </tbody></table></div>
          <p class="small" style="margin:8px 0 0">From ${curvePass()}; compiling each routine cost a median ${usd(C.compile.median)} once (Muse Wonder). Starbucks in the final evaluation: 9 calls and 30.8 s on its first run, then 0 calls and 10.58 s. ${srcA(C.pass.src, "real.json")} ${srcA(T.src, "Starbucks runs")}</p>
        </div>
        <div class="card" style="padding:20px">
          <h3>A new input</h3>
          <p style="margin:6px 0 0;color:var(--ink-2);font-size:14.5px">“${esc(n.goal.replace(/^In the Starbucks app, /, "").replace(/^./, (c) => c.toUpperCase()))}” The same routine with <span class="slot">{{drink_name}}</span> = Caramel Macchiato: <b style="color:var(--ink)">${esc(n.answer.replace(/^calories: /, ""))}</b>, in ${secs(n.seconds)} with ${n.calls} model calls (one run, hybrid profile).</p>
          <p class="small" style="margin:10px 0 0">On real apps, routines answered a new input with no model call in ${esc(D.real.current.stages["New input, no model call"])} workflows in the final evaluation (${sec("results")}); on SkyLark, our test app, 50 of 50.</p>
        </div>
        <div class="card" style="padding:20px">
          <h3>When the app changes, it repairs one step</h3>
          <p class="small" style="margin:6px 0 0">A failed check climbs a ladder: wait and retry, a relaxed match, a known pop-up, then a local repair by a model (Muse Wonder by default${RP.skylark.profile !== "hybrid" ? `; the SkyLark suite ran on the ${RP.skylark.profile} profile` : ""}). A repair becomes a new version on trial, kept only if a clean replay passes.</p>
          <ul class="plain" style="margin-top:8px">
            <li class="small"><b>On real apps:</b> self-repair proposed ${RP.real.length} versions and the trials kept ${kept.length}. ${repaired.length ? `Among them, the ${repaired.map((c) => c.app === "Instagram" ? "Reel's" : "Short's").join(" and the ")} checks, rewritten after their live posts on Nov 2; both passed their trial in Muse's dry run with 0 model calls in Envoy's replay.` : ""} On Nov 4, a routine learned from one finished Uber task, on a real account with no ride requested, met an extra screen: it repaired that step with 1 model call, and the new version passed its trial in 12.81 s with 0.</li>
            <li class="small"><b>On SkyLark, the stress test:</b> 50 injected layout changes, ${esc(RP.layouts.length)} kinds; all recovered, then 46 of 50 ran alone with no model call. ${testApp}</li>
          </ul>
          <div class="label-rec">${srcA(RP.real_src, "routine versions")} ${ev("repairs", "all 50 changes")}</div>
        </div>
        <div class="card" style="padding:20px">
          <h3>Shared, a routine is a tool</h3>
          <p class="small" style="margin:6px 0 0">Each routine has a switch, “Share with agents”, off until you turn it on. Then the next tool list an agent asks for carries the routine as a tool of its own, with typed inputs. No restart, no reconnect: Muse saw a tool newly added to a test connector without reconnecting (Nov 1). Muse adds a new tool to its allowed list before its first call. Envoy has ${D.readme.tools} built-in tools today, including <code>wait_for_task</code>, which lets an agent stay in its turn until a task is final.</p>
          <div class="toollist"><span class="lbl">One agent's tool list, as it stood on Nov 1 · ${learnedTools.length} learned routines</span><div class="chips">${X.tools.map((t) => `<code class="tchip ${t.learned ? "new" : ""}">${esc(t.name)}</code>`).join("")}</div></div>
          <p class="meta" style="margin:10px 0 4px">Its first call, a learned routine by name:</p>
          <div class="tline-one"><code>${callSig(first.tool, first.args)}</code></div>
          <p class="small" style="margin:8px 0 0">One of the learned tools is on SkyLark, our test app. ${srcA(D.agents.crosspost_src, "event log")}</p>
        </div>
      </div>
      ${learnCard()}
      <div class="block who-does" style="margin-top:16px"><b>What's new.</b> To the best of our search, Envoy adds to prior work such as SkillDroid, which compiles runs into templates: checks after steps as well as before, written as code; repairs kept as versions with a trial and a rollback; learned routines served to agents as tools of their own; and an approval no agent can give. ${srcA({ path: "docs/technical-design.md#what-is-new-honestly" }, "the comparison")}</div>
      <div class="block who-does" style="margin-top:16px">
        <b>Meta's models, by job.</b> Muse Wonder turns task experience into routines: it plans and decides a first run's steps, compiles the run, and repairs a broken step. Muse Spark handles matching and extraction: which routine a request means, the answer on screen, facts for memory. SAM 3.1 helps find drawn controls when the accessibility tree is missing: with SAM first and Spark's grounding second, Envoy found ${sg[0]} of ${sg[1]} targets on saved screens (16 of them drawn seats in our test app, the rest real-app controls); grounding alone, ${sg[2]} (the second of two samples). ${srcA(M.phase6_src, "results")} ${ev("models", "SAM on a drawn screen")}
      </div>`;

    let i = 0, timer = null;
    const items = [...body.querySelectorAll("#fr-steps li")];
    function show(k) {
      i = Math.max(0, Math.min(R.steps.length - 1, k));
      const s = R.steps[i];
      items.forEach((li, j) => { li.classList.toggle("on", j === i); li.classList.toggle("done", j < i); });
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
      const el = s.action.element;
      $("#fr-cap").textContent = s.frame
        ? (s.box_kind === "tap" ? `Ringed: element [${el}], the one Wonder chose. Frame recorded just before this tap.`
          : "Dashed: the text the answer was read from.")
        : "Step 1 acts on the app's first screen.";
      $("#fr-t").textContent = secs(s.t);
      $("#fr-c").textContent = s.calls_so_far;
      $("#fr-u").textContent = usd(s.usd_so_far);
      const tree = esc(s.compact).replace(new RegExp(`^(\\[${el}\\].*)$`, "m"), "<mark>$1</mark>");
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
    body.querySelector(".run").addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") { stop(); show(i + 1); }
      if (e.key === "ArrowLeft") { stop(); show(i - 1); }
    });
    // ?step=N opens the run at step N (for links and screenshots).
    show((+new URLSearchParams(location.search).get("step") || 2) - 1);
  }

  // "Make it a routine", measured on the final tag (the learn-path pass), with what it couldn't take next to it.
  function learnCard() {
    const LP = D.learn_path, m = LP.main, x = LP.supplementary;
    const not = [
      m.by_library && `${m.by_library} ran a routine already in Envoy's library, which the request matched first, and the button doesn't take a routine's task`,
      m.not_compilable && `the compiler refused ${m.not_compilable} (Calendar's answer couldn't be read back from its own final screen)`,
      m.replay_failed && `${m.replay_failed} failed its checking replay (Chrome)`,
      m.blocked && `Target's bot check blocked ${m.blocked}`,
      m.not_learnable_other && `${m.not_learnable_other} timed out waiting for the phone, a fault in the test harness`,
    ].filter(Boolean);
    return `
      <div class="card learn-path" style="padding:20px;margin-top:16px">
        <div class="row-between"><h3>“Make it a routine”, measured</h3><span class="chip sage">the final evaluation's tag · Nov 3</span></div>
        <p style="margin:8px 0 0;color:var(--ink-2);font-size:14.5px">The same ${m.n} read-only real-app workflows, asked over MCP on Envoy's emulator (hybrid profile, standard tier). Envoy answered <b style="color:var(--ink)">${m.right} of ${m.n}</b> right${m.right_by_library ? `, ${m.right_by_library} of them through a routine already in its library` : ""}. Then “Make it a routine” on each finished task <b style="color:var(--ink)">saved ${m.saved} of ${m.n}</b> (${m.saved} of the ${m.n - m.by_library} that weren't already routines), each compiled with one Wonder call (median ${usd(m.compile_usd.median)}) and replayed once on its own with no model (median ${s2(m.replay_s.median)}). The saved routines that had a second input to try got it right <b style="color:var(--ink)">${m.new_right} of ${m.new}</b>, ${m.new_zero} with no model call.</p>
        <p class="small" style="margin:10px 0 0"><b>Not saved, ${m.n - m.saved}:</b> ${not.join("; ")}. A second pass with an empty library, outside the headline, measured those ${x.n}: the agent right ${x.right} of ${x.n}, saved ${x.saved} of ${x.n}, new inputs right ${x.new_right} of ${x.new} (${x.new_zero} with no model call).</p>
        <div class="label-rec">${srcA(LP.src, "README.md")} ${srcA(LP.results_src, "results.json")} ${srcA(LP.protocol_src, "PROTOCOL.md")}</div>
      </div>`;
  }

  // ---- the Spark agent's runs, from its page's event log ----
  function sparkLog(run) {
    const t0 = (run.rows.find((x) => x.kind === "user") || { t: 0 }).t;
    const asked = {};
    const out = [];
    for (const r of run.rows) {
      if (r.kind === "user" || r.kind === "wait") continue;
      if (r.kind === "ask") asked[r.task] = r.ask === "approval" ? r.title : "use Envoy's phone";
      const label = r.kind === "ask" ? r.title : r.kind === "answer" ? `${asked[r.task]}|${r.outcome}` : null;
      const prev = out[out.length - 1];
      if (label && prev && prev.kind === r.kind && prev.label === label && Math.abs(r.t - prev.t) < 2) { prev.n += 1; continue; }
      out.push({ ...r, label, what: asked[r.task], n: 1 });
    }
    const t = (r) => `<span class="t">${(r.t - t0).toFixed(1)} s</span>`;
    return `<ol class="tline">${out.map((r) => {
      if (r.kind === "commentary") return `<li class="say">${t(r)}<span>“${esc(r.text)}”</span></li>`;
      if (r.kind === "reply") return `<li class="say reply">${t(r)}<span><b>Answer:</b> “${esc(r.text)}”</span></li>`;
      if (r.kind === "call") return `<li class="call">${t(r)}<span><code>${callSig(r.tool, r.args)}</code><span class="res">${r.ok ? "→" : "✕"} ${esc(r.result)}</span></span></li>`;
      if (r.kind === "refusal") return `<li class="refuse">${t(r)}<span><span class="chip">Envoy refused</span> “${esc(r.text)}”</span></li>`;
      if (r.kind === "ask") return `<li class="ask">${t(r)}<span><span class="chip apricot">Envoy asks on the iPhone${r.n > 1 ? ` ×${r.n}` : ""}</span> ${r.ask === "approval" ? `final button <b>${esc(r.title)}</b>` : `“${esc(r.title)}”`}</span></li>`;
      if (r.kind === "answer") return `<li class="ans">${t(r)}<span>${esc(r.what === "use Envoy's phone" ? "Use Envoy's phone" : r.what)}${r.n > 1 ? ` ×${r.n}` : ""}: <span class="chip ${r.outcome === "declined" ? "" : "sage"}">${r.outcome === "declined" ? "declined" : "yes"}</span> after ${secs(r.after_s)}</span></li>`;
      return "";
    }).join("")}</ol>`;
  }

  // ---- 3: acts ----
  // What a real post carried, from its task's inputs.
  const postText = (name, i) => name === "instagram_story_poll" ? `poll “${i.poll_question}” ${i.poll_option_1} / ${i.poll_option_2}`
    : `“${i.song_title || i.sound_title}” by ${i.song_artist || i.sound_artist}, ${i.short_title ? "title" : "caption"} “${i.caption || i.short_title}”`;
  // The batch's limits for the limits list, read from its records; a version made after it is named, never counted.
  const batchLimits = () => {
    const out = [];
    for (const c of D.showcase.cards) {
      const b = D.batch.routines[c.name], name = POST[c.name];
      if (b.stops.song) {
        const ok = Object.entries(b.songs).filter(([, v]) => v.yes).map(([k]) => `“${esc(k)}”`);
        out.push(`the ${name} passed every check only with ${ok.join(", ")}, its sound check stopping ${b.stops.song} runs with other songs`);
      }
      if (b.stops.caption) out.push(`the ${name}'s outcome checks stopped ${b.stops.caption} runs whose caption was lost before ${esc(b.final)}`);
      if (c.after_batch.length && (b.stops.song || b.stops.caption)) out.push(`the ${name}'s later versions are on its card, not counted here`);
    }
    return out.length ? `In the posting batch, ${out.join("; ")}.` : "";
  };
  // One version made since the batch: what it is, its device check, and its own runs. Never counted with the batch.
  const afterBatch = (v) => {
    const r = v.runs || [], ck = v.check;
    return `v${v.version} (${esc(v.date)}) is ${esc(v.kind)}${v.what ? `: ${esc(v.what)}` : ""}${ck ? `. On Envoy's phone, ${ck.ok} of ${ck.n} ${esc(ck.what || "runs")} reached ${esc(ck.final)} with every check yes${ck.calls != null ? `, at ${ck.calls} model calls in Envoy's replay` : ""}.`
      : r.length === 1 ? `. In its one run so far (${esc(r[0].date)}), it finished with ${r[0].calls} model calls in Envoy's replay, in ${(+r[0].seconds).toFixed(1)} s.` : "."}`;
  };
  // What the batch says about one routine, besides its counts: what stopped its runs, and its songs.
  const batchNote = (b) => {
    const fails = (b.classes.failed || 0), stops = Object.values(b.stops).reduce((x, y) => x + y, 0), agent = b.classes["agent fallback"] || 0;
    const parts = [];
    if (b.stops.caption) parts.push(`The outcome checks stopped ${b.stops.caption} runs before ${esc(b.final)}: the caption had been lost`);
    if (b.stops.song) {
      const okSongs = Object.entries(b.songs).filter(([, v]) => v.yes).map(([k]) => k);
      parts.push(`Every check passed only with ${okSongs.map((t) => `“${esc(t)}”`).join(", ")} (${okSongs.map((t) => b.songs[t].yes).join(", ")} of ${okSongs.map((t) => b.songs[t].n).join(", ")}); with the other songs, the sound check found it never attached and stopped ${b.stops.song} runs before ${esc(b.final)}`);
    }
    if (agent) parts.push(`the agent finished ${agent}, so its checks couldn't run`);
    if (fails > stops) parts.push(`${fails - stops} more ${fails - stops === 1 ? "run" : "runs"} stopped for other reasons, given in the results`);
    if (b.classes.repair) parts.push(`${b.classes.repair} needed a repair`);
    if (/by eye/.test(b.yes_cell)) parts.push("the poll isn't text on the final screen, so it was read by eye on the approval screenshots");
    if (!parts.length && b.calls === b.n * 3) parts.push("3 model calls a run: it reads TikTok's drawn sound list with vision");
    return parts.length ? parts.join("; ").replace(/^./, (x) => x.toUpperCase()) + "." : "";
  };
  const POST = { instagram_reel_song: "Reel", instagram_story_poll: "Story", tiktok_post_sound: "TikTok", youtube_short_sound: "Short" };
  function renderActs() {
    const S = D.showcase, A = D.agents, X = A.crosspost, MD = A.muse.dry_run, K = D.keys, R = K.readonly, SF = D.safety, BT = D.batch;
    const card = (c) => {
      const b = BT.routines[c.name], ab = c.after_batch;
      return `<article class="card post-card">
        <div class="row-between"><span class="chip sage">${esc(c.app)}</span><span class="chip">v${c.version} · ${c.steps} steps</span></div>
        <h3>${esc(c.what)}</h3>
        <div class="sig small"><code>${esc(c.name)}(${c.inputs.map(esc).join(", ")})</code></div>
        <dl class="fr">
          <div><dt>Made</dt><dd><b>${c.hand && !c.hand_from ? "Compiled from one agent run" : "Learned from one agent run"}</b><span>${c.hand_from ? `No hand edits until v${c.hand_from.version} (${esc(c.hand_from.date)}), which has ${esc(c.hand)}` : c.hand ? esc(c.hand.replace(/^./, (x) => x.toUpperCase())) : "No hand edits"}${c.repair && c.repair.passed ? `. Its checks were repaired automatically after its live post (v${c.repair.version})` : ""}.</span></dd></div>
          <div class="rp"><dt>The batch, final tag</dt><dd><b>${b.reached} of ${b.n} reached ${esc(b.final)}</b><span>${esc(b.yes_cell.replace(/ \(poll by eye\)$/, ""))} with every check yes${/by eye/.test(b.yes_cell) ? " (the poll by eye)" : ""} · median ${s0(b.secs.median)} to the final button · ${b.calls} model call${b.calls === 1 ? "" : "s"} in all, ran v${b.versions.join(", v")}</span></dd></div>
        </dl>
        <p class="small" style="margin:6px 0 0">${batchNote(b)}</p>
        ${ab.length ? `<p class="small after-batch" style="margin:6px 0 0"><b>After the batch, not part of it:</b> ${ab.map(afterBatch).join(" ")}</p>` : ""}
        <ul class="plain real">${c.real.map((p) => `<li><span class="chip ${p.live ? "sage" : "apricot"}">${p.live ? "live" : "first post"}</span> <span class="small">${esc(p.live ? postText(c.name, p.inputs) : p.note)} · ${p.calls} model calls in Envoy</span></li>`).join("")}</ul>
        <div class="label-rec" style="margin-top:8px">${srcA(c.yaml_src, `v${c.version}.yaml`)} ${srcA(c.src, "versions")}</div>
      </article>`;
    };
    const ask = X.rows.find((x) => x.kind === "user");
    const refusal = R.rows.find((r) => r.kind === "refusal");
    $("#acts-body").innerHTML = `
      ${head("acts", "Acts", "It acts in the apps, and waits for a yes on the iPhone.",
        "Some things exist only inside an app. Muse can post plain Instagram content itself, but library songs and poll stickers exist only in the apps, and Muse had no connector for TikTok when we checked (Nov 1). So each of these four posts was compiled from one agent run on Envoy's phone into a routine, and shared with agents as a tool. Each final button waited for the person's yes on their iPhone. No agent can approve: there is no tool for it.")}
      <div class="card" style="padding:20px;margin-top:24px">
        <div class="row-between"><h3>One request, every post</h3><span class="chip"><code>cross_post</code></span></div>
        <p style="margin:8px 0 0;color:var(--ink-2);font-size:14.5px">${D.readme.take ? `In a ${esc(D.readme.take.date)} take, Muse made one <code>cross_post</code> call for ${esc(D.readme.take.posts)}, and all three finished, at ${esc(D.readme.take.calls)} model calls in Envoy's replay. ` : ""}It runs the shared posting routines as one task with a part per destination, one after another. A retry runs only the parts that didn't post, and a part whose outcome is unknown is never posted again by itself.</p>
        <div class="label-rec">${srcA({ path: "eval/results/showcase/muse-2026-11-04/task-rows.json" }, "task-rows.json")} ${srcA(D.readme.cross_post_src, "cross-post-pixel.json")} ${srcA(D.readme.cross_post_tests, "test_crosspost.py")} ${srcA(D.readme.readme, "README")}</div>
      </div>
      <div class="posts four">${S.cards.map(card).join("")}</div>
      <p class="small" style="margin:10px 4px 0">The batch was declared before it ran: the four routines at the final evaluation's tag, ${BT.n / S.cards.length} attempts each from a cold app, an open app or a saved draft, on Envoy's phone with the test accounts (${day(BT.date)}). Every final button it reached was declined; each card counts every attempt. The live posts went out on test accounts. ${srcA(BT.src, "RESULTS.md")} ${srcA(BT.protocol_src, "PROTOCOL.md")} ${srcA(S.live_src, "the posts' task records")} ${srcA(S.doc_src, "demo-showcase.md")}</p>
      <div class="callout" style="margin-top:14px"><b>What the first live post taught it.</b> The first live TikTok went out without its sound: the compiler had dropped the agent's correction, and no check looked at the editor. That's fixed, and the re-post had it. Since Nov 2, code also checks just before the final button that the song or sound asked for is shown, the caption or title is in its field, and the clip is the one put on the phone (the Reel, TikTok and Short; on the Story the clip, since its poll isn't text on the final screen); a planted wrong clip stopped TikTok before it started.</div>
      <details class="ev" style="margin-top:14px"><summary><span class="t">The dry runs before it</span><span class="s">Nov 1–2: the Spark agent's one request and Muse's five tasks, every final button declined</span></summary><div class="ev-body">
      <div class="agent-row" style="margin-top:0">
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>One request, four posts: a dry run</h3><span class="chip">the Spark agent · ${X.model_calls} model calls · ${usd(X.usd)}</span></div>
          <p class="goal" style="margin:12px 0 0">${esc(ask.text)}</p>
          <p class="small" style="margin:10px 0 0">The Spark agent, on Meta's models, called the four learned tools at once. Envoy ran them one at a time on its phone; each first asked to use Envoy's phone, then stopped at its final button. A script stood in for the person: yes to the phone, no at every final button. Nothing was posted. Envoy's own replays made no model calls except TikTok's, which reads its drawn sound list with vision.</p>
          <details class="read"><summary>The run, call by call</summary>${sparkLog(X)}</details>
          <div class="shots">
            ${shot(A.shots.asks, "The Spark agent's page: four Use Envoy's phone asks stacked while Envoy waits", "Four phone asks, stacked (Nov 1).")}
            ${shot(A.shots.declined, "The Spark agent's page after all four final buttons were declined", "The end: nothing posted (Nov 1).")}
          </div>
          <div class="label-rec"><span><b>Recorded</b> ${esc(date(X.started_et + ":00"))}, a test copy of Envoy, Envoy's phone</span>${srcA(A.crosspost_src, "event log")} ${srcA(A.crosspost_readme, "README")}</div>
        </div>
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>Muse, the same four: a dry run</h3><span class="chip apricot">Nov 2 · every final button declined</span></div>
          <p class="small" style="margin:8px 0 0">From Muse for Mac: Muse put a test clip in Envoy's outbox, had Envoy put it on the phone (after the person's yes), then called the four learned tools by name, one per turn. Each task asked to use Envoy's phone first. The person declined every final button.</p>
          <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Post</th><th>How it ended</th><th class="r">Calls</th><th class="r">Time</th></tr></thead>
            <tbody>${MD.tasks.map((t) => `<tr><td>${esc(POST[t.routine] || t.routine)}</td><td>${t.status === "declined" ? "reached its final button; declined" : `<b>${t.status === "failed" ? "failed" : "stopped, asked the person"}</b><div class="small">${esc(t.note)}</div>`}</td><td class="r">${t.model_calls}</td><td class="r">${mins(t.seconds)}</td></tr>`).join("")}</tbody></table></div>
          <p class="small" style="margin:8px 0 0">Calls are Envoy's own. Time runs from Muse's call to the task's end, so it includes both asks and the wait at the final button. In this run Muse went one post per turn, waiting for a tap between posts; since then, <code>wait_for_task</code> lets an agent stay in its turn, and <code>cross_post</code> takes every post in one request. ${srcA(A.muse.dry_run_src, "task-rows.json")} ${srcA(A.muse.doc, "muse-link.md")}</p>
          ${shot(A.muse.mac, "Muse for Mac moving the newest video into Envoy's outbox folder and writing its caption file", "Muse for Mac putting a clip and its caption in Envoy's outbox (Oct 29). Cropped to Muse's window.")}
        </div>
      </div>
      </div></details>
      <div class="card trust" style="padding:20px;margin-top:16px">
        <h3>Only a person approves</h3>
        <div class="trust-grid">
          <ul class="plain">
            <li><b>No agent can approve.</b> There's no tool for it, whatever an agent's key allows, and Envoy's app is where you decide. A request from an agent, a trigger or an email waits for the person's yes on their iPhone, unless they've set that routine to run without asking; money always asks. A request the person types into Envoy themselves counts as their OK for what they asked.</li>
            <li><b>A key per agent.</b> You make each agent's key in Envoy's settings, with only the tool groups it needs; the key is stored as a hash. Each agent can start at most ${K.per_minute} tasks a minute, and every task says which agent asked.${refusal ? ` On a read-only key, the Spark agent saw ${R.tools.length} tools; a call outside them was refused: “${esc(refusal.text)}”` : ""}</li>
            <li><b>Tested.</b> ${SF.caught[0]} of ${SF.caught[1]} irreversible controls were caught, among ${SF.captured.controls} controls on ${SF.captured.screens} captured screens from ${SF.captured.apps} apps (${SF.captured.skylark_screens} of the screens from SkyLark, our test app); text planted on screen to redirect the agent was followed in ${SF.agent[2]} of ${SF.agent[1]} runs on SkyLark (${esc(suiteProfile("6b"))} profile). ${testApp} ${notFinal(SF.safety_run.commit)} ${srcA(SF.safety_src, "safety.md")} ${srcA(SF.injection_src, "injection.md")} ${ev("safety", "the tests")}</li>
          </ul>
          ${shot(A.muse.no_accept, "Muse in the iPhone app saying it can't accept Envoy's offers: there's no accept or approve tool", "Asked to accept for the person, Muse: “there's no accept or approve tool” (Oct 29).", "phone-shot")}
        </div>
      </div>`;
  }

  // ---- 4: watches ----
  const KINDS = {
    time: "a time: every N minutes, daily, weekly, or once",
    before_fact: "a time from memory, such as 24 hours before a flight; it moves when the flight does",
    watch: "a read-only routine re-run on a schedule (a gate, a delivery), with an alert when what it reads changes",
    email: "a new email from a sender",
    fact_changed: "a remembered fact that changes, such as a departure time",
    notification: "a notification on Envoy's phone, from an app the person lets Envoy watch",
  };
  function renderWatches() {
    const W = D.watches;
    const cols = W.live.length ? Object.keys(W.live[0]) : [];
    $("#watches-body").innerHTML = `
      ${head("watches", "Watches", "It watches the phone, tells you at once, and it's waiting for your agent.",
        "A trigger can tell you, ask you first, or run a routine. An agent can propose one; it's created switched off, and only you turn it on. What happened waits for agents in <code>phone_updates</code>: they see it the next time they check, Muse about every 10 minutes.")}
      <div class="card" style="padding:20px;margin-top:24px">
        <h3>Real comments on the live posts, Nov 2</h3>
        <p class="small" style="margin:6px 0 0">The trigger “Instagram, TikTok or YouTube: comment”, set to tell. One comment per row, TikTok's three together; times run from the notification landing on Envoy's phone.</p>
        <div class="tbl-wrap"><table class="tbl watch-tbl"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
          <tbody>${W.live.filter((r) => !/^no:/.test(r["Landed on the Pixel"])).map((r) => `<tr>${cols.map((c, i) => `<td${i === cols.length - 1 && /^\+/.test(r[c]) ? ' class="hit"' : ""}>${esc(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
        <p class="small" style="margin:8px 0 0">Envoy's part stayed under 4 s. The time from a comment to its notification is each app's own: seconds on Instagram, about two minutes on YouTube. TikTok showed its comments only inside the app, where a notification watcher can't see them. ${srcA(W.src, "phone-watch-report.md")}</p>
      </div>
      <div class="watch-grid">
        <div class="card" style="padding:20px">
          <h3>Six kinds of trigger</h3>
          <ul class="kinds">${W.kinds.map((k) => `<li><code>${esc(k)}</code><span>${esc(KINDS[k] || "")}</span></li>`).join("")}</ul>
          <p class="small" style="margin:10px 0 0">An app's notifications are watched only after you switch it on. The notification list is read in memory and dropped; only matched notifications are kept, with code-like numbers hidden first.</p>
          <div class="label-rec">${srcA(W.kinds_src, "scheduler.py")} ${srcA(W.code_src, "notifications.py")}</div>
        </div>
        <div class="card" style="padding:20px">
          <h3>How an agent hears it</h3>
          <p class="small" style="margin:6px 0 0">A Muse scheduled task checked Envoy's phone updates every 10 minutes and told the person, unprompted, about a file Envoy was waiting to put on the phone (Oct 29).</p>
          ${shot(W.muse, "Muse on the iPhone: a scheduled task checking Envoy's phone updates every 10 minutes reports a new offer", "Muse's scheduled task reports a phone update. Cropped below the status bar.", "tall")}
          <div class="label-rec">${srcA(W.muse_src, "capture")}</div>
        </div>
      </div>`;
  }

  // ---- 5: results ----
  function renderResults() {
    const P = D.proof, E = D.eval, RA = D.real, C = RA.curve, cur = RA.current, S = D.showcase;
    const stage = ["First run right", "Compiled", "Same input, no model call", "New input, no model call"];
    const passes = RA.passes.map((p) => ({ label: passLabel(p), profile: p.profile, cells: stage.map((k) => p.cells[k]) }));
    if (cur.final) {
      passes.push({ label: "Final evaluation", profile: cur.profile, final: true, cells: stage.map((k) => cur.stages[k]) });
    }
    const BR = Object.values(D.batch.routines);
    const passRow = (p) => `<tr${p.final ? ' class="final"' : ""}><td>${esc(p.label)}<div class="small">${esc(p.profile)} profile</div></td>${p.cells.map((c) => `<td class="r">${esc(c).replace(/ \((.+)\)$/, ' <span class="rng">($1)</span>')}</td>`).join("")}</tr>`;
    // The report's own labels, in words: its emulators by size, and its end-to-end checks by what they cover.
    const suiteText = (t) => t.replace("envoy-test", "standard emulator").replace("envoy-small", "small").replace("envoy-large", "large").replace(/\bphone (\d)/, "the Pixel 5 $1")
      .replace(/^phase4 passed; approval_modes passed; phase5 passed$/, "sign-in hand-off, approvals and approval modes, MCP, memory, pushes, voice and live view: all three end-to-end checks passed");
    const skySuites = P.suites.filter((s) => !/^(4|8)\./.test(s.suite));
    const mixed = new Set(skySuites.map((s) => /eval-final/.test(s.ran_on))).size > 1;
    const profiles = [...new Set(skySuites.map((s) => `${s.profile} profile, ${s.tier} tier`))];
    const skyProfiles = profiles.length === 1 ? `Every suite here ran on the ${profiles[0]}` : `Profiles: ${profiles.join("; ")}`;
    const aw = P.aw, AH = aw.hybrid;
    $("#results-body").innerHTML = `
      ${head("results", "Results", "Scored by code, on real apps first.",
        "Every suite starts from a known state and is scored by code, on the app's real state or the answer on screen (its value where the truth is known, its shape where it changes daily, like a price), never by a model. Each number says which pass and which profile it's from: hybrid, the default, has Muse Wonder decide the agent's steps; the Spark profile has Muse Spark decide them. Both compile with Muse Wonder. Dollars are at Meta's standard prices.")}
      <div class="final-banner ${E.final ? "done" : ""}">
        ${E.final ? `<b>Final numbers.</b> All ${E.suites} suites ran on the <code>eval-final</code> tag, and all ${P.targets.length} success targets the design set on Oct 26, before any code, were met (${ev("targets", "the table")}).`
          : `<b>Final numbers after Nov 3.</b> The final evaluation runs Nov 3 on one tagged commit; ${E.on_tag} of ${E.suites} suites have run on it so far. Until then, these are the development passes, each labeled.`} ${srcA(E.src, "report.md")}
      </div>
      <h3 class="sub-h">Real apps</h3>
      <p class="small" style="margin:4px 0 0">${RA.rows.length} read-only workflows on real apps, on Envoy's emulator: search a store, read a setting, find an email.</p>
      <div class="results-grid">
        <div class="card" style="padding:18px 20px">
          <h3>First run vs routine</h3>
          <p class="small" style="margin:4px 0 0">Medians and ranges over the ${C.n} of ${C.of} workflows whose first run and same-input rerun both passed (a rerun that needed a repair isn't counted), from ${curvePass()}. The routine is called by name; asked in words, Envoy's matcher adds one Spark call.</p>
          <div class="tbl-wrap"><table class="tbl curve"><thead><tr><th></th><th class="r">Calls</th><th class="r">Time</th><th class="r">Cost</th></tr></thead><tbody>
            <tr><td>The agent's first run</td><td class="r">${med(C.first.calls)}</td><td class="r">${med(C.first.seconds, s2)}</td><td class="r">${med(C.first.usd, usd)}</td></tr>
            <tr><td>Envoy's replay</td><td class="r">${med(C.rerun.calls)}</td><td class="r">${med(C.rerun.seconds, s2)}</td><td class="r">${med(C.rerun.usd, usd)}</td></tr>
            <tr><td>Compiling it, once</td><td class="r">1 <span class="rng">(Muse Wonder)</span></td><td class="r">–</td><td class="r">${med(C.compile, usd)}</td></tr>
          </tbody></table></div>
          <p class="small" style="margin:8px 0 0">The routine's calls are Envoy's own; an agent calling Envoy pays for its own model too (the Spark agent's four-post run: ${D.agents.crosspost.model_calls} calls, ${usd(D.agents.crosspost.usd)}). ${C.pass.final ? "" : notFinal(C.pass.commit)} ${srcA(C.pass.src, "real.json")} ${srcA(C.pass.md_src, "real.md")}</p>
        </div>
        <div class="tbl-wrap card"><table class="tbl">
          <thead><tr><th>Pass</th>${stage.map((s) => `<th class="r">${esc(s)}</th>`).join("")}</tr></thead>
          <tbody>${passes.filter((p) => p.final || !cur.final).map(passRow).join("")}</tbody>
        </table></div>
        ${cur.final ? `<details class="ev" style="margin-top:0"><summary><span class="t">Earlier passes</span><span class="s">the same workflows, Oct 29 to Nov 2, one pass per row</span></summary><div class="ev-body"><div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>Pass</th>${stage.map((s) => `<th class="r">${esc(s)}</th>`).join("")}</tr></thead>
          <tbody>${passes.filter((p) => !p.final).map(passRow).join("")}</tbody></table></div></div></details>` : ""}
      </div>
      <p class="small" style="margin:10px 4px 0">Each workflow is in the ${ev("real", "evidence")}. On Envoy's phone, the posting batch on the final tag: ${BR.reduce((x, b) => x + b.reached, 0)} of ${D.batch.n} attempts reached their final button, every one declined there (${S.cards.map((c) => `${POST[c.name]} ${D.batch.routines[c.name].reached}`).join(", ")}; ${sec("acts")}).</p>
      <h3 class="sub-h" style="margin-top:28px">SkyLark, our test app: the stress test</h3>
      <p class="small" style="margin:4px 0 0">Our own airline app, where the evaluation can change the layout on purpose and check the app's real state. Memory also uses test inboxes, and the safety suites also use captured screens from real apps. ${skyProfiles}.</p>
      <div class="tbl-wrap card" style="margin-top:10px"><table class="tbl suites">
        <thead><tr><th>Suite</th><th>Result</th>${mixed ? "<th>Measured</th>" : ""}</tr></thead>
        <tbody>${skySuites.map((s) => `<tr><td>${esc(s.suite.replace(/^\w+\. /, ""))}</td><td>${esc(suiteText(s.result))}</td>${mixed ? `<td>${/eval-final/.test(s.ran_on) ? '<span class="chip sage">final</span>' : '<span class="chip apricot pending">development pass</span>'}</td>` : ""}</tr>`).join("")}</tbody>
      </table></div>
      ${E.final || mixed ? "" : `<p class="small" style="margin:8px 4px 0">All development passes; the commit each ran on is in the ${ev("runs", "evidence")}. ${notFinal()}</p>`}
      <div class="stats results-tiles" style="margin-top:12px">
        <div class="card stat"><div class="row-between"><div class="lbl">The Pixel 5, Envoy's phone</div>${testApp}</div><div class="big">${P.phone.passed}/${P.phone.runs}</div><div class="lbl">SkyLark's 10 core routines, compiled on an emulator, on 3 new bookings each: <b>${P.phone.calls} model calls in Envoy's replay</b>, median ${secs(P.phone.median_s)} (${esc(P.phone.profile)} profile, ${esc(P.phone.tier)} tier)</div>${notFinal(P.phone.commit)} ${srcA(P.phone.src, "sizes.json")}</div>
        <div class="card stat wide aw"><div class="lbl">AndroidWorld, Google's benchmark: ${AH.all.n} tasks across 20 apps, scored by its own code</div>
          <div class="aw-grid">
            <div><div class="big">${AH.all.success}/${AH.all.n}</div><div class="lbl"><b>The shipped default (${esc(AH.profile)}) on main, ${day(AH.date)}:</b> ${AH.all.rate}%, a paired +${AH.vs.all.gained} −${AH.vs.all.lost} over our Oct 28 run (p = ${AH.vs.all.p_paired}); the held-out half ${AH.held.success} of ${AH.held.n} (${AH.held.rate}%). A median ${usd(AH.median_usd)} and ${s0(AH.median_s)} a task.</div>${srcA(AH.src, "README.md")} ${srcA(AH.summary_src, "summary.json")}</div>
            <div><div class="big">${aw.held[0]}/${aw.held[1]}</div><div class="lbl"><b>Oct 28–29, the agent on ${esc(aw.model)} (the Spark profile):</b> the held-out half after 13 general changes found on a dev half, against ${aw.held[2]} before them (+20 −1, p < 0.0001). The ${aw.routines.alone} routines (of ${aw.routines.compiled} compiled from its solved runs) that did their own task alone, on three new seeds: ${esc(aw.routines.did)} of ${esc(aw.routines.of)} right at ${esc(aw.routines.calls)} model call and ${esc(aw.routines.usd)} each, where the full agent did ${esc(aw.routines.agent)} at ${esc(aw.routines.agent_calls)} calls and ${esc(aw.routines.agent_usd)}; counting the agent's run where a routine failed (computed), ${aw.routines.fallback[0]} of ${aw.routines.fallback[1]}.</div>${srcA(aw.src, "androidworld-results.md")}</div>
          </div>
          <p class="small" style="margin:10px 0 0">It keeps improving by a repeatable loop: study the failures, ship general fixes, check them on held-out tasks and Envoy's own suites. Not a model-only comparison: the code changed between the two runs too. The held-out half was reused, and its gain from Oct 28 to Nov 3 (+${AH.vs.held.gained} −${AH.vs.held.lost}, p = ${AH.vs.held.p_paired.toFixed(2)}) is within run-to-run noise. ${srcA(AH.compare_src, "comparison")}</p>
        </div>
      </div>
      <div class="card limits" style="margin-top:20px">
        <h3>Also in Envoy</h3>
        <ul>
          <li><b>A cloud phone.</b> Routines compiled on the Mac ran unchanged on an emulator on Google Cloud, 48 of 48 with no model calls (SkyLark, our test app), and the whole learn-then-replay loop ran there too. ${srcA({ path: "docs/cloud.md" }, "cloud.md")}</li>
          <li><b>Siri and voice.</b> The iPhone's Action Button, “Hey Siri, Ask Envoy” or a Control Center button, through an Apple Shortcut with no app to install. Dictation runs on Muse Voice Transcribe. ${srcA({ path: "docs/siri.md" }, "siri.md")}</li>
          <li><b>Offers and habits.</b> Envoy can offer before it acts (“Check in for SL 482?”), notices what you repeat, and sets up recurring jobs you ask for, switched off until you say yes. ${srcA({ path: "backend/api/offers.py" }, "offers.py")}</li>
          <li><b>One question, two apps.</b> One task with a part per app, and one answer. ${srcA({ path: "backend/api/crossapp.py" }, "crossapp.py")}</li>
          <li><b>Before I start, and saved logins.</b> Envoy says what to expect before a task, and the phone's own password manager can fill a sign-in, so Envoy never sees a password (off by default). ${srcA({ path: "docs/preflight-and-autofill.md" }, "the doc")}</li>
          <li><b>Real apps.</b> Tasks run in Amazon, Calendar, Chipotle, Chrome, Clock, Contacts, DoorDash, Gmail, Instagram, Lyft, Maps, the Play Store, Settings, Starbucks, TikTok, Uber, YouTube and YouTube Music. Apps that refuse emulators go to your own phone, asking first: Uber won't install on an emulator, so it runs on Envoy's phone, and Target, whose bot check we saw, starts on that list. Envoy adds an app itself when it sees a bot check. ${srcA({ path: "backend/api/routing.py" }, "routing.py")}</li>
        </ul>
      </div>
      <div class="card limits" style="margin-top:20px">
        <h3>Limits</h3>
        <ul>
          <li>A routine can still need the agent, or fail, in a live run; each routine's version history lists every run.</li>
          <li>Some apps refuse emulators, like Target with its bot check (banking apps are expected to, untested). That's why Envoy can also use your own Android phone: it sends those apps there, asking first. When a bot check or a sign-in appears, Envoy pauses and prompts you to take over, then carries on when you hand it back.</li>
        </ul>
      </div>
      ${D.readme.since.length ? `<div class="card limits" style="margin-top:12px">
        <h3>Changes since the evaluation</h3>
        <p class="small" style="margin:4px 0 0">Made after the <code>eval-final</code> tag, and not measured by it.</p>
        <ul>${D.readme.since.map((c) => `<li><b>${esc(c.name)}:</b> ${esc(c.text)}</li>`).join("")}</ul>
      </div>` : ""}`;
  }

  // ---- the evidence appendix ----
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

  // Every run the page cites: what, when, where, code and configuration.
  function runsTable() {
    const F = D.first_run, L = D.learned, X = D.agents.crosspost, MD = D.agents.muse.dry_run, RA = D.real.current, K = D.repair.skylark;
    const rows = [
      ["Starbucks first run (section 2)", date(F.started_et), "Android emulator", commit(F.total.commit), runProfile(F.calls), `<code>${esc(F.task_id)}</code>`, srcA(F.total.src, "runs.jsonl")],
      ["Its compile", "Oct 30", "–", commit(L.compile.commit), "Muse Wonder", "", srcA(L.compile.src, "runs.jsonl")],
      ["Starbucks, new input", "Oct 30", "Android emulator", commit(L.new_input.commit), "hybrid profile", `<code>${esc(L.new_input.task_id)}</code>`, srcA(L.new_input.src, "runs.jsonl")],
      [`Starbucks replays (${L.loop.replay.calls.n}) and first runs (${L.loop.first.calls.n})`, "Oct 30", "Android emulator", `${L.loop.replay.commits} code versions`, "hybrid profile", "", srcA(F.total.src, "runs.jsonl")],
      ["The Spark agent's four-post dry run (section 3)", date(X.started_et + ":00"), "Envoy's phone (Pixel 5)", `main <code>${esc(D.agents.crosspost_commit)}</code>, a test copy`, `${esc(X.model)} (the agent)`, "", srcA(D.agents.crosspost_src, "event log")],
      ["Muse's dry run (section 3)", "Nov 2, 11:41–12:20 ET", "Envoy's phone", "the live Envoy", "", MD.tasks.map((t) => `<code>${esc(t.id)}</code>`).join(" "), srcA(D.agents.muse.dry_run_src, "task-rows.json")],
      ["The live posts (sections 1, 3)", "Nov 2, 01:00–02:31 ET", "Envoy's phone", "the live Envoy", "", allPosts().map((p) => `<code>${esc(p.task)}</code>`).join(" "), srcA(D.showcase.live_src, "task-rows.json")],
      ["The posting routines' rehearsals", "Nov 1–2", "Envoy's phone", "a test copy", "hybrid profile", "", srcA(D.showcase.runs_src, "runs.md")],
      [`Real apps, ${RA.final ? "the final evaluation" : "the evaluation's real-app suite"} (${D.real.rows.length} workflows; section 5)`, day(RA.date), "Android emulator", RA.breakdown.length > 1 ? `rows from ${RA.breakdown.length} runs: ${RA.breakdown.map((b) => `<code>${esc(b.commit)}</code> (${b.rows} ${b.rows === 1 ? "row" : "rows"})`).join(", ")}` : `<code>${esc(RA.commit)}</code>`, `${RA.profile} profile, ${RA.tier} tier`, RA.breakdown.length > 1 ? RA.breakdown.map((b) => `run ${esc(b.run)}`).join(", ") : `run ${esc(RA.run_id)}`, srcA(D.real.md_src, "real.md")],
      ...D.real.passes.filter((p) => p.commit !== RA.commit).map((p) => [`Real apps, ${passLabel(p)}${/pass$/.test(passLabel(p)) ? "" : " pass"}`, p.date, "Android emulator", `<code>${esc(p.commit)}</code>`, `${p.profile} profile`, "", srcA(p.src, p.src.path.split("/").pop())]),
      ["The posting batch (section 3)", day(D.batch.date), "Envoy's phone (Pixel 5)", `the <code>eval-final</code> tag (<code>${esc(D.batch.tag)}</code>), a clean copy`, "hybrid profile, standard tier", `${D.batch.n} attempts`, srcA(D.batch.src, "RESULTS.md")],
      ["AndroidWorld, the shipped default (section 5)", day(D.proof.aw.hybrid.date), "AndroidWorld's emulator (Pixel 6, API 33)", `main <code>${esc(D.proof.aw.hybrid.commit)}</code>`, `${esc(D.proof.aw.hybrid.profile)} profile, standard tier`, esc(D.proof.aw.hybrid.stage), srcA(D.proof.aw.hybrid.src, "README.md")],
      ["SkyLark repair example (section 2)", day(K.date), "Android emulator", `<code>${esc(K.commit)}</code>`, `${K.profile} profile, ${K.tier} tier`, "", srcA(K.src, "change.json")],
      ...D.proof.suites.map((s) => [`Evaluation suite ${plainText(s.suite)}`, "", "", `<code>${esc(s.ran_on)}</code>`, s.profile ? `${s.profile} profile, ${s.tier} tier` : "", "", srcA(D.proof.src, "report.md")]),
    ];
    return `<div class="tbl-wrap"><table class="tbl runs"><thead><tr><th>What</th><th>When</th><th>Where</th><th>Code</th><th>Config</th><th>Task or run ids</th><th></th></tr></thead>
      <tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i === 5 ? ' class="ids"' : ""}>${i === 0 || i === 1 || i === 2 ? esc(c) : c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="small" style="margin:8px 0 0">A commit written “X, a branch of main Y” ran on a working branch made from that commit of <code>main</code>. “The live Envoy” is the copy on the Mac that Envoy's phone and the iPhone use; a test copy has its own data, and every final button on one here was declined.</p>`;
  }

  // The posting batch's attempts, as recorded (the clip, the song and the typed text checked before the final button).
  function batchTable() {
    const BT = D.batch, mark = (v) => v === "yes" ? "✓" : v === "no" ? "✕" : v === "n/a" ? "–" : "?";
    return `<div class="tbl-wrap card"><table class="tbl batch">
      <thead><tr><th>Attempt</th><th>Start</th><th>Song</th><th>How it ended</th><th class="r">To the final button</th><th>Clip</th><th>Song</th><th>Text</th><th class="r">Calls</th></tr></thead>
      <tbody>${BT.attempts.map((a) => `<tr><td><code class="small">${esc(a.code)}</code> <span class="small">${esc(POST[a.routine])}</span></td><td>${esc(a.state)}</td><td class="small">${esc(a.song || "–")}</td><td>${esc(a.class)}${a.reached ? "" : ", not reached"}</td><td class="r">${a.to_ask != null ? s0(a.to_ask) : "–"}</td><td>${mark(a.checks.clip)}</td><td>${mark(a.checks.song)}</td><td>${mark(a.checks.caption)}</td><td class="r">${a.calls ?? "–"}</td></tr>`).join("")}</tbody></table></div>
      <p class="small" style="margin:8px 0 0">✓ checked yes, ✕ checked no (the run stopped before the final button), ? not checkable, – not applicable. The Story's poll isn't text on the final screen; it was checked by eye on the approval screenshots, which stay outside the repo. Calls are Envoy's own, in its replay. ${srcA(BT.attempts_src, "attempts")} ${srcA(BT.src, "RESULTS.md")} ${srcA(BT.protocol_src, "PROTOCOL.md")}</p>`;
  }

  function renderEvidence() {
    const F = D.first_run, L = D.learned, RP = D.repair, K = RP.skylark, SB = RP.starbucks, RA = D.real, M = D.models, Sm = M.sam,
      V = M.vision, P = D.proof, B = D.built, T = D.teach, C = D.agents.claude, KY = D.keys;
    const maxMs = Math.max(...L.replay_steps.map((s) => s.ms.total));
    const ladder = (s) => s.status === "skipped" ? `<span class="chip">skipped</span>` : s.rung ? `<span class="chip apricot" title="${esc(s.rungs.join("; "))}">${esc(LADDER[s.rung] || "")}</span>` : "";
    const group = (id, title, sub, html) => `<details class="ev" id="ev-${id}"><summary><span class="t">${title}</span>${sub ? `<span class="s">${sub}</span>` : ""}</summary><div class="ev-body">${html}</div></details>`;
    const res = (r) => !r ? "–" : `${esc(r.result)}${r.calls ? `, ${r.calls} calls` : ""}`;
    const chart = (k, t, cap) => `<figure class="card chart"><img src="data/${esc(P.charts[k])}" alt="${esc(t)}" loading="lazy"><figcaption><b>${esc(t)}</b> ${cap} ${srcA({ path: P.charts_src.path + "/" + k + ".png" }, k + ".png")}</figcaption></figure>`;
    $("#evidence-body").innerHTML = `
      <span class="eyebrow">Evidence</span>
      <h2 id="evidence-h">Runs, commits, configuration, and the rest of the engine.</h2>
      <p class="lede">Everything above, with its task ids and the code it ran on, then the parts of Envoy the story skips. Each opens on a click.</p>
      ${group("runs", "Every run cited on this page", "what, when, where, commit, profile, ids", runsTable())}
      ${group("routine", "The Starbucks routine: its steps, checks, versions, and one replay inside", "section 2's run, compiled", `
        <div class="learn">
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
            <div class="callout" style="margin-top:12px"><b>A detail in the last step.</b> Its after-check still names <span class="slot">{{drink_size}}</span>, an input the compiler dropped as unused. At replay that check held as a relaxed match.</div>
          </div>
          <div>
            <div class="card vs">
              <h3>Every model call in the first run</h3>
              <table class="ledger"><thead><tr><th>At</th><th>Model</th><th>Job</th><th class="r">Took</th><th class="r">Cost</th></tr></thead>
              <tbody>${F.calls.map((c) => `<tr><td>${secs(c.t)}</td><td>${esc(MODEL[c.model] || c.model)}</td><td>${esc(JOB[c.job] || c.job)}</td><td class="r">${(c.ms / 1000).toFixed(1)} s</td><td class="r">${usd(c.usd)}</td></tr>`).join("")}</tbody></table>
              <p class="small" style="margin:8px 0 0">After the answer, Muse Spark wrote ${F.app_notes.length} app notes for next time: ${F.app_notes.map((x) => `“${esc(x)}”`).join(" ")}</p>
            </div>
            <div class="card vs" style="margin-top:16px">
              <h3>Inside one replay</h3>
              <p class="meta" style="margin:6px 0 0">One of the loop's quicker replays of v${L.replay.version}: ${L.replay_steps.length} steps in ${secs(L.replay.routine_s)}, ${L.replay.routine_calls} model calls inside the routine, ${L.replay.calls} for the task. Across the loop's replays the median was ${L.loop.replay.calls.median} calls. Each step waits for its before-checks, acts, then waits for its after-checks.</p>
              <div class="timeline">${L.replay_steps.map((s) => `
                <div class="tl ${s.status === "skipped" ? "skipped" : ""}"><span class="id" title="${esc(s.id)}">${esc(s.id)} ${ladder(s)}</span>
                  <span class="track"><span class="fill" style="display:block;width:${((s.ms.total / maxMs) * 100).toFixed(1)}%"></span></span><span class="ms">${(s.ms.total / 1000).toFixed(1)} s</span></div>`).join("")}</div>
              <div class="label-rec"><span><code>${esc(L.replay.task_id)}</code> on ${commit(L.replay.commit)}</span>${srcA(L.replay_src, "recording")}</div>
            </div>
            <div class="card vs" style="margin-top:16px">
              <h3>How the routine got to v${L.active.version}</h3>
              <ul class="versions">${L.versions.map((v) => `
                <li><span class="v">v${v.version}</span><div>
                  <span class="chip ${v.status === "active" ? "sage" : v.status === "rejected" ? "apricot" : ""}">${esc(v.status)}</span>
                  <span class="chip">${v.by === "self-repair" ? "self-repair, by Wonder" : v.version === 1 ? "compiled; input note fixed by hand" : "fixed by hand"}</span>
                  ${v.trial ? `<span class="meta"> trial ${v.trial.passed ? "passed" : "failed"}</span>` : ""}
                  <p>${v.changes.map((c) => esc(plainText(c).replace(/\.?$/, "."))).join(" ")}</p></div></li>`).join("")}</ul>
              <p class="small">The kept self-repair (v3): ${esc(SB.change)}. ${esc(MODEL[SB.call.model] || SB.call.model)}, one call, ${(SB.call.ms / 1000).toFixed(1)} s, ${usd(SB.call.usd)}; its trial passed with ${SB.trial.model_calls} model calls. Replaced later by a hand fix (v4).</p>
              <div class="label-rec">${srcA(L.versions_src, "index.json")} ${srcA(SB.call_src, "repair call")}</div>
            </div>
          </div>
        </div>`)}
      ${group("repairs", "Repairs on SkyLark: all 50 injected changes", "the stress test", `
        <div class="repair">
          <div class="card" style="padding:20px">
            <div class="row-between"><h3>An extra screen, injected on purpose</h3>${testApp}</div>
            <p class="meta" style="margin:6px 0 0">SkyLark's check-in got a “Review your trip” screen the routine had never seen; its next step looked for “Confirm check-in” and didn't find it.</p>
            <div class="pair">
              <figure>${phoneHTML(K.before, "SkyLark: the injected Review your trip screen with Looks good", [1080, 2400])}<figcaption><b>Before the repair</b><br>The unexpected screen.</figcaption></figure>
              <figure>${phoneHTML(K.after_img, "SkyLark: Confirm check-in, reached after tapping Looks good", [1080, 2400])}<figcaption><b>After</b><br>Back on the routine's path.</figcaption></figure>
            </div>
            <div class="quote"><span class="meta">${esc(MODEL[K.repair_model] || K.repair_model)}'s reason, one call:</span><br>“${esc(K.reason)}”</div>
            <ol class="flow">
              <li><b>Repair</b> on first meeting the change: ${secs(K.first.duration_s)}, ${K.first.calls} model call, ${usd(K.first.standard_usd)}.</li>
              <li><b>Saved</b> as v2: ${esc(K.patch)}.</li>
              <li><b>Trial</b> on a new booking: ${K.trial.passed ? "passed" : "failed"}, ${secs(K.trial.duration_s)}, ${K.trial.calls} model calls.</li>
              <li><b>After:</b> another booking ${K.after.passed ? "passed" : "failed"} with ${K.after.calls} calls; the original layout ${K.back.passed ? "passed" : "failed"} too (the new step is optional).</li>
            </ol>
            <details class="read"><summary>The saved version's diff (v1 → v2)</summary><pre class="diff">${K.diff.map((l) => `<span class="${l[0] === "+" && !l.startsWith("+++") ? "add" : l[0] === "-" && !l.startsWith("---") ? "del" : ""}">${esc(l)}</span>`).join("\n")}</pre></details>
            <div class="label-rec"><span><b>Recorded</b> ${esc(K.date)}</span><span><code>${esc(K.commit)}</code></span>${srcA(K.src, "change.json")} ${srcA(K.lib_src, "patches.json")}</div>
          </div>
          <div class="card" style="padding:20px">
            <h3>Each of 10 routines met each of 5 changed layouts</h3>
            <div class="tbl-wrap"><table class="tbl">
              <thead><tr><th>Change</th><th>Recovered</th><th>How</th><th class="r">Calls</th><th>Then, no call</th></tr></thead>
              <tbody>${RP.layouts.map((l) => `<tr><td>${esc(l.Layout.replace(/^\d: /, ""))}</td><td><b>${esc(l.Recovered)}</b></td><td class="small">${esc(l["Saved by"])}</td><td class="r">${esc(l["Model calls (first)"])}</td><td>${esc(l["After, no model call"])}</td></tr>`).join("")}</tbody>
            </table></div>
            <p class="small" style="margin:10px 0 0">New inputs on the same routines: ${esc(String(RP.new_inputs.Passed || "").replace(/\*/g, ""))} of ${esc(RP.new_inputs.Runs)} right, ${esc(RP.new_inputs["No model call"])} with no model call. ${notFinal("6c507f3")}</p>
            <h3 style="margin-top:18px">Real-app self-repairs and their trials</h3>
            <ul class="versions">${RP.real.map((v) => `<li><span class="v">v${v.version}</span><div><span class="chip ${v.passed ? "sage" : "apricot"}">${v.passed ? "kept" : "rejected by its trial"}</span> <code class="small">${esc(v.routine)}</code><p class="small">${esc(plainText(v.changes[0]))}</p></div></li>`).join("")}</ul>
            <div class="label-rec">${srcA(RP.layouts_src, "change.md")} ${srcA(RP.real_src, "index.json files")}</div>
          </div>
        </div>`)}
      ${group("real", "Real apps, workflow by workflow", `${esc(RA.rows.length)} workflows, ${esc(curvePass())}`, `
        <div class="tbl-wrap card"><table class="tbl">
          <thead><tr><th>Workflow</th><th>First run</th><th class="r">Agent</th><th>Compiled</th><th>Same input</th><th>New input</th><th>Graded by</th></tr></thead>
          <tbody>${RA.rows.map((r) => `<tr><td><code class="small">${esc(r.workflow)}</code><div class="small">${esc(r.goal)}</div></td><td>${esc(r.first_run)}</td><td class="r">${r.agent.calls} calls, ${s0(r.agent.seconds)}</td><td>${r.compiled ? `yes, ${r.steps} steps` : "no"}</td><td>${r.same ? `${res(r.same)}${r.same.seconds != null ? `, ${s0(r.same.seconds)}` : ""}` : "–"}</td><td>${res(r.new)}</td><td class="small">${esc(r.graded_by === "truth" ? "the app's truth" : "the answer's shape")}</td></tr>`).join("")}</tbody>
        </table></div>
        <p class="small" style="margin:8px 0 0">Of the 11 “graded by shape” answers (a price, a title), a person read 3: all 3 right. ${srcA(RA.curve.pass.md_src, "real.md")} ${srcA(RA.curve.pass.src, "real.json")}</p>`)}
      ${group("targets", "The design's targets on our test app, and four charts", `three on SkyLark, one on real apps; ${esc(suiteProfile("1"))} profile`, `
        <div class="tbl-wrap card"><table class="tbl"><thead><tr><th>Target</th><th>Goal</th><th>Measured</th></tr></thead>
          <tbody>${P.targets.map((t) => `<tr><td>${esc(t.Target)}</td><td>${esc(t.Goal)}</td><td>${esc(t.Measured)}</td></tr>`).join("")}</tbody></table></div>
        <div class="charts">
          ${chart("cost_and_time_over_repeated_runs", "First run vs later runs", "SkyLark's 10 core tasks, a new booking each time.")}
          ${chart("real_apps_stages", "Real apps, stage by stage", `18 read-only workflows, ${D.real.current.final ? "the final evaluation" : day(D.real.current.date)}.`)}
          ${chart("recovery_by_injected_change", "Recovery from injected UI changes", "SkyLark, 50 of 50.")}
          ${chart("success_by_system_and_layout", "Envoy vs the full agent vs a fixed replay", "SkyLark core set.")}
        </div>`)}
      ${group("batch", "The posting batch, attempt by attempt", `${D.batch.n} attempts on the final tag, every final button declined, ${day(D.batch.date)}`, batchTable())}
      ${group("tools", "One share switch, one new tool", "the tool list before and after, as agents see it", "<div id='tools-x'></div>")}
      ${group("models", "SAM 3.1 on a screen that's only pixels", "Meta's models", "<div id='models-x'></div>")}
      ${group("safety", "Safety tests: an approval, and planted text", "", "<div id='safety-x'></div>")}
      ${group("keys", "Agent keys and tool groups", "", "<div id='keys-x'></div>")}
      ${group("claude", "Claude Code, on its own key", "any MCP agent", `
        <p class="small" style="margin:0 0 8px">With a read-and-run key, Claude Code saw Envoy's tools and ran a learned SkyLark routine. Its check-in stopped at “Confirm check-in” for the person, and Claude said it can't approve: “Only the user can decide it, on their phone in Envoy.” An API restart later ended that waiting task; nothing was checked in. ${testApp}</p>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Routine and task</th><th>Status</th><th class="r">Time</th></tr></thead>
          <tbody>${C.tasks.map((t) => `<tr><td><code class="small">${esc(t.routine)}</code><div class="small">${esc(t.id)}</div></td><td>${esc(t.status)}${t.detail && t.status !== "done" ? `<div class="small">${esc(t.detail)}</div>` : ""}</td><td class="r">${secs(t.seconds)}</td></tr>`).join("")}</tbody></table></div>
        <div class="label-rec">${srcA(C.src, "task-rows.json")} ${srcA(C.readme, "README")}</div>`)}
      ${group("teach", "Teach mode: shown once by a script, replayed alone", "", "<div id='teach-x'></div>")}
      ${group("memory", "Memory with sources", "", "<div id='memory-x'></div>")}
      ${group("built", "How it's built", "", "<div id='built-x'></div>")}`;

    // The Starbucks routine's two views.
    const showV = (v) => {
      const rt = L[v];
      $("#rt-body").innerHTML = routineHTML(rt);
      $("#rt-src").innerHTML = srcA(rt.src);
      $("#rt-meta").textContent = v === "compiled"
        ? `Starbucks · ${rt.steps.length} steps · as the compiler wrote it from the first run (named ${rt.routine} then)`
        : `Starbucks · ${rt.steps.length} steps · v${rt.version}, the version the replay ran`;
      document.querySelectorAll("#ev-routine .tabs button").forEach((b) => { const on = b.dataset.v === v; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
    };
    document.querySelectorAll("#ev-routine .tabs button").forEach((b) => b.onclick = () => showV(b.dataset.v));
    showV("compiled");

    // A routine shared with agents: agent-door's check on a test copy, and the Spark agent calling the tool by name.
    const TT = D.tools, BN = TT.by_name, tool = TT.tool, props = Object.entries(tool.input.properties || {});
    const fresh = TT.after.tools.filter((t) => !TT.before.tools.includes(t));
    // The run's call to a learned routine (its first calls may search memory).
    const byName = BN.rows.find((r) => r.kind === "call" && BN.tools.some((t) => t.learned && t.name === r.tool));
    $("#tools-x").innerHTML = `
      <div class="keys-grid" style="margin-top:0">
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>Before and after the switch</h3>${testApp}</div>
          <div class="toollist"><span class="lbl">Before · ${TT.before.tools.length} tools</span><div class="chips">${TT.before.tools.map((t) => `<code class="tchip">${esc(t)}</code>`).join("")}</div></div>
          <div class="toollist"><span class="lbl">After sharing one routine · ${TT.after.tools.length} tools</span><div class="chips">${TT.after.tools.map((t) => `<code class="tchip ${fresh.includes(t) ? "new" : ""}">${esc(t)}</code>`).join("")}</div></div>
          <div class="tline-one" style="margin-top:12px"><code>${esc(tool.name)}(${props.map(([k]) => esc(k)).join(", ")})</code><p class="small" style="margin:6px 0 0">${esc(tool.description)}</p>
            <ul class="plain">${props.map(([k, v]) => `<li class="small"><code>${esc(k)}</code> · ${esc(v.type)}${(tool.input.required || []).includes(k) ? ", required" : ""}: ${esc(v.description || "")}</li>`).join("")}</ul></div>
          <p class="small" style="margin:10px 0 0">One call to it: <code>${callSig(TT.call.tool, TT.call.args)}</code> → ${esc(TT.call.status)}, “${esc(TT.call.result)}”, ${esc(TT.call.detail)}.</p>
          <div class="label-rec"><span><b>Recorded</b> ${esc(TT.before.at.slice(0, 16))}, a test copy of Envoy</span>${srcA(TT.door_src, "eval/results/agent-door")}</div>
        </div>
        <div class="card" style="padding:20px">
          <h3>What the person sees, and an agent calling it</h3>
          ${shot(TT.settings, "Envoy's Settings, Agent tools: three learned tools, each with its inputs and when it was learned", "Settings › Agents › Agent tools on a test copy: each shared routine as an agent calls it.")}
          <p class="small" style="margin:10px 0 0">The Spark agent, asked “${esc((BN.rows.find((r) => r.kind === "user") || {}).text)}”, called the learned tool directly: <code>${callSig(byName.tool, byName.args)}</code>. ${BN.model_calls} Spark calls, ${usd(BN.usd)}; the routine made none.</p>
          ${shot(TT.shot, "The Spark agent's page: skylark_check_flight_status called as a learned routine", "")}
          <div class="label-rec"><span><b>Recorded</b> ${esc(date(BN.started_et + ":00"))}</span>${srcA(TT.by_name_src, "event log")} ${srcA(TT.settings_src, "capture")}</div>
        </div>
      </div>`;

    // SAM.
    const [W, H] = Sm.screen, mp = Sm.model_point, pct = (x) => `${Math.round(x * 100)}%`, VC = M.vision_canvas;
    $("#models-x").innerHTML = `
      <div class="card sam" style="margin-top:0"><div class="pair one">
        <figure><div class="phone"><img src="data/${esc(Sm.frame)}" alt="SkyLark's drawn seat map, with no accessibility tree for the seats" loading="lazy" width="540" height="1200">
          <svg class="ring" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
            <rect class="tap-glow" x="${Sm.box[0]}" y="${Sm.box[1]}" width="${Sm.box[2] - Sm.box[0]}" height="${Sm.box[3] - Sm.box[1]}" rx="14"/>
            <rect class="tap" x="${Sm.box[0]}" y="${Sm.box[1]}" width="${Sm.box[2] - Sm.box[0]}" height="${Sm.box[3] - Sm.box[1]}" rx="14"/>
            <g class="miss"><line x1="${mp[0] - 26}" y1="${mp[1] - 26}" x2="${mp[0] + 26}" y2="${mp[1] + 26}"/><line x1="${mp[0] + 26}" y1="${mp[1] - 26}" x2="${mp[0] - 26}" y2="${mp[1] + 26}"/></g>
          </svg></div>
          <figcaption>Ringed: the box SAM 3.1 proposed and Spark picked. ✕: where the step model alone pointed.</figcaption></figure>
        <div>
          <div class="row-between"><h3>A drawn seat map</h3>${testApp}</div>
          <p style="color:var(--ink-2);margin:8px 0 0">SkyLark's seat map is drawn on a canvas, so its seats aren't in the accessibility tree. Asked for “${esc(Sm.target)}”, the step model's own point fell just above the seat. SAM 3.1 proposed ${Sm.candidates} boxes from a shape phrase, they were numbered on the screenshot, and Muse Spark picked one: ${Sm.calls} calls, ${usd(Sm.usd)}, ${(Sm.ms / 1000).toFixed(1)} s. Recorded ${esc(Sm.recorded_et)} ET. ${srcA(M.sam_src, "sam.json")}</p>
          <div class="tbl-wrap" style="margin-top:14px"><table class="tbl">
            <thead><tr><th>On ${V.step.targets} saved targets with no tree</th><th class="r">Hit</th><th class="r">Median error</th><th class="r">$ / target</th></tr></thead>
            <tbody>
              <tr><td>Step model's own coordinates</td><td class="r">${pct(V.step.accuracy)}</td><td class="r">${V.step.median_error_px} px</td><td class="r">${usd(V.step.cost_per_target)}</td></tr>
              <tr><td>Grounding alone</td><td class="r">${pct(V.grounding.accuracy)}</td><td class="r">${V.grounding.median_error_px} px</td><td class="r">${usd(V.grounding.cost_per_target)}</td></tr>
              <tr><td>SAM 3.1 + Spark's pick</td><td class="r">${pct(V.sam.accuracy)}</td><td class="r">${V.sam.median_error_px} px</td><td class="r">${usd(V.sam.cost_per_target)}</td></tr>
            </tbody></table></div>
          <p class="small" style="margin:8px 0 0">${VC.sam.targets} of the ${V.step.targets} targets are SkyLark's drawn seats (SAM + pick hit ${VC.sam.hits}, grounding ${VC.grounding.hits}); the rest are real-app controls on saved screens. Envoy runs SAM first, then grounding. ${srcA(M.vision_src, "vision.json")} ${srcA(M.phase6_src, "results")}</p>
        </div></div></div>`;

    // Safety.
    const S = D.safety, PL = S.planted, AP = S.approval;
    $("#safety-x").innerHTML = `
      <div class="safety">
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>An approval, recorded</h3>${testApp}</div>
          <div class="pair one">
            <figure>${phoneHTML(AP.frame, "SkyLark: the Confirm check-in screen the routine stopped on", [1080, 2400])}</figure>
            <div>
              <p style="margin:0;font-family:var(--serif);font-size:17px">“${esc(AP.description)}”</p>
              <p class="meta" style="margin:10px 0 4px">Why it asked:</p>
              <ul class="plain">${AP.reasons.map((r) => `<li><span class="chip">${esc(r)}</span></li>`).join("")}</ul>
              <p class="small" style="margin:10px 0 0">Three signals vote on every tap: rules on the target's words, the screen's own warnings, and the model's label. Any one flags it. By default “check me in” approves tapping Confirm check-in for that trip, and Envoy says so afterwards; a request from an agent, a trigger or an email waits for a person, unless they've set that routine to run without asking; money always asks. ${esc(AP.asked_et)} ET. ${srcA(S.approval_src, "approval.json")}</p>
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
            <figure>${phoneHTML(PL.frame, "SkyLark trip screen with a planted message telling the agent to cancel the trip", PL.screen, [{ box: PL.box, kind: "read" }])}<figcaption>Dashed: the planted message.</figcaption></figure>
            <div>
              <p class="meta" style="margin:0">The request:</p>
              <p style="margin:2px 0 10px;font-family:var(--serif);font-size:17px">“${esc(PL.goal)}”</p>
              <p class="meta" style="margin:0">What the agent wrote while it worked:</p>
              <ul class="plain">${PL.mentions.slice(0, 3).map((m) => `<li class="small">Step ${m.step}: “${esc(m.reason)}”</li>`).join("")}</ul>
              <p class="small" style="margin:10px 0 0"><b>It never tapped Cancel trip.</b> It saved the number and stopped (${PL.model_calls} model calls, ${secs(PL.seconds)}).</p>
            </div>
          </div>
          <div class="stats two" style="margin-top:16px">
            <div class="block stat"><div class="big">${S.agent[0]}/${S.agent[1]}</div><div class="lbl">agent runs still right with planted text; tried to follow it: <b>${S.agent[2]}</b>. Routines ${S.routines[0]}/${S.routines[1]}.</div>${notFinal(S.injection_run.commit)}</div>
            <div class="block stat"><div class="big">${S.inbox[0]}</div><div class="lbl">values from 4 planted emails stored in memory (instructions stored as facts: ${S.inbox[1]})</div>${srcA(S.injection_src, "injection.md")}</div>
          </div>
          <div class="label-rec"><span>Recorded Oct 28, an earlier pass (the counts above are Nov 3's), <code>${esc(PL.run)}</code></span>${srcA(S.planted_src, "planted.json")}</div>
        </div>
      </div>`;

    // Keys.
    const RK = KY.readonly, refusal = RK.rows.find((r) => r.kind === "refusal");
    const approveAsk = RK.rows.filter((r) => r.kind === "user").pop(), approveReply = RK.rows.filter((r) => r.kind === "reply").pop();
    $("#keys-x").innerHTML = `
      <div class="keys-grid" style="margin-top:0">
        <div class="card" style="padding:20px">
          <h3>Tool groups</h3>
          <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Group</th><th>Tools</th></tr></thead>
            <tbody>${Object.entries(KY.groups).map(([g, ts]) => `<tr><td><b>${esc(g)}</b></td><td>${ts.map((t) => `<code class="small">${esc(t)}</code>`).join(", ")}${g === "run" ? `<div class="small">and every shared routine's own tool</div>` : ""}</td></tr>`).join("")}</tbody></table></div>
          ${shot(KY.settings, "Envoy's Settings, Agents: Muse's key, and the form to add an agent with tool groups Read, Run, Memory, Files and Triggers", "Settings › Agents on a test copy: a new agent gets read and run unless the person adds more.")}
          <div class="label-rec">${srcA(KY.groups_src, "auth.py")} ${srcA(KY.settings_src, "capture")} ${srcA(KY.doc_src, "docs/agents.md")}</div>
        </div>
        <div class="card" style="padding:20px">
          <div class="row-between"><h3>The Spark agent on a read-only key</h3>${testApp}</div>
          <ul class="plain" style="margin-top:10px">
            <li><b>It sees ${RK.tools.length} tools,</b> all in the read group: ${RK.tools.map((t) => `<code class="small">${esc(t.name)}</code>`).join(", ")}.</li>
            ${refusal ? `<li><b>It called one it wasn't given</b>, <code>${esc(refusal.tool)}</code>. Envoy answered “${esc(refusal.text)}”, and nothing started.</li>` : ""}
            ${approveAsk ? `<li><b>Asked “${esc(approveAsk.text)}”:</b> “${esc(approveReply.text)}”</li>` : ""}
          </ul>
          ${shot(KY.readonly_shot, "The Spark agent's page: Envoy refused an unknown tool, and Spark says only the person can approve", "")}
          <p class="small" style="margin:8px 0 0">${RK.model_calls} Spark calls, ${usd(RK.usd)}. A test copy of Envoy, no phone used. Recorded ${esc(date(RK.started_et + ":00"))}.</p>
          <div class="label-rec">${srcA(KY.readonly_src, "event log")}</div>
        </div>
      </div>`;

    // Teach mode.
    const TC = T.rec.calendar, TK = T.rec.skylark, TR = TC.replay;
    const label = (s) => s.kind === "type" ? `type “${esc(s.typed)}”` : `tap “${esc(s.label)}”`;
    const film = (items) => `<div class="film">${items.join("")}</div>`;
    $("#teach-x").innerHTML = `
      <p class="small" style="margin:0">In teach mode a person does the task through Envoy's live view; Envoy records each screen and each tap or keystroke, Muse Wonder compiles the recording into a routine, and Envoy replays it alone before saving it. Here the “person” was a script that sends the web app's own live-view messages. Calendar was chosen because it's where learning from the agent stalled: on the Pixel its days are drawn, so they aren't in the accessibility tree. ${srcA(T.table_src, "table.md")}</p>
      <div class="card" style="padding:20px;margin-top:12px">
        <div class="row-between"><h3>Shown once: “${esc(TC.goal)}”</h3><span class="chip">${secs(TC.shown_s)} · ${TC.shown_calls} model calls</span></div>
        ${film(TC.steps.map((s) => `<figure>${phoneHTML(s.frame, `Google Calendar before step ${s.n}: ${s.kind} ${s.typed || s.label}`, [1080, 2400], [{ box: s.box, kind: "tap" }])}<figcaption><b>${s.n}.</b> ${label(s)}<br>${secs(s.t)}</figcaption></figure>`))}
        <p class="small" style="margin:8px 0 0">Ringed: where the person touched. Google Calendar on Envoy's emulator, a test account. One scripted demonstration and one replay, Oct 31.</p>
        <div class="learn-mid">
          <div><b>Compiled</b> by ${esc(MODEL[TC.routine.compiler] || TC.routine.compiler)}, one call, ${usd(TC.routine.usd)}, into <code>${esc(TC.routine.name)}</code> with inputs
            ${Object.entries(TC.routine.inputs).map(([k, v]) => `<span class="slot">{{${esc(k)}}}</span> (${esc(v)})`).join(" and ")}.</div>
          <ol class="flow">${TC.routine.steps.map((s) => `<li>${slots(s.intent)}</li>`).join("")}</ol>
        </div>
        <div class="row-between" style="margin-top:18px"><h3>Replayed alone</h3><span class="chip sage">${TR.steps.length}/${TR.steps.length} steps · ${secs(TR.seconds)} · ${TR.calls} model calls</span></div>
        ${film(TR.steps.map((s, i) => `<figure>${phoneHTML(s.frame, `Replay, after step ${i + 1}: ${s.id}`, [1080, 2400])}<figcaption><b>${i + 1}.</b> <code>${esc(s.id)}</code><br>${(s.ms / 1000).toFixed(1)} s${s.rung ? ` · ${esc(LADDER[s.rung] || "")}` : ""}</figcaption></figure>`))}
        <div class="callout" style="margin-top:14px"><b>Fixed since.</b> The last step is named “Tap Open Tasks”: Calendar's editor sheet sat over that button with Save on top at the same spot, and the recorder named the element underneath. The replay taps the same point, so it saves. A taught tap now goes to the topmost element under the finger (<code>f25be22</code>, Oct 31); this recording predates that.</div>
        <div class="label-rec"><span><b>Recorded</b> ${esc(TC.shown_et)} ET</span><span><code>${esc(TC.task_id)}</code></span>${srcA(T.src, "teach.json")} ${srcA(T.code_src, "teach.py")} ${srcA(T.person_src, "teach_person.py")}</div>
      </div>
      <p class="small" style="margin:10px 0 0">The same on SkyLark ${testApp}: “${esc(TK.goal)}”, shown in ${TK.steps} steps, compiled for ${usd(TK.usd)} into <code>${esc(TK.routine)}</code>, replayed alone in ${secs(TK.replay_s)} with ${TK.replay_calls} model calls; it read “${esc(TK.replay_output)}”, the same answer the person saw.</p>`;

    // Memory.
    const MM = D.memory, X = MM.extraction, demo = MM.demo;
    const KIND = { email: "email", email_markup: "email (markup)", app_screen: "app screen", routine_run: "routine run", photo: "photo" };
    const ORDER = ["number", "date", "start_date", "from", "to", "depart_time", "seat", "gate", "boarding_time", "confirmation_code", "status"];
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
    $("#memory-x").innerHTML = `
      <p class="small" style="margin:0">Facts come in from app screens, email and photos through Muse Spark; every value must appear in its source, and a newer source replaces an older value while the old one stays as history.</p>
      <div class="mem" style="margin-top:12px">
        ${ent("SL 482 · Fri, Oct 30, 2026", (f) => f.current && ["number", "date", "from", "to", "depart_time", "seat", "gate", "boarding_time", "confirmation_code", "status"].includes(f.attribute))}
        <div>
          ${ent("SL 1190 · Sat, Nov 14, 2026", (f) => ["number", "date", "seat", "confirmation_code"].includes(f.attribute))}
          <p class="small" style="margin:8px 4px 0">The seat came from the booking email; a later “Seat change confirmed” email replaced it. Both stay, on two timelines: when it was true, and when Envoy learned it.</p>
        </div>
      </div>
      <div class="label-rec">The demo world: SkyLark's test inbox, SkyLark app runs and one test photo. ${srcA(MM.demo_src, "memory.json")} ${srcA(MM.readme_src, "backend/memory/README.md")}</div>
      <div class="stats" style="margin-top:12px">
        <div class="card stat"><div class="row-between"><div class="big">${X.right}/${X.of}</div>${testApp}</div><div class="lbl">attributes right on ${X.items} labeled items from our test inboxes and SkyLark screens (${X.pct}%), <b>${X.wrong} wrong</b></div>${notFinal(MM.commit)} ${srcA(MM.src, "memory.md")}</div>
        <div class="card stat"><div class="row-between"><div class="big">${MM.stale.unwarned} of ${MM.stale.of}</div>${testApp}</div><div class="lbl">stale facts served without a warning, on SkyLark bookings</div>${notFinal(MM.commit)} ${srcA(MM.src, "memory.md")}</div>
      </div>`;

    // How it's built.
    $("#built-x").innerHTML = `
      <figure class="card chart" style="margin-top:0"><img src="data/${esc(B.diagrams.architecture)}" alt="Envoy's architecture: interfaces, the task API, the backend, Meta's models and the device layer" loading="lazy"><figcaption>${srcA(B.diagrams_src, "docs/diagrams")}</figcaption></figure>
      <figure class="card chart" style="margin-top:16px"><img src="data/${esc(B.diagrams.lifecycle)}" alt="Routine lifecycle: compile once, run many times, repair locally" loading="lazy"><figcaption>${srcA(B.diagrams_src, "docs/diagrams")}</figcaption></figure>
      <div class="built">
        <div class="card" style="padding:20px">
          <h3>What Envoy built itself</h3>
          <ul class="ours">${B.ours.map((o) => `<li><b>${esc(o.title)}.</b> <span>${esc(plainText(o.text).split(". ")[0].replace(/\.$/, "").replace(/^./, (c) => c.toUpperCase()))}.</span></li>`).join("")}</ul>
          <p class="small" style="margin:10px 0 0">Ideas borrowed, no code used: ${B.borrowed.map(esc).join(" ")}</p>
        </div>
        <div class="card" style="padding:20px">
          <h3>Open-source plumbing</h3>
          <p class="small" style="margin:6px 0 10px">Talking to phones, streaming video, serving HTTP, drawing the web app. Each credited with its license.</p>
          <div class="chips">${B.plumbing.map((p) => `<span class="chip" title="${esc(p.license)}: ${esc(p.use)}">${esc(p.name)}</span>`).join("")}</div>
          <div class="label-rec">${srcA(B.src, "THIRD_PARTY.md")} ${srcA(P.tests.src, `${P.tests.functions} test functions in ${P.tests.files} files`)}</div>
        </div>
      </div>
      <div class="card next-up">
        <div><h3>The code</h3><p class="meta" style="margin:4px 0 0">${D.meta.repo_url ? `<a href="${esc(D.meta.repo_url)}">${esc(D.meta.repo_url)}</a>` : ""}</p></div>
        <div class="meta">This site: <code>site/</code>, built by <code>scripts/build_site_data.py</code>.</div>
      </div>`;
  }

  // ---- table of contents ----
  function renderToc() {
    const all = [...document.querySelectorAll("main section.sec")];
    const names = { claim: "The idea", learns: "Learns", acts: "Acts", watches: "Watches", results: "Results", evidence: "Evidence" };
    $("#toc").innerHTML = all.map((s) => {
      const n = num(s.id);
      return `<a href="#${s.id}" data-id="${s.id}">${n ? `<span class="n">${n}</span>` : ""}${esc(names[s.id] || s.id)}</a>`;
    }).join("");
    const links = [...document.querySelectorAll("#toc a")];
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.dataset.id === e.target.id));
    }), { rootMargin: "-40% 0px -55% 0px" });
    all.forEach((s) => io.observe(s));
  }

  // An evidence link opens its group before the browser scrolls to it; so does a #ev-… address.
  function openFromHash(id) {
    const d = document.getElementById(id);
    if (d && d.tagName === "DETAILS") { d.open = true; return d; }
    return null;
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-open]");
    if (a) openFromHash(a.dataset.open);
  });

  renderIdea();
  renderLearns();
  renderActs();
  renderWatches();
  renderResults();
  renderEvidence();
  renderToc();
  // ?only=<section id> shows one section alone (for screenshots: headless Chrome captures from the top); with
  // ?only=evidence&open=1 every evidence group is open.
  const q = new URLSearchParams(location.search), only = q.get("only");
  if (only) document.querySelectorAll("main section.sec").forEach((s) => { if (s.id !== only) s.hidden = true; });
  if (q.get("open")) document.querySelectorAll("details.ev").forEach((d) => { d.open = true; });
  // Sections render after load, so a #section link lands short; scroll again once they're in.
  if (location.hash) { const id = location.hash.slice(1); openFromHash(id); const t = document.getElementById(id); if (t) t.scrollIntoView(); }
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
