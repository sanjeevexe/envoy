"""Put the Instagram scene (docs/demo-creator-workflow.md) in a take's starting state, in one command.

  uv run --project backend python scripts/instagram_take.py --routine off   # take 1: the agent's first run
  uv run --project backend python scripts/instagram_take.py --routine on    # take 2: from the learned routine
  uv run --project backend python scripts/instagram_take.py --check         # say how things stand, change nothing

  --api-dir <the API's data dir> [--api http://127.0.0.1:<port>]   also tidy that API: its outbox (from its setting), its
      pending handoff offers ("not now"), and the phone's name in its offers (--phone-name, default "Envoy's phone").
      Without it: the outbox is --outbox, else $ENVOY_OUTBOX, else ~/Envoy Outbox, and the API is left alone.

Run it from the checkout whose API films the take: the routine is switched in that checkout's library (data/routines),
which the API reads on every run. In order:

1. **The outbox**: anything in it is moved to "<outbox> before <time>" beside it (never deleted), so the take's clip is
   the only file and the only offer.
2. **The routine** `instagram_post_reel` on or off (`RoutineStore.switch`: off leaves the offer to the agent; its versions
   and runs stay).
3. **The phone** (the one connected over USB; claim it first, coord/devices.sh): awake and unlocked, Instagram signed in
   to the test account (`--account`, read from Home's story tray), and its composer reset: Instagram is restarted (as a
   run starts it), Create is opened and whatever comes (the camera, "Keep editing your draft?", the editor, the caption
   screen) is left without posting, until Create opens the gallery ("New reel") right after a restart twice in a row;
   then back to Home. "Keep editing your draft?" gets "Start new video", which keeps the half-made reel as a private
   draft (nothing else clears it across a restart). The script taps only the buttons named in TAPS below, never Share,
   Next, Post, Save draft, Follow or Like.
4. **The phone's app names** read once for the agent (`data/apps/labels.json` in this checkout: the planner lists the
   phone's apps by name). The first agent run in a checkout otherwise spends ~55 s pulling each app's APK for its label
   (measured Oct 30 on the Pixel); after that it's ~1 s.
5. A summary: what an offer will say, the routine, what Create opens, and the drafts count (rehearsal drafts are deleted
   by hand: Create › Drafts › ⋯ › Delete).

Exit 0 when every check holds, 1 otherwise (it says which).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from devices.screen import build_state, mask_passwords  # noqa: E402
from devices.types import Action, ScreenState  # noqa: E402

IG = "com.instagram.android"
ROUTINE = "instagram_post_reel"
PERMISSIONS = "com.google.android.permissioncontroller"
# The only buttons this script taps, by Instagram 453's resource id (and label where one id has several). Nothing here
# publishes, saves a draft, follows or messages; "Start over" discards the reel being made (Save draft keeps it).
TAPS = {
    "create": ("action_bar_left_button", None),  # Home's top-left Create
    "home_tab": ("feed_tab", None),
    "gallery_home": ("gallery_cancel_button", "Back to Home"),
    "camera_gallery": ("gallery_preview_button", "Gallery"),
    "editor_cancel": ("cancel_button", "Cancel"),
    "start_over": ("igds_alert_dialog_primary_button", "Start over"),
    "keep_editing": ("primary_button", "Keep editing"),  # "Keep editing your draft?": back into the editor, then Start over
    "start_new": ("auxiliary_button", "Start new video"),  # the same question: keeps the half-made reel as a private draft
    "close": ("close_button", None),  # a pop-up's close (the "Brand survey" on opening)
}
NEVER = re.compile(r"share|post|publish|next|save draft|follow|like|send|message|comment|reply|story|live", re.I)


# ---- the phone -----------------------------------------------------------------------------------------


def connect() -> Any:
    from devices.android import AndroidDevice
    from devices.phone import discover
    phones = [p for p in discover() if p["state"] == "device"]
    if len(phones) != 1:
        sys.exit(f"expected one connected phone, found {[(p['model'], p['state']) for p in discover()]}")
    return AndroidDevice(phones[0]["serial"]).connect()


def look(dev: Any) -> ScreenState:
    pkg, act, secure = dev._foreground()
    state = build_state(mask_passwords(dev._dump()), pkg, act, dev.capabilities.width, dev.capabilities.height, secure=secure)
    dev._last = state  # element numbers in actions refer to this screen
    return state


def ids(state: ScreenState) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for e in state.numbered:
        out.setdefault(e.resource_id.split("/")[-1], []).append(e)
    return out


def words(state: ScreenState) -> str:
    return " ".join(" ".join(x for x in (e.label, e.text, e.desc) if x) for e in state.numbered)


def screen(state: ScreenState) -> str:
    """Which of Instagram's screens this is: home, gallery, camera, editor, caption, save_draft, keep_editing, drafts,
    other_tab, popup, permission, elsewhere or unknown."""
    if state.package == PERMISSIONS:
        return "permission"
    if state.package != IG:
        return "elsewhere"
    have, text = ids(state), words(state)
    if "igds_alert_dialog_primary_button" in have and re.search(r"\bSave draft\?", text):
        return "save_draft"
    if re.search(r"Keep editing your draft\?", text):
        return "keep_editing"
    if "gallery_drafts_list_item_container" in have or "Reels drafts" in text:
        return "drafts"
    if "gallery_title_container" in have:
        return "gallery"
    if "camera_shutter_button" in have or "camera_home_button" in have:
        return "camera"
    if "clips_right_action_button" in have and "cancel_button" in have:
        return "editor"
    if "caption_input_text_view" in have or "share_button" in have:
        return "caption"
    if "feed_tab" in have and "action_bar_left_button" in have and "swipeable_tab_view_pager" in have:
        return "home"
    if "feed_tab" in have:
        return "other_tab"
    if "close_button" in have:
        return "popup"
    return "unknown"


def tap(dev: Any, state: ScreenState, name: str) -> str:
    rid, label = TAPS[name]
    el = next((e for e in ids(state).get(rid, []) if label is None or (e.label or e.desc or e.text or "").strip() == label), None)
    if el is None:
        raise LookupError(f"no {name} ({rid}) on this screen")
    said = " ".join(x for x in (el.label, el.text, el.desc) if x)
    if NEVER.search(said) and name != "home_tab":  # belt and braces: the ids above never carry these words
        raise RuntimeError(f"refused to tap {said!r}")
    got = dev._act_sync(Action(kind="tap", element=el.number))
    if not got.ok:
        raise RuntimeError(f"tap {name}: {got.error}")
    return name


def account(state: ScreenState) -> str | None:
    """The signed-in account, from Home's story tray: the first avatar reads "<account>'s story, 0 of N"."""
    for e in state.numbered:
        m = re.fullmatch(r"(.+)'s story, 0 of \d+.*", (e.label or e.desc or e.text or "").strip())
        if m:
            return m.group(1)
    return None


