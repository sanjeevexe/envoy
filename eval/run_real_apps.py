"""The real-app test set on envoy-real: read-only workflows across apps, each learned once by the agent,
compiled into a routine, rerun, and graded automatically.

  uv run --project backend python eval/run_real_apps.py                         # agent runs only where no trace exists yet
  uv run --project backend python eval/run_real_apps.py --only gmail_newest,maps_address --rerun-agent
  uv run --project backend python eval/run_real_apps.py --regression            # after a routines change: no agent, cached
                                                                                # compile answers, so 0 model calls unless a repair runs
  uv run --project backend python eval/run_real_apps.py --report                # rebuild report.md from suite.json

Every workflow is scored at the four places learning can break (eval/results/real_apps/report.md):
  1. first run   the agent, from a fresh launch, gives a right answer
  2. compile     its trace becomes a routine (only verified runs compile)
  3. same input  the routine reruns with no model call and gives a right answer (repair allowed only if that fails)
  4. new input   the same with a second input (a different search term, drink, place)
"Right" is checked against ground truth where there is one (the phone's settings over adb, the Gmail API, published
facts such as an address or a year) and against the answer's shape otherwise (a price, a rating). An output that is
just the input echoed back is never right. Bot checks are recorded as such: Envoy hands them to a person.

envoy-real is never restored to a snapshot; "reset" is force-stopping and relaunching the app. Standard tier only.
Safety: every approval is declined by the script (nothing irreversible may run), sign-in screens stop the run
(hand-off), nothing is typed into a password field, and outputs holding personal data are redacted in results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agent.loop import AgentRunner, RunConfig
from agent.trace import RUNS
from devices.emulator import EmulatorDevice
from devices.types import ScreenState
from models.adapter import ModelAdapter
from models.schemas import CompiledRoutine
from policy.approvals import ScriptedApprover
from policy.botcheck import bot_check_reason
from routines.compiler import NotCompilable, compile_trace
from routines.executor import ExecConfig, RoutineExecutor
from routines.model import dump_yaml
from routines.screens import norm

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "real_apps"
PRIVATE_DIR = REPO / "data" / "real_routines"  # routines over personal data stay out of the repo
SPEC_DIR = OUT / "compiled"  # routines and Wonder's cached answers (the final evaluation keeps its own)
TASK_PREFIX = "p2-real"  # agent traces are data/runs/<prefix>-<workflow> (the Phase 2 checkpoint's are reused here)
SERIAL = "emulator-5556"

NO_ACCOUNT = "Don't sign in, create an account or turn on sync; if asked, choose to continue without an account. Don't install anything."
PRICE = r"\$\s?\d+(\.\d{2})?"


@dataclass
class Workflow:
    id: str
    app: str
    category: str
    goal: str
    expect: str = r"\w"  # regex (case-insensitive) a right answer matches, for the first input
    second: dict[str, str] = field(default_factory=dict)  # example value → second value (e.g. a search term)
    expect_second: str | None = None  # for the second input (default: `expect`)
    truth: Callable[[], tuple[str, str | None]] | None = None  # (expect, expect_second) computed at run time: adb, Gmail API
    memory: str = ""
    private: bool = False  # outputs hold personal data: redact before writing results
    graded_by: str = "shape"  # "truth" when `expect` is ground truth rather than the answer's shape


def adb(*args: str) -> str:
    return subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=30).stdout.strip()


async def chrome_blank(app: str) -> None:
    """Chrome reopens its last tab on a fresh launch, so a run after a run starts on the article the last one found (Nov 2:
    the first run started on the Eiffel Tower article and never typed the topic). A blank page first, as run_loop.py does."""
    if app == "com.android.chrome":
        adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "about:blank", "-p", app)
        await asyncio.sleep(2.0)


def _android_version() -> tuple[str, None]:
    return rf"\b{re.escape(adb('shell', 'getprop', 'ro.build.version.release'))}\b", None


def _bluetooth() -> tuple[str, None]:
    on = adb("shell", "settings", "get", "global", "bluetooth_on") == "1"
    return (r"^(?!.*\boff\b).*\b(on|enabled)\b" if on else r"^(?!.*\b(on|enabled)\b).*\b(off|disabled)\b"), None


def _gmail(query: str | None, second: str | None = None) -> Callable[[], tuple[str, str | None]]:
    """The subject of the newest message (for a search: the newest matching one), from the Gmail API. "My inbox" is either
    the Primary tab, where the Gmail app opens, or the whole inbox: on Oct 31 a Promotions mail was newer than Primary's top
    message, which the agent read, and only the whole inbox's counted."""
    def newest() -> str:
        primary, inbox = subject("in:inbox category:primary"), subject("in:inbox")
        return primary if primary == inbox else f"(?:{primary})|(?:{inbox})"

    def subject(q: str | None) -> str:
        from integrations.mail import gmail_service
        users = gmail_service().users()
        msgs = users.messages().list(userId="me", q=q or "", maxResults=1).execute().get("messages", [])
        if not msgs:
            return r"\b(no|none|nothing)\b"
        head = users.messages().get(userId="me", id=msgs[0]["id"], format="metadata", metadataHeaders=["Subject"]).execute()
        s = next((h["value"] for h in head["payload"]["headers"] if h["name"].lower() == "subject"), "")
        words = re.findall(r"[A-Za-z0-9']{3,}", s)[:4]  # the first few words, so emoji and punctuation don't matter
        # An empty pattern would match any answer: a mail with no subject is "(no subject)" in the app.
        return r".*".join(re.escape(w) for w in words) or (re.escape(s) if s.strip() else r"no subject")
    return lambda: (subject(query) if query else newest(), subject(second) if second else None)


