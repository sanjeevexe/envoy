"""The agent path and "Make it a routine" over MCP, as declared in eval/results/learn-agent-path/PROTOCOL.md.

A harness acting as an outside agent asks a test API copy at the `eval-final` tag each real-app question with run_task
over MCP. The copy's own session token stands in for the person: it asks "Make it a routine", shares the routine, and
declines every approval. The harness then calls the new tool over MCP with the second input, and each answer is graded
by the real-app suite's graders (eval/run_real_apps.py at the tag).

  uv run --project backend python eval/run_learn_path.py --copy <checkout at eval-final> --api-dir <new folder> \\
      [--port 8766] [--phone envoy-real] [--only amazon,starbucks] [--retry <workflow>] [--dry-run]
  uv run --project backend python eval/run_learn_path.py --report     # README.md again from results.json

The copy is started and stopped by the harness: `--profile demo`, model profile hybrid, its own ENVOY_API_DIR (a new
folder: 0 push subscriptions, its own session token, its own agent key) and ENVOY_OUTBOX. Its checkout must be clean, at
the tag, with its own logs/ folder (the compile's model calls are counted from the copy's cost log). Keys and tokens are
read from files and never printed. The phone is touched only with `adb -s <serial>` (the suite's SERIAL) to prepare each
task: Chrome on about:blank first, the app force-stopped, then the home screen. envoy-real is claimed and cold-booted
before the pass (`coord/devices.sh claim`, `scripts/start_emulator.sh envoy-real`) and stopped after; the harness does
neither.

`--dry-run` needs no phone: no preparation and no truth graders (the recorded patterns stand in). It runs the first
task through the same calls (it ends without an answer), then shares a routine already in the tag's library, checks
tools/list and calls that tool. Its results go to <api-dir>/dry-run.json, never to the results folder.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
import final_common  # noqa: E402,F401  (sets sys.path for the backend)
import run_real_apps as rr  # noqa: E402
from mcp_tool_check import Client  # noqa: E402
from routines.model import load_yaml  # noqa: E402
from routines.screens import norm  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "eval" / "results" / "learn-agent-path"
CAP_S = 360  # each run_task, learn and tool call (PROTOCOL.md: 6 min)
POLL_S = 2.0
ENDED = {"done", "failed", "declined", "stopped", "needs_you", "taken_over"}
BLOCKED = re.compile(r"\bbot\b|blocks emulators|human verification|captcha|press and hold|sign[- ]?in|log[- ]?in", re.I)
LIBRARY_EMPTIED = re.compile(r"^D  data/routines/")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True).stdout.strip()


# ---- the copy ------------------------------------------------------------------------------------------------------


class Copy:
    """The API copy at the tag, started here and stopped at the end."""

    def __init__(self, checkout: Path, api_dir: Path, port: int) -> None:
        self.checkout, self.api_dir, self.port = checkout, api_dir, port
        self.base = f"http://127.0.0.1:{port}"
        self.proc: subprocess.Popen | None = None

    def check(self, dry: bool, empty_library: bool = False) -> dict:
        """`empty_library`: the supplementary pass (README, Deviations), whose copy differs from the tag only by its routine
        library deleted (`git rm -r data/routines`)."""
        tag = git(self.checkout, "rev-parse", "eval-final^{commit}")
        head = git(self.checkout, "rev-parse", "HEAD")
        dirty = [ln for ln in git(self.checkout, "status", "--porcelain", "--untracked-files=no").splitlines() if ln]
        problems = []
        if not tag or tag != head:
            problems.append(f"the copy's HEAD {head[:9]} is not eval-final {tag[:9] or '(no tag)'}")
        if empty_library:
            if not dirty or any(not LIBRARY_EMPTIED.match(ln) for ln in dirty):
                problems.append("the copy's only change must be its routine library deleted")
            if any((self.checkout / "data" / "routines").glob("*")):
                problems.append("the copy's routine library isn't empty")
        elif dirty:
            problems.append("the copy's checkout has changes")
        if (self.checkout / "logs").is_symlink():
            problems.append("the copy's logs/ is a link: its cost log must be its own")
        if self.api_dir.exists() and any(self.api_dir.iterdir()):
            problems.append(f"{self.api_dir} is not a new, empty folder")
        same = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", f"{tag}", "--", "eval/run_real_apps.py"]).returncode == 0
        if not same:
            problems.append("this harness's eval/run_real_apps.py differs from the tag's (the tasks and graders must be the tag's)")
        if problems and not dry:
            sys.exit("refusing to start: " + "; ".join(problems))
        return {"eval_final": tag, "copy_head": head, "harness_head": git(REPO, "rev-parse", "HEAD"), "problems": problems,
                "library": "empty" if empty_library else "the tag's"}

    def start(self) -> None:
        self.api_dir.mkdir(parents=True, exist_ok=True)
        (self.api_dir / "outbox").mkdir(exist_ok=True)
        token = self.api_dir / "session_token"
        token.write_text(secrets.token_urlsafe(32))
        token.chmod(0o600)
        env = {**os.environ, "ENVOY_API_DIR": str(self.api_dir), "ENVOY_PORT": str(self.port),
               "ENVOY_OUTBOX": str(self.api_dir / "outbox"), "ENVOY_MODEL_PROFILE": "hybrid"}
        log = (self.api_dir / "server.out").open("w")
        self.proc = subprocess.Popen(["uv", "run", "--project", "backend", "python", "-m", "api", "--profile", "demo"],
                                     cwd=self.checkout, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(90):
            try:
                httpx.get(f"{self.base}/api/tasks", headers=self.headers(), timeout=2)
                break
            except httpx.HTTPError:
                time.sleep(1)
        else:
            self.stop()
            sys.exit(f"the copy didn't come up on :{self.port} (see {self.api_dir}/server.out)")
        key = self.api_dir / "agent.key"
        subprocess.run(["uv", "run", "--project", "backend", "python", "scripts/agent_key.py", "issue", "learn-harness",
                        "--tools", "read,run", "--out", str(key)], cwd=self.checkout, env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=30)

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {(self.api_dir / 'session_token').read_text().strip()}", "X-Envoy": "1",
                "Content-Type": "application/json"}

    def http(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        r = httpx.request(method, self.base + path, headers=self.headers(), json=body, timeout=60)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"text": r.text[:300]}

    def push_subscriptions(self) -> int:
        db = sqlite3.connect(f"file:{self.api_dir / 'envoy.db'}?mode=ro", uri=True)
        try:
            return db.execute("SELECT count(*) FROM push_subs").fetchone()[0]
        finally:
            db.close()

    def compile_calls(self, tid: str, since: str) -> int:
        """Model calls of the learn's compile: Wonder's, and any screenshot read it made, from the copy's own cost log."""
        log = self.checkout / "logs" / "model_costs.jsonl"
        if not log.exists():
            return 0
        n = 0
        for line in log.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            t = str(e.get("task_id") or "")
            if e.get("time", "") >= since and t.startswith(tid) and "event" not in e and (
                    e.get("job") == "compile" or t.endswith("-compile-read")):
                n += 1
        return n

    def decline(self, aid: str) -> bool:
        code, a = self.http("GET", f"/api/approvals/{aid}")
        if code != 200 or a.get("status") != "pending":
            return False
        code, _ = self.http("POST", f"/api/approvals/{aid}", {"nonce": a["nonce"], "decision": "decline"})
        return code == 200


