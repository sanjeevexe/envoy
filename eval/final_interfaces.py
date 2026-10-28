"""A7 interfaces, end to end: the Phase 4 and Phase 5 scripted checks, through the running API, on the final commit.

  uv run --project backend python eval/run_final.py interfaces [--restart-api]

  phase4          eval/run_phase4.py: sign-in hand-off, takeover, approval with a screenshot, check-in, memory, MCP, chat, live view
  approval_modes  eval/run_approval_modes.py: your request doesn't ask again; MCP asks; a standing approval; "always ask"
  phase5          eval/run_phase5.py: push approvals (a fake push service), a screenshot into memory, voice, live view over HTTPS

Phase 4 and Phase 5 each start from `scripts/demo_setup.py` (SkyLark signed out, a fresh demo memory), which needs the API
stopped, so with --restart-api this stops the API on :8700, sets up, starts it again on the current code (output to
logs/api.out, never printed: it holds the sign-in link), and checks /healthz reports the current commit. Without it, the
running API must already be on the current commit. The scripts' own result files (eval/results/phase4, phase5) are kept
as they were; this run's copies go to eval/results/final/interfaces/.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from typing import Any

import httpx

from final_common import OUT, REPO, Suite, code_state

SCRIPTS = {"phase4": ("eval/run_phase4.py", [REPO / "eval/results/phase4/gate.json"]),
           "approval_modes": ("eval/run_approval_modes.py", [REPO / "eval/results/phase4/approval_modes.json"]),
           "phase5": ("eval/run_phase5.py", [REPO / "eval/results/phase5/gate.json"])}
UV = ["uv", "run", "--project", "backend", "python"]


def api_commit() -> str | None:
    try:
        return httpx.get("http://127.0.0.1:8700/healthz", timeout=3).json().get("commit")
    except Exception:  # noqa: BLE001
        return None


def stop_api() -> None:
    pids = subprocess.run(["lsof", "-t", "-iTCP:8700", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    for p in pids:
        os.kill(int(p), signal.SIGTERM)
    for _ in range(60):
        if not subprocess.run(["lsof", "-t", "-iTCP:8700", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.strip():
            return
        time.sleep(0.5)
    raise RuntimeError("the API on :8700 didn't stop")


def start_api() -> None:
    log = open(REPO / "logs" / "api.out", "a")  # holds the sign-in link: never printed
    subprocess.Popen([*UV, "-m", "api", "--profile", "demo"], cwd=REPO, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(120):
        if api_commit():
            return
        time.sleep(0.5)
    raise RuntimeError("the API didn't come up on :8700")


def demo_setup() -> None:
    subprocess.run([*UV, "scripts/demo_setup.py"], cwd=REPO, check=True, capture_output=True, text=True, timeout=600)


def run_script(name: str) -> dict[str, Any]:
    script, outputs = SCRIPTS[name]
    saved = {p: p.read_bytes() for p in outputs if p.exists()}
    t0 = time.time()
    r = subprocess.run([*UV, script], cwd=REPO, capture_output=True, text=True, timeout=1800, env={**os.environ, "GRPC_VERBOSITY": "ERROR"})
    (OUT / "interfaces").mkdir(parents=True, exist_ok=True)
    (OUT / "interfaces" / f"{name}.log").write_text(r.stdout[-20000:] + ("\n--- stderr ---\n" + r.stderr[-5000:] if r.returncode else ""))
    results = {}
    for p in outputs:
        if p.exists():
            results[p.name] = json.loads(p.read_text())
            (OUT / "interfaces" / f"{name}-{p.name}").write_text(p.read_text())
        if p in saved:
            p.write_bytes(saved[p])  # the phase's own record stays as it was
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("OK ", "BAD", "PASS", "FAIL"))]
    ok = r.returncode == 0
    print(f"{'PASS' if ok else 'FAIL'} {name}: exit {r.returncode}, {len(lines)} checks, {time.time() - t0:.0f} s", flush=True)
    return {"result": "passed" if ok else "failed", "exit": r.returncode, "seconds": round(time.time() - t0), "checks": lines[:60], "results": results}


async def cmd_interfaces(args: Any) -> None:
    s = Suite("interfaces", label="Interfaces, end to end")
    s.extra_prefixes = ["task-", "chat", "voice", "eval-", "photo"]  # the API names its own tasks; this run's window only
    head = code_state()["commit"]
    from final_common import load
    checks: dict[str, Any] = dict((load("interfaces") or {}).get("checks", {}))  # parts not run this time keep their results
    parts = args.parts.split(",")
    for name in ("phase4", "approval_modes", "phase5"):
        if name not in parts:
            continue
        if args.restart_api and name in ("phase4", "phase5"):
            stop_api()
            demo_setup()
            start_api()
        commit = api_commit()
        if commit != head:
            why = f"the API runs {str(commit)[:8]}, not this commit {head[:8]} (use --restart-api)"
            print(f"SKIP {name}: {why}", flush=True)
            checks.setdefault(name, {"result": "not run", "why": why})  # an earlier result stays, with the commit it ran on
            continue
        checks[name] = {**run_script(name), "api_commit": commit}
    md = ["| Check | Result | Time | What it covers |", "| --- | --- | --- | --- |"]
    what = {"phase4": "sign-in hand-off and takeover, approval with a screenshot by the person, check-in done, memory updated, MCP (no approve tool), chat from memory, live view",
            "approval_modes": "your own request isn't asked again; the same request from MCP asks; a standing approval; always ask",
            "phase5": "approval and Done pushes (decrypted by a fake push service, no nonce), a screenshot into memory, voice through Muse Voice Transcribe, live view over the tailnet"}
    for k, v in checks.items():
        on = f" (on `{str(v['api_commit'])[:7]}`)" if v.get("api_commit") and str(v["api_commit"]) != head else ""
        md.append(f"| {k} | {v['result']}{on}{' — ' + v['why'] if v.get('why') else ''} | {v.get('seconds', '–')} s | {what[k]} |")
    md += ["", "The Muse route (the Muse app on the iPhone through a public tunnel to `/mcp`) needs you to start the tunnel; it isn't scripted here."]
    s.save({"checks": checks}, "\n".join(md) + "\n")