WORKFLOWS = [
    # Shopping and food (from the Phase 2 checkpoint)
    Workflow("amazon", "com.amazon.mShop.android.shopping", "shopping",
             "In the Amazon app, search for AA batteries and tell me the price of the first result.",
             expect=PRICE, second={"AA batteries": "USB-C cable"}),
    Workflow("target", "com.target.ui", "shopping", "In the Target app, what are today's hours for my Target store?",
             expect=r"\d{1,2}(:\d\d)?\s*(am|pm)"),
    Workflow("target_search", "com.target.ui", "shopping",
             "In the Target app, search for paper towels and tell me the price of the first result.",
             expect=PRICE, second={"paper towels": "AA batteries"}),
    Workflow("starbucks", "com.starbucks.mobilecard", "food", "In the Starbucks app, how many calories are in a Grande Caffè Latte?",
             expect=r"\b190\b", second={"Caffè Latte": "Caramel Macchiato", "Caffe Latte": "Caramel Macchiato"},
             expect_second=r"\b250\b", graded_by="truth"),
    Workflow("chipotle", "com.chipotle.ordering", "food", "In the Chipotle app, find the price of Chips & Guacamole.",
             expect=PRICE, memory="Preferred Chipotle location: near zip code 10001 (Chelsea, New York)",
             second={"Chips & Guacamole": "Chips & Queso Blanco"}),
    Workflow("doordash", "com.dd.doordash", "food", "In the DoorDash app, what is my saved delivery address?",
             expect=r"Hacker Way", private=True, graded_by="truth"),
    Workflow("doordash_search", "com.dd.doordash", "food",
             "In the DoorDash app, search for pizza and tell me the name of the first restaurant in the results.",
             second={"pizza": "sushi"}),
    # Google's apps on the phone: ground truth from adb, the Gmail API or published facts
    Workflow("settings_version", "com.android.settings", "system", "In the Settings app, what Android version is this phone running?",
             truth=_android_version, graded_by="truth"),
    Workflow("settings_bluetooth", "com.android.settings", "system", "In the Settings app, is Bluetooth turned on or off?",
             truth=_bluetooth, graded_by="truth"),
    Workflow("gmail_newest", "com.google.android.gm", "google", "In the Gmail app, what is the subject of the newest email in my inbox?",
             truth=_gmail(None), private=True, graded_by="truth", memory=NO_ACCOUNT),  # the newest mail can be a sign-in code
    Workflow("gmail_search", "com.google.android.gm", "google",
             "In the Gmail app, search my mail for DoorDash and tell me the subject of the first result.",
             second={"DoorDash": "Security alert"}, truth=_gmail("DoorDash", "Security alert"), graded_by="truth", memory=NO_ACCOUNT),
    Workflow("calendar_today", "com.google.android.calendar", "google", "In Google Calendar, do I have any events today?",
             expect=r"\b(no|none|nothing|not any|don't|do not)\b", graded_by="truth", memory=NO_ACCOUNT),
    Workflow("contacts_count", "com.google.android.contacts", "google", "In the Contacts app, how many contacts do I have?",
             expect=r"\b(no|none|zero|0)\b", graded_by="truth", memory=NO_ACCOUNT),
    Workflow("maps_address", "com.google.android.apps.maps", "maps",
             "In Google Maps, search for the Empire State Building and tell me its street address.",
             expect=r"350\s+(5th|fifth)\s+ave|20\s+w(est)?\.?\s+34th", second={"Empire State Building": "Space Needle"}, expect_second=r"400\s+broad\s+st",
             graded_by="truth", memory=NO_ACCOUNT),
    Workflow("play_rating", "com.android.vending", "store",
             "In the Google Play Store app, what is the star rating of the Duolingo app?",
             expect=r"\b[1-5]\.\d\b", second={"Duolingo": "Spotify"}, memory=NO_ACCOUNT),
    Workflow("youtube_search", "com.google.android.youtube", "media",
             "In the YouTube app, search for lofi hip hop and tell me the title of the first video in the results.",
             second={"lofi hip hop": "pasta carbonara recipe"}, memory=NO_ACCOUNT),
    Workflow("ytmusic_artist", "com.google.android.apps.youtube.music", "media",
             "In the YouTube Music app, search for the song Bohemian Rhapsody and tell me the artist of the first song result.",
             expect=r"^\W*queen\W*$", second={"Bohemian Rhapsody": "Shape of You"}, expect_second=r"^\W*ed sheeran\W*$",
             graded_by="truth", memory=NO_ACCOUNT),
    Workflow("chrome_wikipedia", "com.android.chrome", "web",
             "In Chrome, go to en.m.wikipedia.org, search for Eiffel Tower and tell me the year it opened.",
             expect=r"\b1889\b", second={"Eiffel Tower": "Statue of Liberty"}, expect_second=r"\b1886\b", graded_by="truth",
             memory=NO_ACCOUNT),
]

