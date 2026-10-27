# Phase 2: App routines (the core innovation)

You are continuing **Envoy**, my solo project for the Meta Global AI Developer Hackathon. It runs Oct 26 – Nov 4, 2026 (indie track, problem statement "Push the Frontier"); submissions are due **Nov 4, 9:00 PM ET**. Envoy is a Muse-powered agent that operates Android apps on emulated phones, compiles successful runs into reusable **app routines**, and keeps a shared memory graph across web, voice, iPhone and MCP clients.

Phases 0 and 1 are done, and their gates passed. This phase builds app routines, the part of Envoy that is genuinely new. Take your time and do your best work. You have full permission to do whatever this needs on this Mac (installs, emulators, commits, pushes to the private repo), with two exceptions:
- Never type passwords or sign in to accounts. Sign-ins are mine.
- Never use my payment methods.

## Read first (in this order)

1. `docs/technical-design.md`, especially **App routines** (the whole section), Agent runtime, Device layer, Safety, and Build phases. The live version is https://claude.ai/artifact/Sf51zMf4SMi5ZZmJabgPR5; if the two disagree, the live one wins. Both were updated on Oct 27 with Phase 0 and 1 results.
2. `docs/phase-1-results.md`: what was built and what the evaluation found.
3. `docs/phase-0-findings.md`: measurements, real-app findings (B1), the Muse connector (B2), the rules (B3).
4. `backend/agent/README.md`, `backend/policy/README.md`, `testapps/README.md`.
5. One real trace: run `python3 scripts/show_trace.py` to list runs, then `python3 scripts/show_trace.py p1-final-code-check-checkin-v0-r0 --screens`.

## Where things stand (Oct 27)

**Environment**
- MacBook Pro M5 Pro, 24 GB. `source scripts/env.sh`; it's already in `~/.zshrc`.
- Python 3.13 via uv: `uv run --project backend …`.
- Emulators:
  - `envoy-test` (snapshots allowed; gRPC on 8554): start with `scripts/start_emulator.sh envoy-test`, stop with `scripts/stop_emulator.sh`.
  - `envoy-real` (never snapshot-restored; always stopped cleanly): has Target, Starbucks, Chipotle, Amazon and DoorDash. DoorDash is signed in through my test Google account. Chrome 156 and WebView 155 are updated.
- Repo: `~/Desktop/Envoy`, pushed to the **private** GitHub repo `sanjeevexe/envoy`. It must be public by Nov 4; it's MIT-licensed.
- Meta API: a **shared key** in `.env` (`META_API_KEY`), about **$36.9 left**. Every call is logged to `logs/model_costs.jsonl`. The daily cap is in `.env`.
- The memory notes in `~/.claude/projects/-Users-sanjeevvarma-Desktop-Envoy/memory/` carry durable preferences.

**What exists**
- `backend/devices/`: the `Device` protocol and `EmulatorDevice`.
  - Tree read about 31 ms; full observe about 80 ms.
  - Taps through gRPC (under 1 ms); typing through accessibility set-text (waits for focus).
  - Snapshot save and load with reconnect (about 1.8 s). Detection of `FLAG_SECURE` windows.
  - The compact screen format and the screen signature: app, activity, sorted (resource ID, type) outside lists, ignoring text.
- `backend/agent/`: `AgentRunner`.
  - The loop: plan → observe → decide (Muse Spark 1.3, `low`, json_schema) → policy → act → verify → record.
  - Also: pop-up handler, sign-in hand-off, stuck detection and cycle replanning, success checks in code.
  - Traces in `data/runs/<task_id>/`: `steps.jsonl` has, per step, the decision (`reason`, `action`, `expected_result`, `risk`), the target element with parent and sibling text, and before and after screens. `screens/NNN_before|after.json.gz` hold the full trees.
- `backend/policy/`: risk classifier (rules + screen context + model label), approvers (terminal and scripted), sign-in detection.
- `backend/models/`: the adapter (cost meter, retries, recovery from preamble-before-JSON), schemas, prompts.
- `testapps/skylark/` and `backend/testapps/skylark.py`: SkyLark Air, our test airline app.
  - `prepare(fixtures, variant)`, `state()`, `seed()`, `set_variant()`, `set_gate()`.
  - **Layout variants:** 0 original, 1 moved button, 2 renamed labels, 3 extra confirmation screen. **They exist to test routine repair.**
