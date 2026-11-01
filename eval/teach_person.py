"""A scripted person for teach mode (backend/api/teach.py): starts a teach session on a test API copy, does the task
through the live view's WebSocket exactly as the web app sends it (taps as screen fractions, typing key by key), says it
worked, and follows the compile and the replay to the end.

The person's eyes read the phone only through build_state (devices/screen.py), between steps, to find where to tap;
everything else goes through the API like a person's input.

  ENVOY_API_DIR=<copy's dir> uv run --project backend python eval/teach_person.py skylark_status --api http://127.0.0.1:8752
  ... eval/teach_person.py list
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

import httpx  # noqa: E402
import websockets  # noqa: E402

from devices.emulator import EmulatorDevice  # noqa: E402
from routines.screens import norm  # noqa: E402

# Each demonstration: the goal in the user's words, the app, the answer (question goals), and the steps:
#   ("tap", {"id": "...", "text": "...", "label": "...", "re": "...", "desc": "..."})   the element the person looks for: the
#       first on screen whose id is `id`, label contains `text`, label is exactly `label`, label matches `re`
#   ("type", "text")   key by key, as the web app's keyboard sends it     ("key", "Enter" | "Back" | "Backspace")
#   ("swipe", (x1, y1, x2, y2))   fractions                               ("wait", seconds)
#   ("swipe_until", ((x1, y1, x2, y2), {finder}, most))   slow drags until that element shows above the bottom 15%
DEMOS: dict[str, dict[str, Any]] = {
    "skylark_status": {
        "device": "envoy-test", "app": "com.skylark.air", "goal": "What's the status of flight SL 1190?", "answer": "Delayed 25 min",
        "steps": [("tap", {"id": "nav_status"}), ("tap", {"id": "field_flight_number"}), ("type", "SL 1190"), ("tap", {"id": "btn_search_status"}),
                  ("wait", 1.0)],
    },
    # A real app the agent never learned to write to (loops ran Calendar read-only): the test Google account's Calendar.
    # Tomorrow is Nov 1 here, so the date picker goes to the next month. The event is deleted afterwards, in the app.
    "calendar_add": {
        "device": "envoy-real", "app": "com.google.android.calendar", "goal": "Add a Calendar event called Dentist tomorrow at 3pm",
        "steps": [("tap", {"label": "Creation menu"}), ("tap", {"label": "Event"}), ("type", "Dentist"),
                  ("tap", {"re": r"^[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}, \d{4}$"}), ("tap", {"label": "Change to next month"}),
                  ("tap", {"label": "1"}), ("tap", {"id": "confirm_button"}), ("tap", {"re": r"^\d{1,2}:\d{2} [AP]M$"}),
                  ("tap", {"label": "3"}), ("tap", {"id": "material_timepicker_ok_button"}), ("tap", {"id": "save"}), ("wait", 1.5)],
    },
    # The same without the date picker, whose OK (id confirm_button) the risk rules flag, so its replay asks you first.
    "calendar_add_today": {
        "device": "envoy-real", "app": "com.google.android.calendar", "goal": "Add a Calendar event called Dentist today at 6pm",
        "steps": [("tap", {"label": "Creation menu"}), ("tap", {"label": "Event"}), ("type", "Dentist"),
                  ("tap", {"re": r"^\d{1,2}:\d{2} [AP]M$"}), ("tap", {"label": "6"}), ("tap", {"id": "material_timepicker_ok_button"}),
                  ("tap", {"id": "save"}), ("wait", 1.5)],
    },
    # Teach trials (Nov 1, eval/results/teach_trials_2026-11-01): Loop B's tasks, whose agent runs are the comparison.
    # Wikipedia's routine from an agent run read its answer after one article's own wording and isn't in the library.
    "wikipedia_opened": {
        "device": "envoy-real", "app": "org.wikipedia", "goal": "In the Wikipedia app, what year did the Golden Gate Bridge open?",
        "answer": "1937",
        "steps": [("tap", {"id": "nav_tab_search"}), ("tap", {"id": "search_card"}), ("type", "Golden Gate Bridge"),
                  ("tap", {"re": r"^Golden Gate Bridge · Bridge"}), ("wait", 2.5),
                  ("swipe", (0.5, 0.75, 0.5, 0.45)), ("wait", 1.5)],  # the year is just below the lead's first paragraph
    },
    # The same, answered with the date the sentence gives: the compiler then anchors the read on that sentence's own words.
    "wikipedia_opened_date": {
        "device": "envoy-real", "app": "org.wikipedia", "goal": "In the Wikipedia app, what year did the Golden Gate Bridge open?",
        "answer": "May 27, 1937",
        "steps": [("tap", {"id": "nav_tab_search"}), ("tap", {"id": "search_card"}), ("type", "Golden Gate Bridge"),
                  ("tap", {"re": r"^Golden Gate Bridge · Bridge"}), ("wait", 4.0),  # the header image loads, and the text moves
                  # The app reopens an article where you last left it: up to the top first, then down to the sentence.
                  *[("swipe", (0.5, 0.3, 0.5, 0.9))] * 4, ("wait", 1.0),
                  ("swipe_until", ((0.5, 0.65, 0.5, 0.5), {"text": "opened to the public on"}, 8)), ("wait", 1.5)],
    },
    "skylark_gate": {
        "device": "envoy-test", "app": "com.skylark.air", "goal": "What gate is my Chicago flight at?", "answer": "B12",
        "steps": [("tap", {"id": "card_next_trip"}), ("wait", 0.8)],
    },
}


def find(screen: Any, want: dict[str, str]) -> Any:
    for e in screen.numbered:
        if want.get("id") and e.resource_id.split("/")[-1] != want["id"]:
            continue
        if want.get("text") and norm(want["text"]) not in norm(e.label):
            continue
        if want.get("label") and norm(want["label"]) != norm(e.label):
            continue
        if want.get("re") and not re.match(want["re"], e.label):
            continue
        if want.get("desc") and norm(want["desc"]) not in norm(e.desc):
            continue
        return e
    raise LookupError(f"not on screen: {want} ({screen.package})")


async def demonstrate(name: str, api: str, token: str, eyes_wait: float) -> dict[str, Any]:
    demo = DEMOS[name]
    avd = demo["device"]
    hdr = {"Authorization": f"Bearer {token}", "X-Envoy": "1"}
    eyes = EmulatorDevice(avd).connect()
    w, h = eyes.capabilities.width, eyes.capabilities.height
    async with httpx.AsyncClient(base_url=api, headers=hdr, timeout=60) as c:
        r = await c.post("/api/teach/start", json={"device": avd, "goal": demo["goal"], "app": demo.get("app")})
        r.raise_for_status()
        print("start:", {k: r.json().get(k) for k in ("id", "status", "recording")})
        ws_url = api.replace("http", "ws", 1) + f"/api/live/{avd}?fps=6&width=360&quality=50"
        t0 = time.time()
        async with websockets.connect(ws_url, additional_headers={"Authorization": f"Bearer {token}"}, max_size=None) as ws:
            async def drain() -> None:  # frames and control messages; the last control says what the live view shows
                async for m in ws:
                    if isinstance(m, str) and json.loads(m).get("type") == "control":
                        teach = (json.loads(m).get("control") or {}).get("teach") or {}
                        print(f"  live view: recording={teach.get('recording')} steps={teach.get('steps')} {teach.get('why') or ''}".rstrip())
            reader = asyncio.create_task(drain())
            await asyncio.sleep(1.0)
            for kind, arg in demo["steps"]:
                if kind == "tap":
                    screen = await eyes.observe()
                    e = find(screen, arg)
                    x, y = e.center
                    await ws.send(json.dumps({"type": "tap", "x": x / w, "y": y / h, "id": 1}))
                    print(f"  tap {e.label or e.resource_id!r}")
                elif kind == "type":
                    for ch in arg:
                        await ws.send(json.dumps({"type": "text", "text": ch}))
                        await asyncio.sleep(0.12)
                    print(f"  typed {arg!r}")
                elif kind == "key":
                    await ws.send(json.dumps({"type": "key", "key": arg}))
                    print(f"  key {arg}")
                elif kind == "swipe":
                    x1, y1, x2, y2 = arg
                    await ws.send(json.dumps({"type": "swipe", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "ms": 350}))
                    print(f"  swipe {arg}")
                elif kind == "swipe_until":
                    (x1, y1, x2, y2), want, most = arg
                    for _ in range(most):
                        try:
                            seen = find(await eyes.observe(), want).center[1]
                        except LookupError:
                            seen = None
                        if seen is not None and seen < 0.85 * h:
                            break
                        await ws.send(json.dumps({"type": "swipe", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "ms": 1200}))  # a slow drag: no fling
                        print(f"  swipe {arg[0]} looking for {want} (seen at y={seen})")
                        await asyncio.sleep(eyes_wait + 0.8)
                    else:
                        raise LookupError(f"not found after {most} swipes: {want}")
                elif kind == "wait":
                    await asyncio.sleep(arg)
                await asyncio.sleep(eyes_wait)
            await asyncio.sleep(1.0)
            reader.cancel()
        shown_s = round(time.time() - t0, 1)
        r = await c.post("/api/teach/finish", json={"device": avd, "ok": True, "answer": demo.get("answer") or ""})
        r.raise_for_status()
        print("finish:", r.json()["status"], "-", r.json()["detail"])
        while True:
            s = (await c.get(f"/api/teach/{avd}")).json()
            if s["status"] not in ("compiling", "replaying", "recording"):
                break
            await asyncio.sleep(2)
        s["shown_s"] = shown_s
        return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("demo", choices=[*DEMOS, "list"])
    ap.add_argument("--api", default="http://127.0.0.1:8752")
    ap.add_argument("--eyes-wait", type=float, default=1.2, help="seconds the person waits between steps")
    args = ap.parse_args()
    if args.demo == "list":
        for k, d in DEMOS.items():
            print(f"{k}: {d['goal']} ({d['device']})")
        return 0
    api_dir = os.environ.get("ENVOY_API_DIR")
    if not api_dir:
        print("set ENVOY_API_DIR to the test copy's folder (its own session token; never the live API's)", file=sys.stderr)
        return 2
    token = (Path(api_dir) / "session_token").read_text().strip()
    out = asyncio.run(demonstrate(args.demo, args.api, token, args.eyes_wait))
    print(json.dumps({k: out.get(k) for k in ("id", "status", "detail", "routine", "version", "steps", "shown_s", "cost_usd", "notes",
                                                "warnings", "dropped", "replay_task")}, indent=1))
    print(json.dumps(out.get("replay"), indent=1))
    return 0 if out.get("status") == "saved" else 1


if __name__ == "__main__":
    sys.exit(main())