def bot_check(screen: ScreenState | None) -> bool:
    """A bot check on screen (policy/botcheck.py, which the task runner uses too)."""
    return bot_check_reason(screen) is not None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(wf: Workflow, value: object) -> object:
    if not wf.private:
        return value
    if isinstance(value, dict):
        return {k: "[redacted]" if v else v for k, v in value.items()}
    if isinstance(value, str) and value:
        return "[redacted]"
    return value


def right(text: str | None, pattern: str | None, inputs: dict[str, str], truth: bool = False) -> bool:
    """The answer matches its pattern and, unless the pattern is ground truth, is not just an input echoed back
    (a subject can be the search term itself: "Security alert")."""
    if not text or not pattern:
        return False
    if not truth and any(v and norm(text) == norm(v) for v in inputs.values()):
        return False
    return re.search(pattern, " ".join(text.split()), re.I) is not None


def in_sentence(pattern: str) -> str:
    """A pattern written for a routine's bare output ("^\\W*queen\\W*$") as it appears inside the agent's sentence
    ("... is by Queen - Bohemian Rhapsody · Queen • 5:55")."""
    core = re.sub(r"\\W\*\$$", "", re.sub(r"^\^\\W\*", "", pattern))
    return rf"\b(?:{core})\b" if core != pattern else pattern


def agent_row(task_id: str) -> dict | None:
    p = RUNS / task_id / "run.json"
    if not p.exists():
        return None
    r = json.loads(p.read_text())
    return {k: r.get(k) for k in ("status", "result", "steps", "model_calls", "cost_at_standard_usd", "duration_s", "popups", "check")}


def scrub(row: dict, secrets: list[str]) -> dict:
    """A private workflow's row with every word of its answers (3+ characters) replaced wherever a check, compile note or step
    detail quotes them, and its ground truth hidden: on Oct 31 Gmail's newest subject was a sign-in code, and both the answer
    check's detail and the expected pattern repeated it."""
    words = {w for s in secrets if isinstance(s, str) for w in re.findall(r"[A-Za-z0-9']{3,}", s)}
    pat = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r")(?![A-Za-z0-9])") \
        if words else None

    def walk(v: object) -> object:
        if isinstance(v, str):
            return pat.sub("[redacted]", v) if pat else v
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    out = {k: walk(v) if k in ("agent", "compile", "routine_runs", "error") else v for k, v in row.items()}
    for k in ("expect", "expect_second"):
        if out.get(k):
            out[k] = "[redacted]"
    return out