# ---- one task -------------------------------------------------------------------------------------------------------


def follow(copy: Copy, mcp: Client, tid: str, rec: dict) -> dict:
    """get_task over MCP every 2 s until the task ends (cap 6 min), declining every approval on the way."""
    t0, view, declined = time.time(), {}, []
    while time.time() - t0 < CAP_S:
        _, view = mcp.call("get_task", {"task_id": tid})
        if not isinstance(view, dict) or view.get("error"):
            view = {"status": "error", "error": str(view.get("error") if isinstance(view, dict) else view)[:200]}
            break
        for a in view.get("pending_approvals") or []:
            if a["approval_id"] not in declined and copy.decline(a["approval_id"]):
                declined.append(a["approval_id"])
        if view.get("status") in ENDED:
            break
        time.sleep(POLL_S)
    else:
        copy.http("POST", f"/api/tasks/{tid}/stop")
        view = {**view, "status": "timed out"}
    _, full = copy.http("GET", f"/api/tasks/{tid}")
    task = full.get("task") or {}
    rec.update({"status": view.get("status"), "seconds": round(time.time() - t0, 1), "model_calls": task.get("model_calls"),
                "cost_usd": task.get("cost_usd"), "approvals_declined": len(declined)})
    return {"view": view, "task": task}


def outputs_text(result: str | None, outputs: list[str]) -> str:
    """A routine task's result ("uberx price: $11.95; …") as the suite grades routine outputs: the values, joined by " | "."""
    if not result:
        return ""
    values = []
    for part in result.split("; "):
        for name in outputs:
            label = name.replace("_", " ") + ": "
            if part.startswith(label):
                values.append(part[len(label):])
    return " | ".join(values) if values else result


