"""Cross-app answers end to end (api/crossapp.py): questions that need two apps, on the phones Envoy routes them to.

  META_DAILY_COST_CAP_USD=2 uv run --project backend python eval/run_crossapp.py --data /tmp/crossapp --questions R1 --pairs 2
  ... --serve 600    # then keep the API copy up for 10 minutes, to look at the tasks in the web app

An API copy runs on 127.0.0.1:8713 (or --port) with everything in --data: its tasks, its own memory, its own session
token, and a routine library assembled from the SkyLark routines and the Phase 7 real-app routines
(eval/results/final/real_compiled). It never uses the user's API, memory or token, and sends no push.

Each question runs in two modes, alternated (P S P S …):
- parallel: through chat (the product path: pre-filter → lead → parts, each on the phone routing picks);
- sequential: the same lead and orchestrator, each part started only when the previous one has ended (the baseline).
Wall time is from the message to the combined answer. Every approval is declined; each part's app is closed when the
part ends, and the phone goes home after each question. Real apps: read-only questions, standard tier, no Target.

Results: eval/results/crossapp/runs.json (every run: parent, parts, steps, timeline, approvals, model calls and cost
from the cost log) and report.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
OUT = REPO / "eval" / "results" / "crossapp"
SERIALS = {"envoy-test": "emulator-5554", "envoy-real": "emulator-5556"}
ENDED = ("done", "failed", "declined", "stopped")

# id → (question, phones it needs). R*: real apps only (envoy-real); T*: SkyLark on envoy-test beside a real app.
QUESTIONS: dict[str, tuple[str, list[str]]] = {
    "R1": ("How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?", ["envoy-real"]),
    "R2": ("What's a Caffè Latte at Starbucks vs on DoorDash?", ["envoy-real"]),
    "R3": ("How many calories are in a Caffè Mocha at Starbucks, and what's the address of the Space Needle in Google Maps?", ["envoy-real"]),
    "T1": ("What's my gate for my Denver flight, and what's the address of the Space Needle?", ["envoy-test", "envoy-real"]),
    "T2": ("What's my gate for my Denver flight, and how long is the drive from 1 Hacker Way to SFO?", ["envoy-test", "envoy-real"]),
}


def adb(serial: str, *cmd: str) -> None:
    subprocess.run(["adb", "-s", serial, "shell", *cmd], capture_output=True, timeout=20)


def library(dst: Path) -> Any:
    """SkyLark's routines and the real-app routines Phase 7 compiled, each as v1."""
    from routines.model import load_yaml
    from routines.store import RoutineStore
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(REPO / "data" / "routines", dst)
    store = RoutineStore(dst)
    for y in sorted((REPO / "eval" / "results" / "final" / "real_compiled").glob("*.yaml")):
        if y.name.startswith("gmail"):  # the test account's inbox: no question here needs it
            continue
        try:
            store.add(load_yaml(y.read_text()))
        except (KeyError, ValueError) as e:  # a dump this loader can't read back (youtube_search): left out, said so
            print(f"routine {y.name} left out: {type(e).__name__}: {e}", flush=True)
    return store