def step_rows(outcome) -> list[dict]:
    return [{"id": s.id, "status": s.status, "rung": s.rung, "rungs": s.rungs, "score": s.score, "detail": s.detail[:200],
             "ms": round(s.wait_ms + s.act_ms + s.post_ms)} for s in outcome.steps]


async def run_one(wf: Workflow, args, device: EmulatorDevice, adapter: ModelAdapter, approver) -> dict:
    row = await _run_one(wf, args, device, adapter, approver)
    secrets = row.pop("_secrets", [])
    return scrub(row, secrets) if wf.private else row


async def _run_one(wf: Workflow, args, device: EmulatorDevice, adapter: ModelAdapter, approver) -> dict:
    task_id = f"{TASK_PREFIX}-{wf.id}"
    expect, expect_second = wf.expect, wf.expect_second
    if wf.truth:
        expect, truth_second = wf.truth()
        expect_second = truth_second or expect_second
    expect_second = expect_second or expect
    row: dict = {"app": wf.app, "category": wf.category, "goal": wf.goal, "graded_by": wf.graded_by, "time": now(),
                 "expect": expect, "expect_second": expect_second if wf.second else None}

    # 1. First run (the agent), unless a trace exists and no rerun is asked for.
    if not args.regression and (args.rerun_agent or agent_row(task_id) is None):
        await chrome_blank(wf.app)
        await device.launch(wf.app, fresh=True)
        await asyncio.sleep(2.0)
        blocked = bot_check(await device.observe())
        agent = AgentRunner(device, adapter=adapter, approver=approver, config=RunConfig(data_scope="real", max_steps=25, max_cost_usd=0.25))
        res = await agent.run(wf.goal, task_id=task_id, memory=wf.memory)
        row["bot_check_at_launch"] = blocked
        print(f"agent    {wf.id:18s} {res.status:9s} {res.steps:2d} steps {res.model_calls:2d} calls {res.duration_s:6.1f}s "
              f"{redact(wf, res.result)!s:.80}", flush=True)
    a = agent_row(task_id)
    if a is None:
        row["first_run"] = "not run"
        return row
    a_ok = a["status"] == "done" and right(a["result"], in_sentence(expect), {})
    row["_secrets"] = [a["result"]]  # run_one scrubs a private row of these words
    row["agent"] = {**a, "result": redact(wf, a["result"])}
    row["first_run"] = ("pass" if a_ok else "wrong") if a["status"] == "done" else ("right, unverified" if a["status"] == "done_unverified"
                        and right(a["result"], in_sentence(expect), {}) else
        "bot check" if row.get("bot_check_at_launch") or re.search(r"bot|human verification|captcha", a["result"] or "", re.I) else a["status"])

    # 2. Compile (Muse Wonder, or its cached answer).
    spec_dir = PRIVATE_DIR if wf.private else SPEC_DIR
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / f"{wf.id}.spec.json"
    for old in (REPO / "eval/results/phase2/compiled-real" / spec_file.name, PRIVATE_DIR / spec_file.name):
        if not spec_file.exists() and old.exists():
            spec_file.write_text(old.read_text())  # a Phase 2 compile answer for the same trace
    cached = CompiledRoutine.model_validate_json(spec_file.read_text()) if (args.reuse_spec or args.regression) and spec_file.exists() else None
    try:
        routine, report = await compile_trace(RUNS / task_id, adapter=adapter, memory=wf.memory, spec=cached)
        if cached is None and report.wonder:
            spec_file.write_text(json.dumps(report.wonder, indent=1, ensure_ascii=False))
    except NotCompilable as e:
        row["compile"] = {"compiled": False, "reason": str(e)[:300]}
        print(f"compile  {wf.id:18s} not compiled: {str(e)[:120]}", flush=True)
        return row
    (spec_dir / f"{wf.id}.yaml").write_text(dump_yaml(routine))
    row["compile"] = {"compiled": True, "routine": routine.routine, "steps": len(routine.steps),
                      "inputs": {k: redact(wf, v.example) for k, v in routine.inputs.items()}, "outputs": routine.outputs,
                      "dropped": report.dropped, "warnings": report.warnings, "cost_usd": round(report.cost_at_standard_usd, 4)}
    print(f"compile  {wf.id:18s} {routine.routine}: {len(routine.steps)} steps, inputs {list(routine.inputs)}, outputs {routine.outputs}", flush=True)

    # 3 and 4. Reruns: same input, then a second input; repair only if the strict run fails.
    ex = RoutineExecutor(device, adapter=adapter, approver=approver, config=ExecConfig(data_scope="real"))
    cases = [("same input", {k: v.example or "" for k, v in routine.inputs.items()}, expect)]
    if wf.second:
        alt = {}
        for k, v in routine.inputs.items():  # replace the part of the example that the second input changes
            example = v.example or ""
            alt[k] = next((new if norm(old) == norm(example) else example.replace(old, new)
                           for old, new in wf.second.items() if norm(old) in norm(example)), example)
        cases.append(("new input", alt, expect_second))
        row["second_input_bound"] = alt != cases[0][1]
    runs = []
    for name, inputs, pattern in cases:
        if name == "new input" and not row["second_input_bound"]:
            runs.append({"case": name, "result": "input not learned", "detail": "the compiled routine has no input the second value fits"})
            continue
        for allow_repair in (False, True):
            await chrome_blank(wf.app)
            out = await ex.run(routine, inputs, task_id=f"{task_id}-{name.replace(' ', '-')}-{'repair' if allow_repair else 'strict'}",
                               launch="fresh", allow_repair=allow_repair, allow_agent=False, memory=wf.memory)
            text = " | ".join(v for v in out.outputs.values() if v)
            row["_secrets"].append(text)
            blocked = out.status != "done" and bot_check(await device.observe())
            result = ("bot check" if blocked else "fail") if out.status != "done" else (
                ("pass" if not allow_repair and out.model_calls == 0 else "pass after repair") if right(text, pattern, inputs, wf.graded_by == "truth")
                else "wrong")
            runs.append({"case": name, "inputs": redact(wf, inputs), "repair_allowed": allow_repair, "status": out.status, "result": result,
                         "detail": out.detail[:300], "outputs": redact(wf, out.outputs), "rung": out.rung, "model_calls": out.model_calls,
                         "cost_usd": round(out.cost_at_standard_usd, 4), "duration_s": out.duration_s, "steps": step_rows(out),
                         "patches": [p.description for p in out.patches], "popups": out.popups})
            print(f"routine  {wf.id:18s} {name:10s} {'repair' if allow_repair else 'strict'}: {result:17s} calls={out.model_calls} "
                  f"{out.duration_s:5.1f}s {redact(wf, out.outputs)!s:.70} {out.detail[:70]}", flush=True)
            if out.status == "done" or blocked:
                break  # done (right or wrong), or a bot check a repair can't help with
    row["routine_runs"] = runs
    return row