def drafts(state: ScreenState) -> int | None:
    for e in ids(state).get("gallery_destination_item", []):
        m = re.fullmatch(r"Drafts(?: · (\d+))?", (e.label or "").strip())
        if m:
            return int(m.group(1) or 0)
    return None


def awake(dev: Any) -> str | None:
    """Why the phone isn't ready for a take (asleep, locked), or None."""
    power = dev.adb.shell("dumpsys power | grep -E 'mWakefulness='")
    if "Awake" not in power:
        return "the screen is off: wake the phone"
    locked = dev.adb.shell("dumpsys window | grep -E 'mDreamingLockscreen=|isStatusBarKeyguard|mShowingLockscreen='")
    if re.search(r"(mDreamingLockscreen|mShowingLockscreen)=true|isStatusBarKeyguard=true", locked):
        return "the phone is locked: unlock it"
    return None


def leave_composer(dev: Any, max_steps: int = 14, wait_s: float = 1.3) -> list[str]:
    """From anywhere in Instagram's composer back to Home, keeping nothing: the caption screen goes Back to the editor,
    the editor's Cancel asks "Save draft?" and gets Start over, "Keep editing your draft?" (shown a few seconds after a
    restart when a reel was being made) gets Keep editing and then the same, the gallery and camera go Back to Home. A
    permission dialog is dismissed with Back, never answered. Used after a rehearsal too (eval/run_creator.py)."""
    done: list[str] = []
    for _ in range(max_steps):
        state = look(dev)
        kind = screen(state)
        if kind == "home":
            return done
        if kind == "elsewhere":
            done.append(f"left Instagram ({state.package})")
            return done
        try:
            if kind == "save_draft":
                done.append(tap(dev, state, "start_over"))
            elif kind == "keep_editing":  # its other button, "Start new video", saves the draft
                done.append(tap(dev, state, "keep_editing"))
            elif kind == "editor":
                done.append(tap(dev, state, "editor_cancel"))
            elif kind == "gallery":
                done.append(tap(dev, state, "gallery_home"))
            elif kind == "camera":
                done.append(tap(dev, state, "camera_gallery"))
            elif kind == "other_tab":
                done.append(tap(dev, state, "home_tab"))
            elif kind == "popup":
                done.append(tap(dev, state, "close"))
            else:  # the caption screen, Drafts, "Keep editing your draft?", a permission dialog, anything else: Back
                dev._act_sync(Action(kind="back"))
                done.append(f"back ({kind})")
        except LookupError:
            dev._act_sync(Action(kind="back"))
            done.append(f"back ({kind}, button not found)")
        time.sleep(wait_s)
    done.append(f"stopped after {max_steps} steps on {screen(look(dev))}")
    return done