def blocked(*texts: str | None) -> bool:
    return any(t and BLOCKED.search(t) for t in texts)


async def prepare(wf: rr.Workflow, dry: bool) -> None:
    """As a fresh agent run in run_real_apps.py: Chrome on about:blank first, the app force-stopped; then the home screen."""
    if dry:
        return
    await rr.chrome_blank(wf.app)
    rr.adb("shell", "am", "force-stop", wf.app)
    rr.adb("shell", "input", "keyevent", "KEYCODE_HOME")
    await asyncio.sleep(1.0)


async def run_task(wf: rr.Workflow, copy: Copy, mcp: Client, phone: str, dry: bool, row_id: str) -> dict:
    expect, expect_second = wf.expect, wf.expect_second
    if wf.truth and not dry:
        expect, truth_second = wf.truth()
        expect_second = truth_second or expect_second
    expect_second = expect_second or expect
    row: dict = {"row": row_id, "workflow": wf.id, "app": wf.app, "question": wf.goal, "graded_by": wf.graded_by,
                 "second": wf.second or None, "time": now()}
    secrets_seen: list[str] = []

    # a. The agent path.
    await prepare(wf, dry)
    a: dict = {}
    err, res = mcp.call("run_task", {"goal": wf.goal, "phone": phone})
    tid = res.get("task_id") if isinstance(res, dict) else None
    if err or not tid:
        a.update({"outcome": "no answer", "error": str(res)[:300]})
        row.update({"agent": a, "learn": {"outcome": "not learnable", "reason": "no task"}})
        return row
    a["task_id"] = tid
    got = follow(copy, mcp, tid, a)
    answer = got["task"].get("result") or got["view"].get("result")
    secrets_seen.append(answer or "")
    a["answer"] = rr.redact(wf, answer)
    if got["task"].get("routine"):
        a["library_routine"] = got["task"]["routine"]  # run_task matched the library: a routine ran, not the agent
    if a["status"] == "done":
        a["outcome"] = "right" if rr.right(answer, rr.in_sentence(expect), {}) else "wrong"
    else:
        a["outcome"] = "blocked" if blocked(answer, got["task"].get("detail")) else "no answer"
    row["agent"] = a

    # b. Make it a routine.
    lr: dict = {}
    row["learn"] = lr
    if a["status"] != "done":
        lr.update(unlearned(a))
        return finish(wf, row, secrets_seen)
    since = now()
    for _ in range(15):  # the phone stays leased a moment after the task ends; a person would wait for it too
        code, view = copy.http("POST", f"/api/tasks/{tid}/learn")
        if code != 409 or not re.search(r"using this phone|being taught", str(view.get("detail"))):
            break
        time.sleep(POLL_S)
    if code != 200:
        lr.update(unlearned(a, str(view.get("detail") or view)[:300]))
        return finish(wf, row, secrets_seen)
    t0, declined = time.time(), 0
    while time.time() - t0 < CAP_S and view.get("status") in ("compiling", "replaying"):
        time.sleep(POLL_S)
        _, full = copy.http("GET", f"/api/tasks/{tid}")
        view = (full.get("task") or {}).get("learn") or view
        if (rt := view.get("replay_task")):
            _, rfull = copy.http("GET", f"/api/tasks/{rt}")
            if (rfull.get("task") or {}).get("status") == "waiting_approval" and copy.decline(rfull["task"].get("waiting_for") or ""):
                declined += 1
    replay = view.get("replay") or {}
    detail = view.get("detail") or ""
    lr.update({"status": view.get("status"), "reason": detail[:300], "routine": view.get("routine"), "version": view.get("version"),
               "replay_seconds": replay.get("duration_s"), "replay_model_calls": replay.get("model_calls"),
               "compile_model_calls": copy.compile_calls(tid, since), "compile_cost_usd": view.get("cost_usd"),
               "seconds": round(time.time() - t0, 1), "approvals_declined": declined})
    if view.get("status") == "saved":
        lr["outcome"] = "saved"
    elif view.get("status") in ("compiling", "replaying"):
        lr["outcome"], lr["reason"] = "replay failed", f"timed out while {view.get('status')}"
        copy.http("POST", f"/api/tasks/{view.get('replay_task')}/stop") if view.get("replay_task") else None
    elif blocked(detail):
        lr["outcome"] = "blocked"
    elif detail.startswith("can't become a routine"):
        lr["outcome"] = "not compilable"
    else:
        lr["outcome"] = "replay failed"
    if lr["outcome"] != "saved":
        return finish(wf, row, secrets_seen)

    # c. Share, and look for the tool.
    name = lr["routine"]
    code, shared = copy.http("POST", f"/api/routines/{name}/share", {"on": True})
    tool = shared.get("tool") if code == 200 else None
    tools = [t["name"] for t in mcp.rpc("tools/list")["tools"]]
    row["share"] = {"tool": tool, "outcome": "share failed" if code != 200 else ("listed" if tool and tool in tools else "shared, not listed")}
    if row["share"]["outcome"] != "listed":
        return finish(wf, row, secrets_seen)

    # d. Call the new tool: the second input, else the same input again.
    _, rdoc = copy.http("GET", f"/api/routines/{name}")
    routine = load_yaml(rdoc["yaml"])
    same = {k: v.example or "" for k, v in routine.inputs.items()}
    inputs, pattern, case = same, expect, "same input"
    if wf.second:
        alt = {}
        for k, v in routine.inputs.items():  # as the suite does: the part of the example the second input changes
            example = v.example or ""
            alt[k] = next((new if norm(old) == norm(example) else example.replace(old, new)
                           for old, new in wf.second.items() if norm(old) in norm(example)), example)
        inputs, pattern, case = alt, expect_second, "new input"
        if alt == same:
            row["call"] = {"case": case, "outcome": "not run", "reason": "input not learned: no input of the routine fits the second value"}
            return finish(wf, row, secrets_seen)
    c: dict = {"case": case, "tool": tool, "inputs": rr.redact(wf, inputs)}
    err, res = mcp.call(tool, {**inputs, "phone": phone})
    ctid = res.get("task_id") if isinstance(res, dict) else None
    if err or not ctid:
        c.update({"outcome": "no answer", "error": str(res)[:300]})
        row["call"] = c
        return finish(wf, row, secrets_seen)
    c["task_id"] = ctid
    got = follow(copy, mcp, ctid, c)
    text = outputs_text(got["task"].get("result"), routine.outputs)
    secrets_seen.append(text)
    c["answer"] = rr.redact(wf, text)
    if c["status"] != "done":
        c["outcome"] = "no answer"
    elif not rr.right(text, pattern, inputs, wf.graded_by == "truth"):
        c["outcome"] = "wrong"
    else:
        c["outcome"] = "right, 0 calls" if not c.get("model_calls") else "right with model calls"
    row["call"] = c
    return finish(wf, row, secrets_seen)


