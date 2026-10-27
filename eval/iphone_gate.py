"""The Phase 5 gate on the real iPhone: set up, then report what happened (pushes, approval, check-in, memory).

  uv run --project backend python eval/iphone_gate.py prepare [--signed-out]   # SkyLark ready, "always ask" for the run
  ... on the iPhone: ask Envoy to check in; the approval arrives as a push; open it; approve ...
  uv run --project backend python eval/iphone_gate.py report [--out=PATH]      # what happened, with timings
  uv run --project backend python eval/iphone_gate.py restore                  # approval rules as they were

The person does the deciding on the iPhone; this script only prepares the test app and reads the record. It reads
the session token itself (never printed). Results: eval/results/phase5/iphone_gate.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from demo_setup import demo_fixtures  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

BASE = "http://127.0.0.1:8700"
H = {"Authorization": f"Bearer {(REPO / 'data' / 'api' / 'session_token').read_text().strip()}"}
STATE = REPO / "data" / "api" / "iphone_gate.json"
OUT = REPO / "eval" / "results" / "phase5" / "iphone_gate.json"


def prepare(signed_out: bool) -> None:
    SkyLark("emulator-5554").prepare(fixtures=demo_fixtures(signed_in=not signed_out), variant=0)
    rules = httpx.get(f"{BASE}/api/settings/approvals", headers=H).json()["rules"]
    if not STATE.exists():
        STATE.write_text(json.dumps({"rules": rules, "since": time.time()}))
    else:
        STATE.write_text(json.dumps({**json.loads(STATE.read_text()), "since": time.time()}))
    httpx.post(f"{BASE}/api/settings/approvals", json={**rules, "default": "always", "apps": {}, "routines": {}}, headers=H)
    print(f"SkyLark ready ({'signed out' if signed_out else 'signed in'}), Chicago not checked in; approvals: always ask for this run")


def restore() -> None:
    if STATE.exists():
        httpx.post(f"{BASE}/api/settings/approvals", json=json.loads(STATE.read_text())["rules"], headers=H)
        STATE.unlink()
    print("approval rules restored")


def report(out_path: Path = OUT) -> None:
    since = json.loads(STATE.read_text())["since"] if STATE.exists() else time.time() - 3600
    tasks = [t for t in httpx.get(f"{BASE}/api/tasks", params={"limit": 20}, headers=H).json() if t["created_at"] >= since]
    pushes = [json.loads(x) for x in (REPO / "logs" / "push.jsonl").read_text().splitlines() if json.loads(x)["time"] >= since]
    out = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "tasks": []}
    for t in reversed(tasks):
        d = httpx.get(f"{BASE}/api/tasks/{t['id']}", headers=H).json()
        approvals = [{k: a.get(k) for k in ("id", "status", "decided_by", "created_at", "decided_at", "description")} for a in d["approvals"]]
        for a in approvals:
            a["decided_after_s"] = round(a["decided_at"] - a["created_at"], 1) if a.get("decided_at") else None
        out["tasks"].append({"goal": t["goal"], "source": t["source"], "status": t["status"], "result": t.get("result"),
                             "approvals": approvals, "memory": next((s["text"] for s in d["steps"] if s.get("kind") == "memory"), None),
                             "duration_s": round(t["updated_at"] - t["created_at"], 1)})
    sent = {p["push"]: p for p in pushes if p["event"] == "sent"}
    out["pushes"] = [{"kind": p["kind"], "service": sent.get(p["push"], {}).get("service"), "status": sent.get(p["push"], {}).get("status"),
                      "send_ms": sent.get(p["push"], {}).get("send_ms"), "delivery_ms": p["delivery_ms"]} for p in pushes if p["event"] == "receipt"]
    out["pushes_without_receipt"] = [p["kind"] for p in sent.values() if p["push"] not in {r["push"] for r in pushes if r["event"] == "receipt"}]
    metrics = REPO / "logs" / "client_metrics.jsonl"
    out["client_metrics"] = [m for m in (json.loads(x) for x in metrics.read_text().splitlines()) if m["time"] >= since] if metrics.exists() else []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:6000])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    out = next((REPO / a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), OUT)  # e.g. the Muse run
    {"prepare": lambda: prepare("--signed-out" in sys.argv), "restore": restore, "report": lambda: report(out)}[cmd]()