def restart(dev: Any, wait_s: float = 6) -> None:
    """Instagram force-stopped and opened again, as every run starts it (the agent's and a routine's fresh launch)."""
    dev.adb.shell(f"am force-stop {IG}")
    dev._act_sync(Action(kind="launch", package=IG))
    time.sleep(wait_s)


def reset_instagram(dev: Any, account_name: str | None, rounds: int = 2) -> dict[str, Any]:
    """Create opens the gallery right after a restart, `rounds` restarts in a row. A reel left half-made (any visit to
    the editor, even one that ended with Start over) comes back after a restart as "Keep editing your draft?"; the one
    answer that clears it for good is "Start new video", which keeps it as a private draft (measured Oct 30 on
    Instagram 453: Keep editing, Cancel, Start over brings it back at the next restart). The drafts count is reported;
    deleting drafts is left to you (Create › Drafts › ⋯ › Delete)."""
    log: list[str] = []
    restart(dev)
    log += leave_composer(dev)
    state = look(dev)
    if screen(state) != "home":
        return {"ok": False, "why": f"Instagram isn't on Home ({screen(state)})", "log": log}
    who = account(state)
    if account_name and who != account_name:
        return {"ok": False, "why": f"Instagram is signed in as {who!r}, not {account_name!r}: nothing more was touched", "log": log}
    in_a_row, opened, count = 0, [], None
    for n in range(rounds + 3):
        if n:
            restart(dev)
            log.append("restart")
        log += leave_composer(dev)  # a pop-up Instagram raised by itself
        log.append(tap(dev, look(dev), "create"))
        time.sleep(2.5)
        state = look(dev)
        kind = screen(state)
        opened.append(kind)
        if kind == "gallery":
            count = drafts(state)
            in_a_row += 1
        else:
            in_a_row = 0
            if kind == "keep_editing":
                log.append(tap(dev, state, "start_new"))
                time.sleep(2.5)
        log += leave_composer(dev)
        if in_a_row >= rounds:
            break
    ok = in_a_row >= rounds and screen(look(dev)) == "home"
    return {"ok": ok, "why": None if ok else f"Create opened {opened}", "account": who, "create_opened": opened,
            "drafts": count, "log": log}


# ---- the API, the outbox and the routine ---------------------------------------------------------------


class Api:
    def __init__(self, base: str, api_dir: Path) -> None:
        import httpx
        token = (api_dir / "session_token").read_text().strip()
        self.http = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=20)

    def get(self, path: str, **params: Any) -> Any:
        r = self.http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict[str, Any]) -> Any:
        r = self.http.post(path, json=body)
        r.raise_for_status()
        return r.json()


def clear_outbox(outbox: Path, dry: bool) -> dict[str, Any]:
    """Everything in the outbox moved to "<outbox> before <time>" beside it. Hidden files stay (the watcher ignores them)."""
    if not outbox.is_dir():
        return {"outbox": str(outbox), "moved": [], "note": "no such folder"}
    stale = sorted(p for p in outbox.iterdir() if not p.name.startswith("."))
    if not stale or dry:
        return {"outbox": str(outbox), "moved": [], "waiting": [p.name for p in stale]}
    dest = outbox.with_name(f"{outbox.name} before {datetime.now():%Y-%m-%d %H%M%S}")
    dest.mkdir()
    for p in stale:
        p.rename(dest / p.name)
    return {"outbox": str(outbox), "moved": [p.name for p in stale], "to": str(dest)}