def unlearned(a: dict, refused: str | None = None) -> dict:
    """Stage b for a task "Make it a routine" can't take: one that didn't end done, or one the learn refused."""
    lib = a.get("library_routine")
    if refused is not None:
        return {"outcome": "not learnable", "reason": f"ran library routine {lib}: {refused}" if lib else refused}
    return {"outcome": "blocked" if a["outcome"] == "blocked" else "not learnable",
            "reason": f"ran library routine {lib}, which ended {a['status']}" if lib else f"the task ended {a['status']}"}


def amend(rows: list[dict], db: Path) -> list[str]:
    """Rows recorded before the harness noted library routines and counted "blocks emulators" as a block: the same rules,
    applied afterwards from the stopped copy's own task records (read-only). Returns what changed."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    changed = []
    try:
        for r in rows:
            a, lr = r.get("agent") or {}, r.get("learn") or {}
            t = con.execute("SELECT routine, detail, result FROM tasks WHERE id=?", (a.get("task_id"),)).fetchone() if a.get("task_id") else None
            if t is None:
                continue
            routine, detail, result = t
            before = (a.get("outcome"), lr.get("outcome"), lr.get("reason"))
            if routine and not a.get("library_routine"):
                a["library_routine"] = routine
            if a.get("outcome") == "no answer" and blocked(result, detail):
                a["outcome"] = "blocked"
            if a.get("status") != "done":
                lr.update(unlearned(a))
            elif routine and lr.get("outcome") == "not learnable" and not lr["reason"].startswith("ran library routine"):
                lr["reason"] = f"ran library routine {routine}: {lr['reason']}"
            if (a.get("outcome"), lr.get("outcome"), lr.get("reason")) != before:
                changed.append(f"{r['row']}: a {before[0]} → {a.get('outcome')}, b {before[1]} → {lr.get('outcome')}"
                               + (f" ({lr.get('reason')})" if lr.get("reason") != before[2] else ""))
    finally:
        con.close()
    return changed


def finish(wf: rr.Workflow, row: dict, seen: list[str]) -> dict:
    return rr.scrub(row, [s for s in seen if s]) if wf.private else row


# ---- the report -----------------------------------------------------------------------------------------------------


def rates(rows: list[dict]) -> dict:
    first = [r for r in rows if not r["row"].endswith("-retry")]
    saved = [r for r in first if (r.get("learn") or {}).get("outcome") == "saved"]
    with_second = [r for r in saved if r.get("second")]
    right = [r for r in with_second if (r.get("call") or {}).get("outcome", "").startswith("right")]
    return {"tasks": len(first), "agent_right": sum((r.get("agent") or {}).get("outcome") == "right" for r in first),
            "saved": len(saved), "saved_with_second": len(with_second), "new_input_right": len(right),
            "new_input_right_0_calls": sum(r["call"]["outcome"] == "right, 0 calls" for r in right)}


def summary(doc: dict) -> list[str]:
    r = rates(doc["rows"])
    return [f"`eval-final` = `{doc['versions']['eval_final'][:9]}` (copy HEAD `{doc['versions']['copy_head'][:9]}`, harness "
            f"`{doc['versions']['harness_head'][:9]}`), {doc['started']} → {doc.get('ended', '…')}.", "",
            f"- **Agent path:** right {r['agent_right']}/{r['tasks']}.",
            f"- **Learn rate:** saved {r['saved']}/{r['tasks']}.",
            f"- **New input:** right {r['new_input_right']}/{r['saved_with_second']} saved routines with a second input; "
            f"{r['new_input_right_0_calls']} of them with 0 model calls.", ""]


def table(rows: list[dict]) -> list[str]:
    lines = ["| Row | a. Agent path | b. Make it a routine | c. Share | d. Call | Calls (a / compile / replay / d) |",
             "| --- | --- | --- | --- | --- | --- |"]
    for x in rows:
        a, lr, sh, c = x.get("agent") or {}, x.get("learn") or {}, x.get("share") or {}, x.get("call") or {}
        lines.append(f"| {x['row']} | {a.get('outcome', '–')}"
                     + (f" (library routine {a['library_routine']})" if a.get("library_routine") else "")
                     + f" | {lr.get('outcome', '–')}"
                     + (f" ({lr['reason'][:100]})" if lr.get("outcome") not in (None, "saved") and lr.get("reason") else "")
                     + f" | {sh.get('outcome', '–')} | {(c.get('case', '') + ': ') if c else ''}{c.get('outcome', '–')} | "
                     f"{a.get('model_calls', '–')} / {lr.get('compile_model_calls', '–')} / {lr.get('replay_model_calls', '–')} / {c.get('model_calls', '–')} |")
    return lines


def by_hand(rows: list[dict]) -> list[str]:
    return [f"- {x['row']}: {stage} answer {ans!r}" for x in rows if x.get("graded_by") == "shape"
            for stage, ans in (("first-run", (x.get("agent") or {}).get("answer")), ("tool-call", (x.get("call") or {}).get("answer"))) if ans]


def readme(doc: dict, extra: dict | None = None) -> str:
    """The pass under the protocol; `extra`, the supplementary pass with an empty library, as its own section."""
    lines = ["# The agent path and \"Make it a routine\": results", "",
             "Run under [PROTOCOL.md](PROTOCOL.md) on " + summary(doc)[0], *summary(doc)[1:],
             *([f"Starting state: {n}" for n in doc.get("notes") or []] + ([""] if doc.get("notes") else [])),
             *table(doc["rows"]),
             "", "## Shape-graded answers to read by hand", "", *(by_hand(doc["rows"]) or ["None."])]
    if extra:
        lines += ["", "## Supplementary pass: an empty routine library (a deviation, outside the headline)", "",
                  *(extra.get("why") or []), "", "Run on " + summary(extra)[0], *summary(extra)[1:], *table(extra["rows"]),
                  "", "Shape-graded answers to read by hand:", "", *(by_hand(extra["rows"]) or ["None."])]
    lines += ["", "## Deviations", "", *(doc.get("deviations") or ["None."]), ""]
    return "\n".join(lines)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", type=Path, help="a clean checkout at eval-final, with .env and its own logs/")
    ap.add_argument("--api-dir", type=Path, help="a new, empty folder for the copy's data")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--phone", default="envoy-real")
    ap.add_argument("--only", default="", help="workflows, comma-separated (the declared order is kept)")
    ap.add_argument("--retry", default="", help="a workflow lost to an infrastructure fault, run again as its own row")
    ap.add_argument("--dry-run", action="store_true", help="no phone: a phone id that doesn't exist, so nothing runs on a device")
    ap.add_argument("--note", action="append", default=[], help="the phone's starting state, said in the README")
    ap.add_argument("--supplementary", action="store_true",
                    help="the deviation pass: a copy whose routine library is deleted; results to supplementary.json")
    ap.add_argument("--why", action="append", default=[], help="the supplementary pass's reason, said in the README")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--amend", type=Path, help="with --report: the pass's stopped api-dir, to apply amend() to results.json")
    ap.add_argument("--deviation", action="append", default=[], help="with --report: a deviation to add to the README")
    args = ap.parse_args()
    results, extra = OUT / "results.json", OUT / "supplementary.json"
    if args.report:
        doc = json.loads(results.read_text())
        if args.amend:
            doc["amended"] = doc.get("amended", []) + amend(doc["rows"], args.amend.resolve() / "envoy.db")
            print("\n".join(doc["amended"]) or "nothing to amend")
        doc["deviations"] = doc.get("deviations", []) + args.deviation
        results.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        (OUT / "README.md").write_text(readme(doc, json.loads(extra.read_text()) if extra.exists() else None))
        return 0
    if args.port == 8700 or args.port < 8701:
        sys.exit("the copy runs on its own port, 8701 or higher")
    if args.dry_run:
        args.phone = "dry-run-no-phone"  # never one of the emulators the eval holds
    copy = Copy(args.copy.resolve(), args.api_dir.resolve(), args.port)
    versions = copy.check(args.dry_run, empty_library=args.supplementary)
    copy.start()
    try:
        subs = copy.push_subscriptions()
        if subs:
            sys.exit(f"the copy has {subs} push subscriptions")
        mcp = Client(f"{copy.base}/mcp", (copy.api_dir / "agent.key").read_text().strip())
        mcp.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "learn-harness", "version": "1"}})
        _, phones = mcp.call("list_phones", {})
        ids = [p.get("id") for p in (phones.get("phones") if isinstance(phones, dict) else []) or []]
        if args.phone not in ids and not args.dry_run:  # (a dry run's phone doesn't exist on purpose)
            sys.exit(f"no phone {args.phone!r} on the copy (it has {ids})")
        out = copy.api_dir / "dry-run.json" if args.dry_run else extra if args.supplementary else results
        doc = json.loads(out.read_text()) if out.exists() and args.retry else {
            "protocol": "eval/results/learn-agent-path/PROTOCOL.md", "versions": versions, "started": now(), "phone": args.phone,
            "push_subscriptions": subs, "phones": ids, "notes": args.note, "rows": [], "deviations": []}
        if args.supplementary:
            doc["why"] = args.why
        only = [w for w in args.only.split(",") if w]
        wanted = [w for w in rr.WORKFLOWS if (not only or w.id in only)]
        if args.retry:
            wanted = [w for w in rr.WORKFLOWS if w.id in args.retry.split(",")]
        if args.dry_run:
            wanted = wanted[:1]
        for wf in wanted:
            row_id = f"{wf.id}-retry" if args.retry else wf.id
            row = await run_task(wf, copy, mcp, args.phone, args.dry_run, row_id)
            doc["rows"].append(row)
            out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
            print(f"{row_id:20s} a:{(row.get('agent') or {}).get('outcome')}  b:{(row.get('learn') or {}).get('outcome')}  "
                  f"c:{(row.get('share') or {}).get('outcome', '–')}  d:{(row.get('call') or {}).get('outcome', '–')}", flush=True)
        if args.dry_run:
            doc["dry_share"] = dry_share(copy, mcp, args.phone)
            print("dry-run share and call:", json.dumps(doc["dry_share"])[:400], flush=True)
        doc["ended"] = now()
        out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        if not args.dry_run:
            main_doc = json.loads(results.read_text()) if args.supplementary else doc
            (OUT / "README.md").write_text(readme(main_doc, json.loads(extra.read_text()) if extra.exists() else None))
        return 0
    finally:
        copy.stop()


def dry_share(copy: Copy, mcp: Client, phone: str) -> dict:
    """c and d's calls on a routine the tag's library already has (no phone: the call ends without an answer)."""
    _, lib = copy.http("GET", "/api/routines")
    names = [r.get("name") or r.get("routine") for r in (lib if isinstance(lib, list) else lib.get("routines", []))]
    name = next((n for n in names if n and n.startswith("skylark_")), names[0] if names else None)
    if name is None:
        return {"error": "no routine in the library"}
    code, shared = copy.http("POST", f"/api/routines/{name}/share", {"on": True})
    tool = shared.get("tool")
    listed = tool in [t["name"] for t in mcp.rpc("tools/list")["tools"]]
    routine = load_yaml(copy.http("GET", f"/api/routines/{name}")[1]["yaml"])
    rec: dict = {"routine": name, "share_status": code, "tool": tool, "listed": listed}
    err, res = mcp.call(tool, {**{k: v.example or "" for k, v in routine.inputs.items()}, "phone": phone}) if listed else (True, "not listed")
    rec["call_error"], rec["call"] = err, res if isinstance(res, dict) else str(res)[:200]
    if isinstance(res, dict) and res.get("task_id"):
        follow(copy, mcp, res["task_id"], rec)
    return rec


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