def costs_between(t0: float, t1: float) -> dict[str, Any]:
    """Model calls and dollars from the cost log between two times, by job."""
    path = REPO / "logs" / "model_costs.jsonl"
    by_job: dict[str, dict[str, float]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                e = json.loads(line)
                t = datetime.fromisoformat(e["time"]).timestamp()
            except (ValueError, KeyError):
                continue
            if t0 <= t <= t1 and e.get("model"):
                j = by_job.setdefault(e["job"], {"calls": 0, "usd": 0.0})
                j["calls"] += 1
                j["usd"] += e.get("cost_at_standard_usd") or 0.0
    return {"by_job": by_job, "calls": sum(int(j["calls"]) for j in by_job.values()), "usd": round(sum(j["usd"] for j in by_job.values()), 5)}


def lean_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = ("seq", "time", "kind", "text", "status", "rung", "detail", "risk", "approval", "error", "sources", "entities")
    return [{k: s[k] for k in keep if s.get(k) not in (None, "", [], {})} for s in steps]


class Watch:
    """Declines every approval, closes each part's app when it ends, and records when tasks change."""

    def __init__(self, ctx: Any) -> None:
        self.ctx, self.events, self.declined = ctx, [], []
        ctx.bus.listeners.append(self.on_event)

    def on_event(self, ev: dict[str, Any]) -> None:
        if ev.get("type") != "task":
            return
        t = ev["task"]
        self.events.append({"time": ev["time"], "task_id": t["id"], "parent": t.get("parent"), "status": t["status"], "device": t.get("device")})
        if t.get("parent") and t["status"] in ENDED and t.get("app") and t.get("device") in SERIALS:
            asyncio.get_running_loop().run_in_executor(None, adb, SERIALS[t["device"]], "am", "force-stop", t["app"])

    async def decline_forever(self) -> None:
        while True:
            for a in self.ctx.tasks.approvals(status="pending"):
                approver = self.ctx.runner.approvers.get(a["task_id"])
                if approver and approver.decide(a["id"], False, by="eval (every approval is declined)"):
                    self.declined.append({"task_id": a["task_id"], "description": a["description"]})
            await asyncio.sleep(0.3)


async def run_one(ctx: Any, watch: Watch, qid: str, mode: str) -> dict[str, Any]:
    from api.chat import chat
    from api.crossapp import lead
    message = QUESTIONS[qid][0]
    t0 = time.time()
    if mode == "parallel":
        out = await chat(message, adapter=ctx.adapter, memory=ctx.memory, runner=ctx.runner, routines=ctx.routines, source="chat")
        parent = out.get("task") if out.get("kind") == "task" else None
        if not parent or parent.get("kind") != "crossapp":
            return {"question": qid, "mode": mode, "message": message, "error": "chat didn't split it", "chat": {k: v for k, v in out.items() if k != "task"}}
    else:
        split, _ = await lead(message, ctx.adapter, ctx.routines)
        if split is None:
            return {"question": qid, "mode": mode, "message": message, "error": "the lead didn't split it"}
        parent = ctx.runner.crossapp.start(message, split, "chat", sequential=True)
    pid = parent["id"]
    answered = None
    while time.time() - t0 < 900:
        p = ctx.tasks.get(pid)
        if p["status"] in ENDED:
            answered = time.time()
            break
        await asyncio.sleep(0.1)
    try:
        await asyncio.wait_for(asyncio.shield(ctx.runner.jobs[pid]), 300)  # the parts' and the answer's memory writes
    except Exception:  # noqa: BLE001
        pass
    finished = time.time()
    kids = sorted((t for t in ctx.tasks.list(200) if t.get("parent") == pid), key=lambda t: t["created_at"])
    for k in kids:
        if k.get("device") in SERIALS:
            adb(SERIALS[k["device"]], "am", "force-stop", k.get("app") or "")
    for d in {k.get("device") for k in kids if k.get("device") in SERIALS}:
        adb(SERIALS[d], "input", "keyevent", "KEYCODE_HOME")
    steps = ctx.tasks.steps(pid)
    timeline = next((s for s in steps if s["kind"] == "timeline"), {})
    answer = next((s for s in steps if s["kind"] == "answer"), {})
    return {"question": qid, "mode": mode, "message": message, "parent_id": pid, "started": t0,
            "wall_s": round((answered or finished) - t0, 2), "with_memory_s": round(finished - t0, 2),
            "overlap_s": timeline.get("overlap_s"), "status": ctx.tasks.get(pid)["status"], "answer": ctx.tasks.get(pid)["result"],
            "values": [{k: v.get(k) for k in ("label", "app_name", "status", "result", "screen", "time", "device", "kind", "routine", "why")}
                       for v in answer.get("values", [])],
            "sources": answer.get("sources"), "timeline": timeline.get("parts"),
            "parts": [{"task_id": k["id"], "goal": k["goal"], "app": k["app"], "device": k.get("device"), "kind": k.get("kind"),
                       "routine": k.get("routine"), "inputs": k.get("inputs"), "status": k["status"], "result": k.get("result"),
                       "detail": k.get("detail"), "model_calls": k.get("model_calls"), "steps": lean_steps(ctx.tasks.steps(k["id"]))} for k in kids],
            "parent_steps": lean_steps(steps), "approvals": [a for a in watch.declined if a["task_id"] in {k["id"] for k in kids}],
            "approvals_requested": sum(len(ctx.tasks.approvals(task_id=k["id"])) for k in kids),
            "cost": costs_between(t0, finished)}


def idle(run: dict[str, Any]) -> float:
    """Seconds a phone sat unused between consecutive parts on it (the next part was still being matched)."""
    total = 0.0
    for dev in {p.get("device") for p in run.get("timeline") or []}:
        spans = sorted((p["phone_at"], p["ended_at"]) for p in run["timeline"] if p.get("device") == dev and p.get("phone_at") and p.get("ended_at"))
        total += sum(max(0.0, b[0] - a[1]) for a, b in zip(spans, spans[1:]))
    return total


def report(runs: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    from api.crossapp import NAMES
    md = ["# Cross-app answers, end to end", "",
          f"{meta['date']}, branch `{meta['branch']}` at `{meta['commit']}`, phones: {', '.join(meta['phones'])}. Standard tier (`muse-spark-1.3`); "
          f"every approval declined; read-only questions. {meta['calls']} model calls, ${meta['usd']:.3f} at standard prices.", "",
          "Parallel: through chat (pre-filter → lead → parts on the phones routing picks). Sequential: the same lead and "
          "orchestrator, each part started after the previous one ended. Wall time: from the message to the combined answer "
          "(memory is written after it, as for any task).", "",
          "Overlap: seconds two phones were busy at once. Idle: seconds a phone sat unused between two parts that needed it.", "",
          "| Question | Mode | Wall s | Overlap s | Idle s | Parts (phone, path, s on phone) | Calls | $ | Approvals | Status |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        if r.get("error"):
            md.append(f"| {r['question']} | {r['mode']} | – | – | – | {r['error']} | – | – | – | error |")
            continue
        spans = {p["task_id"]: p for p in r.get("timeline") or []}

        def on_phone(tid: str) -> str:
            s = spans.get(tid, {})
            return f"{s['ended_at'] - s['phone_at']:.1f}" if s.get("phone_at") and s.get("ended_at") else "–"  # never got a phone
        parts = "; ".join(f"{NAMES.get(p['app'], p['app'])} ({p.get('device')}, {p.get('routine') or p.get('kind')}, {on_phone(p['task_id'])})"
                          for p in r["parts"])
        md.append(f"| {r['question']} | {r['mode']} | {r['wall_s']} | {r.get('overlap_s')} | {idle(r):.1f} | {parts} | {r['cost']['calls']} | "
                  f"{r['cost']['usd']:.3f} | {r['approvals_requested']} | {r['status']} |")
    md += ["", "## Medians", "", "| Question | Parallel wall s | Sequential wall s | Saved |", "| --- | --- | --- | --- |"]
    for q in dict.fromkeys(r["question"] for r in runs):
        p = [r["wall_s"] for r in runs if r["question"] == q and r["mode"] == "parallel" and not r.get("error")]
        s = [r["wall_s"] for r in runs if r["question"] == q and r["mode"] == "sequential" and not r.get("error")]
        if p and s:
            mp, ms = statistics.median(p), statistics.median(s)
            md.append(f"| {q} | {mp:.1f} (n={len(p)}) | {ms:.1f} (n={len(s)}) | {ms - mp:.1f} s ({(ms - mp) / ms:.0%}) |")
    md += ["", "## Answers", ""]
    for r in runs:
        if r.get("error"):
            continue
        md.append(f"- **{r['question']} {r['mode']}** ({r['message']}): {r['answer']}")
        for label, line in (r.get("sources") or {}).items():
            md.append(f"  - {label}: {line}")
    return "\n".join(md) + "\n"


async def main_async(args: argparse.Namespace) -> None:
    import uvicorn
    from api.app import build
    from api.store import TaskStore
    from memory.store import MemoryStore

    data = Path(args.data).resolve()
    for sub in ("api", "memory.db"):
        p = data / sub
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    (data / "api").mkdir(parents=True, exist_ok=True)
    token = data / "api" / "session_token"
    token.write_text(secrets.token_urlsafe(32))
    token.chmod(0o600)
    app, ctx = build("demo", memory=MemoryStore(data / "memory.db"), routines=library(data / "routines"),
                     tasks=TaskStore(data / "api" / "envoy.db"), scheduler_every_s=3600)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.1)
    print(f"API copy on http://127.0.0.1:{args.port} (token in {token})", flush=True)
    watch = Watch(ctx)
    decliner = asyncio.create_task(watch.decline_forever())
    phones = sorted({p for q in args.questions for p in QUESTIONS[q][1]})
    if "envoy-test" in phones:  # SkyLark (our test app) seeded as the routine suites seed it: a Denver trip with a gate
        from skylark_routines import fixtures
        from testapps.skylark import SkyLark
        sky = SkyLark(SERIALS["envoy-test"])
        if not sky.installed():
            sky.install()
        sky.seed(fixtures())
    for p in phones:  # the first connection to a phone is slow and one at a time: not part of any timing
        await ctx.pool.device(p)
    t_all = time.time()
    runs: list[dict[str, Any]] = []
    prev = json.loads((OUT / "runs.json").read_text()).get("runs", []) if args.append and (OUT / "runs.json").exists() else []
    order = ["parallel", "sequential"] * args.pairs
    for q in args.questions:
        for mode in order:
            r = await run_one(ctx, watch, q, mode)
            runs.append(r)
            print(f"{q} {mode:10s} wall {r.get('wall_s')} s overlap {r.get('overlap_s')} {r.get('status') or r.get('error')}: {r.get('answer')}", flush=True)
            OUT.mkdir(parents=True, exist_ok=True)
            spent = costs_between(t_all - 1, time.time() + 1)
            meta = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "phones": phones, "calls": spent["calls"], "usd": spent["usd"],
                    "branch": subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, cwd=REPO).stdout.strip(),
                    "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()}
            (OUT / "runs.json").write_text(json.dumps({"meta": meta, "runs": prev + runs}, indent=1, default=str, ensure_ascii=False))
            (OUT / "report.md").write_text(report(prev + runs, meta))
    if args.serve:
        print(f"serving for {args.serve} s", flush=True)
        await asyncio.sleep(args.serve)
    decliner.cancel()
    server.should_exit = True
    await serving


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="a folder for the API copy's tasks, memory and routines (wiped first)")
    ap.add_argument("--questions", default="R1", help=f"comma-separated, from {', '.join(QUESTIONS)}")
    ap.add_argument("--pairs", type=int, default=1, help="parallel/sequential pairs per question")
    ap.add_argument("--port", type=int, default=8713)
    ap.add_argument("--serve", type=float, default=0, help="seconds to keep the API copy up after the runs")
    ap.add_argument("--append", action="store_true", help="add to runs.json instead of replacing it")
    args = ap.parse_args()
    args.questions = [q.strip() for q in args.questions.split(",") if q.strip()]
    # The API copy's settings, before anything from api/ is imported: its own folder, port and token; no tailnet links.
    os.environ["ENVOY_API_DIR"] = str(Path(args.data).resolve() / "api")
    os.environ["ENVOY_PORT"] = str(args.port)
    os.environ["ENVOY_PUBLIC_URL"] = f"http://127.0.0.1:{args.port}"
    os.environ.setdefault("MCP_BEARER_TOKEN", secrets.token_urlsafe(24))
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