def switch_routine(on: bool | None, library: Path) -> dict[str, Any]:
    from routines.store import RoutineStore
    lib = RoutineStore(library)
    if on is not None:
        lib.switch(ROUTINE, on)
    idx = lib.index(ROUTINE)
    return {"routine": ROUTINE, "active": idx.get("active"), "off": idx.get("off"), "library": str(library)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--routine", choices=["on", "off"], help="instagram_post_reel on (take 2) or off (take 1); left as it is if not given")
    ap.add_argument("--check", action="store_true", help="say how things stand; move, switch and tap nothing")
    ap.add_argument("--api", default=None, help="the API's address (default http://127.0.0.1:$ENVOY_PORT or :8700)")
    ap.add_argument("--api-dir", default=os.environ.get("ENVOY_API_DIR") or "", help="the API's data dir (its session_token)")
    ap.add_argument("--outbox", default=None, help="without --api-dir: the outbox folder")
    ap.add_argument("--phone-name", default="Envoy's phone", help="with --api-dir: what offers call the phone ('' leaves it)")
    ap.add_argument("--account", default="envoy3955", help="the Instagram account a take must be signed in to")
    ap.add_argument("--library", default=str(REPO / "data" / "routines"))
    ap.add_argument("--no-phone", action="store_true", help="leave the phone alone")
    args = ap.parse_args()
    t0 = time.time()
    out: dict[str, Any] = {"time": datetime.now().isoformat(timespec="seconds")}
    problems: list[str] = []

    api = None
    if args.api_dir:
        api = Api(args.api or f"http://127.0.0.1:{os.environ.get('ENVOY_PORT', '8700')}", Path(args.api_dir))
        outbox = Path(api.get("/api/settings/handoff")["outbox"])
    else:
        outbox = Path(args.outbox or os.environ.get("ENVOY_OUTBOX") or Path.home() / "Envoy Outbox")
    out["outbox"] = clear_outbox(outbox, args.check)
    if out["outbox"].get("waiting"):
        problems.append(f"the outbox isn't empty: {out['outbox']['waiting']}")

    if api is not None:
        pending = [o for o in api.get("/api/offers", status="pending") if o.get("kind") == "handoff"]
        if not args.check:
            for o in pending:
                api.post(f"/api/offers/{o['id']}", {"decision": "decline"})
        out["handoff_offers_declined"] = [o["title"] for o in pending] if not args.check else []
        if args.check and pending:
            problems.append(f"{len(pending)} handoff offer(s) still pending")
        phones = [p for p in api.get("/api/settings/phones")["phones"] if p.get("state") == "device"]
        if args.phone_name and not args.check:
            for p in phones:
                if p.get("name") != args.phone_name:
                    try:
                        api.post("/api/settings/phones/name", {"id": p["avd"], "name": args.phone_name})
                    except Exception as e:  # noqa: BLE001 - an API from before the name setting
                        problems.append(f"couldn't name the phone ({e}); offers will say 'your {p.get('model') or p.get('name')}'")
            phones = [p for p in api.get("/api/settings/phones")["phones"] if p.get("state") == "device"]
        out["phones"] = [{"id": p["avd"], "name": p.get("name"), "model": p.get("model")} for p in phones]
        if args.phone_name and not any(p.get("name") == args.phone_name for p in phones):
            problems.append(f"no connected phone is named {args.phone_name!r} in that API")

    on = None if args.check or args.routine is None else args.routine == "on"
    out["routine"] = switch_routine(on, Path(args.library))
    if args.routine and (out["routine"]["active"] is not None) != (args.routine == "on"):
        problems.append(f"the routine is {'on' if out['routine']['active'] else 'off'}, not {args.routine}")

    if not args.no_phone:
        dev = connect()
        why = awake(dev)
        if why:
            problems.append(why)
        elif args.check:
            state = look(dev)
            out["phone"] = {"foreground": state.package, "screen": screen(state), "account": account(state)}
            if out["phone"]["screen"] != "home":
                problems.append(f"Instagram isn't on Home ({out['phone']['screen']})")
        else:
            out["phone"] = reset_instagram(dev, args.account or None)
            if not out["phone"]["ok"]:
                problems.append(out["phone"]["why"])
            t = time.time()
            apps = dev.apps()  # devices/apps.py: reads every launchable app's label once per version, cached for the API
            out["app_names"] = {"apps": len(apps.apps), "unread": sorted(apps.errors), "seconds": round(time.time() - t, 1)}

    out["seconds"] = round(time.time() - t0, 1)
    out["ok"] = not problems
    out["problems"] = problems
    print(json.dumps(out, indent=1, default=str))
    ph = out.get("phone") or {}
    print(f"\n{'READY' if not problems else 'NOT READY'} in {out['seconds']} s: outbox {'empty' if not out['outbox'].get('waiting') else 'NOT empty'}"
          f"; routine {ROUTINE} {'on (v' + str(out['routine']['active']) + ')' if out['routine']['active'] else 'off'}"
          + (f"; Instagram as {ph.get('account')}, Create opens {ph.get('create_opened')}, drafts {ph.get('drafts')}" if ph.get("create_opened") else "")
          + (f"; offers say {out['phones'][0]['name']!r}" if out.get("phones") else ""))
    for p in problems:
        print(f"  - {p}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
