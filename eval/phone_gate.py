"""The Phase 6 gate on the real Android phone: set up, then report what happened (asking first, the banner, the approval,
the check-in in SkyLark's own state, memory).

  uv run --project backend python eval/phone_gate.py prepare      # SkyLark on the phone, seeded, signed in; "always ask" for the run
  ... from the iPhone (or the web app): "Check me in for my flight on my phone"; allow the phone; approve the push ...
  uv run --project backend python eval/phone_gate.py report       # what happened, with timings → eval/results/phase6/phone_gate.json
  uv run --project backend python eval/phone_gate.py restore      # approval rules as they were

The person decides everything on the iPhone; this only prepares the test app on the phone and reads the record. The
routine is the one the API's library holds (compiled on envoy-test). The session token is read here and never printed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "backend"))
from demo_setup import demo_fixtures  # noqa: E402
from devices.phone import discover  # noqa: E402
from testapps.skylark import SkyLark  # noqa: E402

BASE = "http://127.0.0.1:8700"
H = {"Authorization": f"Bearer {(REPO / 'data' / 'api' / 'session_token').read_text().strip()}"}
STATE = REPO / "data" / "api" / "phone_gate.json"
OUT = REPO / "eval" / "results" / "phase6" / "phone_gate.json"


def phone() -> dict:
    phones = [p for p in discover() if p["state"] == "device"]
    if not phones:
        raise SystemExit("no Android phone connected: plug it in, unlock it, and tap Allow on 'Allow USB debugging?'")
    return phones[0]


def props(serial: str) -> dict[str, str]:
    get = lambda k: subprocess.run(["adb", "-s", serial, "shell", "getprop", k], capture_output=True, text=True).stdout.strip()  # noqa: E731
    return {"model": get("ro.product.model"), "manufacturer": get("ro.product.manufacturer"), "android": get("ro.build.version.release"),
            "sdk": get("ro.build.version.sdk"), "skin": get("ro.build.version.oneui") or get("ro.miui.ui.version.name") or "",
            "sim": get("gsm.sim.state"), "security_patch": get("ro.build.version.security_patch")}


def prepare() -> None:
    p = phone()
    app = SkyLark(p["serial"])
    if not app.installed():
        app.install()
    app.prepare(fixtures=demo_fixtures(signed_in=True), variant=0)
    rules = httpx.get(f"{BASE}/api/settings/approvals", headers=H).json()["rules"]
    saved = json.loads(STATE.read_text()) if STATE.exists() else {"rules": rules}
    STATE.write_text(json.dumps({**saved, "since": time.time(), "phone": p, "props": props(p["serial"])}))
    httpx.post(f"{BASE}/api/settings/approvals", json={**rules, "default": "always", "apps": {}, "routines": {}}, headers=H)
    print(f"{p['id']} ({props(p['serial'])['model']}, Android {props(p['serial'])['android']}): SkyLark seeded and signed in, Chicago not "
          "checked in; approvals: always ask for this run. Now ask Envoy: \"Check me in for my flight on my phone\".")


def restore() -> None:
    if STATE.exists():
        httpx.post(f"{BASE}/api/settings/approvals", json=json.loads(STATE.read_text())["rules"], headers=H)
        STATE.unlink()
    print("approval rules restored")


def report() -> None:
    st = json.loads(STATE.read_text()) if STATE.exists() else {"since": time.time() - 3600}
    since = st["since"]
    p = st.get("phone") or phone()
    tasks = [t for t in httpx.get(f"{BASE}/api/tasks", params={"limit": 20}, headers=H).json() if t["created_at"] >= since]
    out: dict = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "phone": {**p, **(st.get("props") or props(p["serial"]))}, "tasks": []}
    for t in reversed(tasks):
        d = httpx.get(f"{BASE}/api/tasks/{t['id']}", headers=H).json()
        approvals = [{k: a.get(k) for k in ("id", "status", "decided_by", "created_at", "decided_at", "description")} for a in d["approvals"]]
        for a in approvals:
            a["decided_after_s"] = round(a["decided_at"] - a["created_at"], 1) if a.get("decided_at") else None
        out["tasks"].append({"goal": t["goal"], "source": t["source"], "status": t["status"], "device": t.get("device"), "kind": t.get("kind"),
                             "routine": t.get("routine"), "result": t.get("result"), "approvals": approvals,
                             "notes": [s.get("text") for s in d["steps"] if s.get("kind") == "note"][:20],
                             "memory": next((s["text"] for s in d["steps"] if s.get("kind") == "memory"), None),
                             "duration_s": round(t["updated_at"] - t["created_at"], 1)})
    state = SkyLark(p["serial"]).state()
    out["skylark_on_phone"] = {"checked_in": {t["code"]: t["checked_in"] for t in state["trips"] if t["upcoming"]}}
    pushes = REPO / "logs" / "push.jsonl"
    out["pushes"] = [x for x in (json.loads(line) for line in pushes.read_text().splitlines()) if x["time"] >= since] if pushes.exists() else []
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str)[:6000])


if __name__ == "__main__":
    {"prepare": prepare, "restore": restore, "report": report}[sys.argv[1] if len(sys.argv) > 1 else "report"]()