- `eval/`: the 13-task SkyLark set and runner (`eval/run_skylark.py`). Phase 1: 69/69 runs passed. About 0.85 s and $0.0015 per agent step; a median task is 2–3 actions in about 9 s.
- `backend/tests/`: 23 offline tests (`cd backend && uv run pytest -q tests`).

**Facts that shape routines** (measured; don't re-derive them)
- Real apps often obfuscate resource IDs (the Play Store's are all `0_resource_name_obfuscated`; Starbucks' activity is `dIu`). Locators must lean on text, description, class and neighbors, not IDs alone. The screen signature should not depend only on IDs.
- The XML tree garbles emoji (`..`). Field checks must read values with `get_text`.
- The tree can lag the pixels during transitions (DoorDash), and content can load after the screen "settles" (Target). Before-checks need a wait with timeout.
- Approval links and anything else reachable by GET must never act on a page load (link previews fetch them).
- Settle detection (250 ms of unchanged tree) costs 0.35–0.45 s per step and is the main speed cost on reruns.

## The job: Phase 2

Build exactly what the design doc's **App routines** section describes. In short:

1. **Routine format:** YAML/JSON as in the design doc. It has:
   - name, app, version, intent
   - typed inputs (text, code, date, phone, choice) with `from_memory` hints
   - outputs
   - steps, each with an intent, before-checks, an action with a **multi-attribute locator**, after-checks, a risk level and optional `extract`
   - `scroll_until(locator, direction, max_scrolls)` for lists
2. **Compiler** (`backend/routines/compiler.py`): trace → routine.
   1. Only compile runs that reached the goal: status `done` with a passed check, or user-confirmed.
   2. **Clean up:** drop dead ends, back-tracks, retries, no-change steps and pop-up dismissals (the shared handler covers those).
   3. **Generalize:** a typed or chosen value that equals a task input or a memory note becomes an input slot. A list item chosen because it matched an input becomes an input-based locator. Use **Muse Wonder** to name inputs and decide what stays fixed; it was accessible on the key in Phase 0. If it's unavailable, use Spark at high effort.
   4. **Add checks automatically** by diffing each step's before and after trees: what must be present before, and what must change after (a new screen signature, a toggle on, a field value, a visible text).
   5. **Verify by replay** from a reset snapshot with the same inputs, and with a second set of inputs where SkyLark allows. Only routines that pass go into the library.
3. **Locators** (`backend/routines/locators.py`): score candidates on resource ID, text, description, class, parent and sibling text, and position-in-list hints, with a **strict** and a **relaxed** threshold. Tune both on SkyLark across the four variants. Element-based, never coordinates. For elements with no usable attributes, store a visual crop as a fallback (it may stay a stub this phase).
4. **Executor** (`backend/routines/executor.py`): for each step, wait for the before-checks (up to 5 s), locate, act through the same **policy gate** (irreversible steps always ask for approval, even in routines), then wait for the after-checks. **No model calls while checks pass.** Extract outputs (seat, gate…) and return them.
5. **Fallback ladder,** one rung at a time:
   1. wait and retry
   2. relaxed matching
   3. the known pop-up handler
   4. **local repair**: one model call with the step's intent, checks and current screen, proposing actions that satisfy the after-check; capped at 2 per step and 5 per run
   5. hand the rest of the task to the full agent from the current screen
   6. ask the user
6. **Patching and versions** (`backend/routines/store.py`):
   - A successful repair becomes a **candidate patch** (a new locator, an inserted step such as variant 3's extra screen, or a removed step), saved as a new version marked "on trial".
   - Replay it right away from a reset snapshot on SkyLark. It becomes active if it passes; otherwise roll back.
   - If a routine fails more than half its recent runs, recompile it.
   - Keep the history with before and after screenshots.
7. **Matching** a request to a routine: app, then intent pattern, then description similarity, then a final model confirmation that also fills inputs from the request and notes. A simple version is enough this phase.

**Phase 2 gate (from the design doc):** a routine works on a **new booking** (new inputs), and **recovers from an injected UI change** (SkyLark variants 1–3).

### How I want you to approach it (recommended plan)

1. **Start from traces you already have.** Compile `checkin`, `change_seat`, `ktn` and `gate` from Phase 1 traces before writing anything general. Hand-check the output against the design doc's YAML example, then generalize the compiler.
2. **Make SkyLark support "new inputs"** so the gate is honest. Seed a second upcoming booking with check-in open, different code, flight, seat and gate, through fixtures. Make sure routines take the trip as an input rather than "the first card". Add tasks such as "check in for my Denver flight" and "change my seat on <trip> to <seat>".
3. **Build the executor and the ladder before the patcher,** and measure plain replays on variant 0 first: the target is no model calls, and well under 30 s per run for a 10-step task (the design's success target). If settle time dominates, consider settling on the after-check itself instead of the generic 250 ms quiet window. That's a natural win for routines.
4. **Then injected changes:** run each compiled routine on variants 1, 2 and 3. Record which ladder rung saved it, the patches created, and whether the patched version then succeeds on its own with no model calls. Extend `eval/` with a routines suite and report:
   - routine success on new inputs
   - recovery rate per kind of change
   - model calls and time per run against the full agent (the design's "80% fewer model calls" target)
   - cost per run
   - whether the patched version succeeds on its own
5. **Add the three systems comparison from the design's Evaluation section, if time allows:** full agent every time; a fixed replay that taps recorded coordinates with a screen-similarity check (like Mobilerun macros); Envoy routines. Even a small table makes the innovation measurable.
6. **Real-app checkpoint, my added recommendation, at the end of this phase.** Phase 1's 100% is on an app we built.
   - On `envoy-real`, run 3–4 **read-only** workflows once with the agent. Suggestions:
     - a Target store's hours or a product price (guest; the store is already set to Chelsea, NYC)
     - a Chipotle menu item's price (guest)
     - an Amazon search and the top result's price (guest)
     - my DoorDash order history or a saved address (signed in through Google)
   - Compile each into a routine, rerun it, and record what breaks: locators on obfuscated IDs, WebView content, late-loading content, pop-ups.
   - **Nothing irreversible:** no orders, carts that check out, or sign-ins. Stop at any approval.
   - Fix what's general; write down what's not.
7. **Keep the honest record.** Use `docs/phase-2-results.md` in the style of `docs/phase-1-results.md`: what was built, tables, what the evaluation found and changed, honest limits. Also:
   - Add findings to `docs/meta-feedback.md`.
   - Update both copies of the design doc with a short "Phase 2 results" section. Use the Claude Docs connector for the live one: find-and-replace edits, check `sinceRev` first, never overwrite someone else's edit.
   - Commit after each meaningful step and push.

## Rules and constraints

- **The demo may only show work built during the hackathon (Oct 27 – Nov 4), clearly identified**, or the project can be disqualified. Keep `THIRD_PARTY.md` current. Open source is plumbing; routines, repair and versioning are ours. Don't adopt an existing routine or macro library wholesale.
- **Budget:** the whole phase should cost a few dollars at most. Use `low` effort for steps and repairs where it works, and Wonder only for compiling. Don't use the Contributor tier on this shared key unless I say so.
- **Safety is unchanged in routines:** irreversible steps always go through the policy gate, approvals come only from a person (or the scripted approver on SkyLark), and nothing types passwords.
- Keep `envoy-real` long-lived: never restore a snapshot on it, and always stop it with `scripts/stop_emulator.sh`. Run at most two emulators at once; Chrome stays open on this Mac.
- Before any change visible outside this Mac (making the repo public, submitting forms, posting), ask me.

## Done means

- The Phase 2 gate passes on SkyLark: a routine works on a new booking and recovers from injected UI changes (variants 1–3). There are measurements against the full agent, and patched versions are saved and verified.
- The real-app checkpoint is done and written up.
- Docs, tests and eval reports are committed and pushed.
- Finish with a short summary:
  1. what was built
  2. the key numbers (success, recovery per change, model calls and time against the full agent, cost)
  3. anything that changes the design
  4. what I need to do next