def stage(row: dict, case: str) -> str:
    runs = [r for r in row.get("routine_runs", []) if r["case"] == case]
    return runs[-1]["result"] if runs else "–"


def report() -> str:
    d = json.loads((OUT / "suite.json").read_text())
    rows = d["workflows"]
    n = len(rows)
    first = sum(r.get("first_run") == "pass" for r in rows.values())
    compiled = sum(bool(r.get("compile", {}).get("compiled")) for r in rows.values())
    same = sum(stage(r, "same input") == "pass" for r in rows.values())
    same_any = sum(stage(r, "same input") in ("pass", "pass after repair") for r in rows.values())
    with_second = [r for r in rows.values() if r.get("expect_second")]
    second = sum(stage(r, "new input") == "pass" for r in with_second)
    bots = [k for k, r in rows.items() if "bot check" in (r.get("first_run"), stage(r, "same input"), stage(r, "new input"))]
    calls = sum((r.get("agent") or {}).get("model_calls") or 0 for r in rows.values())
    md = ["# Real-app test set (envoy-real, read-only)", "",
          f"Last run {d['time']}. {n} workflows in {len({r['category'] for r in rows.values()})} categories; "
          f"{sum(r['graded_by'] == 'truth' for r in rows.values())} graded against ground truth, the rest by the answer's shape. "
          "Built by `eval/run_real_apps.py`; `--regression` reruns it after a routines change with no agent runs and cached compile answers.", "",
          "| Stage | Passed |", "| --- | --- |",
          f"| 1. First run: the agent gives a right answer | {first}/{n} |",
          f"| 2. Compile: the trace becomes a routine | {compiled}/{n} |",
          f"| 3. Same input: the routine reruns right with no model call | {same}/{n} ({same_any} counting a repair) |",
          f"| 4. New input: right with a second input, no model call | {second}/{len(with_second)} |",
          f"| Stopped by a bot check | {len(bots)} ({', '.join(bots) or 'none'}) |", "",
          f"First runs: {calls} model calls in all.", "",
          "| Workflow | Category | Graded by | 1. First run | 2. Compiled | 3. Same input | 4. New input | Agent | Routine (same input) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k, r in rows.items():
        a = r.get("agent") or {}
        c = r.get("compile") or {}
        same_run = next((x for x in reversed(r.get("routine_runs", [])) if x["case"] == "same input"), {})
        comp = f"✅ {c.get('steps')} steps" if c.get("compiled") else (f"❌ {c.get('reason', '')[:60]}" if c else "–")
        agent = f"{a.get('steps')} steps, {a.get('model_calls')} calls, {a.get('duration_s')} s" if a else "–"
        rout = f"{same_run.get('duration_s')} s, {same_run.get('model_calls')} calls" if same_run.get("duration_s") is not None else "–"
        md.append(f"| {k} | {r['category']} | {r['graded_by']} | {r.get('first_run', '–')} | {comp} | {stage(r, 'same input')} | "
                  f"{stage(r, 'new input') if r.get('expect_second') else 'n/a'} | {agent} | {rout} |")
    md += ["", "## Why each miss happened", ""]
    for k, r in rows.items():
        notes = []
        if r.get("first_run") not in ("pass", None):
            notes.append(f"first run {r.get('first_run')}: {str((r.get('agent') or {}).get('result'))[:160]}")
        if r.get("compile") and not r["compile"].get("compiled"):
            notes.append(f"not compiled: {r['compile'].get('reason', '')[:160]}")
        for case in ("same input", "new input"):
            x = next((x for x in reversed(r.get("routine_runs", [])) if x["case"] == case), None)  # the case's last run
            if x and x.get("result") != "pass":
                notes.append(f"{case}: {x.get('result')} ({str(x.get('outputs', ''))[:80]}; {x.get('detail', '')[:120]})")
        if notes:
            md.append(f"- **{k}**: " + " · ".join(notes).replace("|", "/"))
    return "\n".join(md) + "\n"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--rerun-agent", action="store_true", help="run the agent again even where a trace exists")
    ap.add_argument("--reuse-spec", action="store_true", help="reuse the cached compile answer (no Wonder call)")
    ap.add_argument("--regression", action="store_true", help="no agent runs and cached compile answers: 0 model calls unless a repair runs")
    ap.add_argument("--report", action="store_true", help="only rebuild report.md")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "suite.json"
    if not args.report:
        device = EmulatorDevice("envoy-real").connect()
        adapter = ModelAdapter()
        approver = ScriptedApprover(approve=False)  # real apps: every approval is declined; nothing irreversible runs
        results = json.loads(path.read_text())["workflows"] if path.exists() else {}
        for wf in WORKFLOWS:
            if args.only and wf.id not in args.only.split(","):
                continue
            try:
                results[wf.id] = await run_one(wf, args, device, adapter, approver)
            except Exception as e:  # one app's failure must not stop the suite
                results[wf.id] = {"app": wf.app, "category": wf.category, "goal": wf.goal, "graded_by": wf.graded_by,
                                  "first_run": "error", "error": f"{type(e).__name__}: {e}"[:300]}
                print(f"error    {wf.id:18s} {type(e).__name__}: {e}", flush=True)
            order = [w.id for w in WORKFLOWS]
            results = dict(sorted(results.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))
            path.write_text(json.dumps({"time": now(), "workflows": results}, indent=1, ensure_ascii=False, default=str))
    (OUT / "report.md").write_text(report())
    print(report())
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
