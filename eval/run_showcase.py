"""showcase (T1c): one clip posted from Envoy's phone to Instagram, TikTok and YouTube Shorts, each with a feature only the
app has, each a learned routine an agent can call (prompts/phone-layer-plan.md §5 "showcase").

Stage 0 (P3) looks before anything is compiled, with no model calls. Claim the phone first
(`~/Desktop/Envoy/coord/devices.sh claim pixel5 showcase 60 <purpose>`):

  uv run --project backend python eval/run_showcase.py facts                 the phone, the three apps' versions, what's in front
  uv run --project backend python eval/run_showcase.py open tiktok [--fresh]   launch an app (--fresh: force-stop it first)
  uv run --project backend python eval/run_showcase.py look <label>          save the screen under eval/results/showcase/recon/
  uv run --project backend python eval/run_showcase.py tap "<query>"         tap the element whose label, text, description or
                                                                             id is exactly <query> (or "#12")
  uv run --project backend python eval/run_showcase.py type "<query>" "<text>"   type into a field (never presses Enter)
  uv run --project backend python eval/run_showcase.py swipe up|down|left|right  scroll the screen (a picker, a list)
  uv run --project backend python eval/run_showcase.py key back|home
  uv run --project backend python eval/run_showcase.py push <clip>           a clip into the phone's gallery (no offer, no post)
  uv run --project backend python eval/run_showcase.py gate <dump.xml> --app tiktok   the Post gate on a recorded screen
  uv run --project backend python eval/run_showcase.py keep <stem>           copy a screenshot you checked into the repo
  uv run --project backend python eval/run_showcase.py leave <app>           out of the app's composer, posting and saving nothing

`tap` never taps a target the risk rules call irreversible (policy/risk.py), and a target with a publishing word anywhere
in it ("Post", "Upload", "Your story", a "Create post" tab) needs `--not-final`, said on purpose each time and never for the
button that publishes.

Screenshots can show personal data (a feed, a camera pointed at the room), so `look` saves the masked dump and its text in
the repo but the PNG outside it (`$SHOWCASE_SHOTS`, default ~/Library/Caches/envoy-showcase), and none at all while a
camera viewfinder is open; `keep` copies one into the repo after you've looked at it.

Stage 1 runs on this session's API copy (127.0.0.1:8764: its own data dir, session token and outbox; never :8700):

  uv run --project backend python eval/run_showcase.py first --app tiktok --goal "…" --api-dir <copy's data dir>
      The agent's first run on Envoy's phone (the copy's session says yes to using the phone), until the post is asked;
      the post and any other approval are declined here. Nothing is posted.
  uv run --project backend python eval/run_showcase.py compile <trace> --name tiktok_post_sound [--final-from-declined]
      Wonder compiles the declined first run under a new name (eval/results/showcase/routine/). A declined tap never ran,
      so the compiler drops it; --final-from-declined adds it back as the routine's last step, irreversible, built from
      the recorded screen it was declined on (said in the routine's `changes`).
  uv run --project backend python eval/run_showcase.py add-routine <yaml>   into this checkout's library, only if its post
      step is irreversible and every input is typed from an input
  uv run --project backend python eval/run_showcase.py replay --routine tiktok_post_sound --input caption="…" --api-dir <…>
      The routine on the copy, declined at the post. Calls, seconds and dollars go to eval/results/showcase/runs/.

Results: eval/results/showcase/recon/ (stage 0), runs/<app>-<mode>-<time>.json plus runs.md, routine/ (stage 1).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "eval"))

from devices.screen import build_state  # noqa: E402
from devices.types import Action, ScreenState  # noqa: E402
from policy.approval_rules import ApprovalRules, decide  # noqa: E402
from policy.risk import classify  # noqa: E402
from run_creator import PAUSED, Copy, connect, ended, find, observe, push, spent, tap, type_into  # noqa: E402

OUT = REPO / "eval" / "results" / "showcase"
RECON = OUT / "recon"
RUNS = OUT / "runs"
ROUTINES = OUT / "routine"
SHOTS = Path(os.environ.get("SHOWCASE_SHOTS") or Path.home() / "Library" / "Caches" / "envoy-showcase")
API = "http://127.0.0.1:8764"
APPS = {"instagram": "com.instagram.android", "tiktok": "com.zhiliaoapp.musically", "youtube": "com.google.android.youtube"}
NAMES = {"com.instagram.android": "Instagram", "com.zhiliaoapp.musically": "TikTok", "com.google.android.youtube": "YouTube"}
PIXEL5 = (1080, 2340)
# The button that publishes, by its whole label: Instagram's Share (its reel's share_button may read only "Next"), its
# Story's "Your story" and "Close Friends", TikTok's Post, YouTube's "Upload Short". The gate below checks each one is irreversible by rule.
PUBLISH_LABEL = re.compile(r"(share|post|publish|upload)( (now|it|post|reel|short|video|story|to (your )?(feed|story)))?|your story|"
                           r"share to (your )?story|close friends", re.I)
PUBLISH_IDS = ("share_button",)
# Labelled like a publishing button, but not one: Instagram's "Your story" bubble in Home's tray only opens the Story
# camera (the coordinator's rule in cd168d6 leaves it a plain tap).
NOT_PUBLISH_IDS = ("outer_container",)
# An approval that is the post itself (its description names the target, its reasons the rule that flagged it).
POST_WORDS = re.compile(r"publishes|\b(share|post|upload)\b|share_button|your story|close friends", re.I)
# A camera viewfinder is open: no screenshot (it would show the room). By the camera's own controls.
CAMERA = re.compile(r"^(flip|flip camera|switch camera|record|record video|capture|take (a )?photo|shutter|camera)$", re.I)
# What `leave` may answer on its way out of a composer: things that throw away the unposted edit, nothing that keeps or
# publishes it. Everything else gets Back.
LEAVE_OK = re.compile(r"^(discard|discard edits|discard video|discard changes|start over|keep editing|exit|leave|close|not now|cancel)$", re.I)
NEVER = re.compile(r"share|post|publish|upload|save|draft|next|follow|like|send|message|comment|reply|story|live|duet|stitch|remix", re.I)


# Never tapped by this script, whatever --not-final says: the post itself, and anything social (contract 6).
SOCIAL = re.compile(r"^(follow|follow back|like|subscribe|comment|add comment|send|send to|message|reply)\b", re.I)


def publishes(label: str | None, resource_id: str | None) -> bool:
    rid = (resource_id or "").split("/")[-1]
    return rid not in NOT_PUBLISH_IDS and (bool(PUBLISH_LABEL.fullmatch((label or "").strip())) or rid in PUBLISH_IDS)


# A feed video's share icon (TikTok: "Share video. 4,682 shares"): it opens the share sheet, where Duet is. Allowed only
# with --opens-sheet, said on purpose, and only on a feed (no Post or Upload on screen).
SHARE_SHEET = re.compile(r"^share video\b", re.I)


def safe_tap(dev: Any, query: str, nth: int, not_final: bool, opens_sheet: bool = False) -> None:
    """run_creator's tap (the risk rules, publishing words need --not-final), after this script's own refusals: a
    button that publishes (TikTok's Post, YouTube's Upload Short, Instagram's "Your story", which the shared word list
    doesn't name) and anything social are never tapped here, --not-final or not."""
    state, _ = observe(dev)
    el = find(state, query, nth)
    if opens_sheet:
        on_feed = not any(publishes(e.label, e.resource_id) or publishes(e.desc, None) for e in state.numbered)
        if not (any(SHARE_SHEET.match((x or "").strip()) for x in (el.label, el.desc)) and on_feed):
            sys.exit(f"REFUSED: --opens-sheet is only for a feed video's 'Share video…' icon, not #{el.number} {el.label!r}")
        tap(dev, query, nth, True)
        return
    for x in (el.label, el.desc):
        if publishes(x, el.resource_id) or SOCIAL.match((x or "").strip()):
            sys.exit(f"REFUSED: #{el.number} {x!r} ({el.resource_id}) publishes or is social: stage 0 stops before it. Nothing was tapped.")
    tap(dev, query, nth, not_final)


def is_post(approval: dict[str, Any]) -> bool:
    return bool(POST_WORDS.search(f"{approval.get('description') or ''} {approval.get('reasons') or ''}"))


def asked_at(approval: dict[str, Any]) -> str:
    """The button an approval was asked at, from its description ('tap "Post" in com.zhiliaoapp.musically')."""
    m = re.search(r'"([^"]*)"', approval.get("description") or "")
    return m.group(1) if m else (approval.get("description") or "?")


# The publishing buttons a run passes and the risk rule must catch first (the coordinator, Nov 1), as P3 recorded them
# (eval/results/showcase/p3.md): YouTube's upload (not reached yet: the label it will most likely have), TikTok's editor
# "Your Story" (one tap posts a TikTok Story, on the screen every TikTok flow passes), Instagram's Story "Your story"
# (caught by its id). main cd168d6 catches all three.
GATED = {"com.google.android.youtube": ("Upload Short", ""), "com.zhiliaoapp.musically": ("Your Story", "com.zhiliaoapp.musically:id/ts6")}
STORY = ("Your story", "com.instagram.android:id/your_story_share_shortcut_button")


def rule_gap(pkg: str, goal: str) -> str | None:
    """Why an agent run must wait: until policy/risk.py catches the app's publishing button by rule, a run would have
    only the model's label between it and a public post. Checked against the rule itself, on a one-button screen, so it
    lifts the moment the rule change lands."""
    label, rid = GATED.get(pkg) or (STORY if pkg == APPS["instagram"] and re.search(r"\bstor(y|ies)\b", goal, re.I) else (None, ""))
    if label is None:
        return None
    xml = ('<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0"><node index="0" text="" resource-id="" '
           f'class="android.widget.FrameLayout" package="{pkg}" content-desc="" clickable="false" enabled="true" bounds="[0,0][1080,2340]">'
           f'<node index="0" text="{label}" resource-id="{rid}" class="android.widget.Button" package="{pkg}" content-desc="" '
           'clickable="true" enabled="true" bounds="[700,2100][1040,2220]" /></node></hierarchy>')
    state = build_state(xml, pkg, "", *PIXEL5)
    button = next((e for e in state.numbered if e.label == label), None)
    if button is not None and classify(Action(kind="tap", element=button.number), state, None).irreversible:
        return None
    where = f"{NAMES[pkg]}{' Stories' if pkg == APPS['instagram'] else ''}"
    return f"{label!r} isn't irreversible by rule yet (policy/risk.py): no agent run on {where} until the coordinator's rule change lands"


def app_of(name: str) -> str:
    if name in APPS:
        return APPS[name]
    if name in APPS.values():
        return name
    sys.exit(f"unknown app {name!r} (one of {', '.join(APPS)})")


def camera_on(state: ScreenState) -> bool:
    return "camera" in (state.activity or "").lower() or any(
        CAMERA.match((x or "").strip()) for e in state.numbered for x in (e.label, e.desc))


# ---- stage 0: looking ----------------------------------------------------------------------------------


def facts(dev: Any) -> dict[str, Any]:
    apps = {}
    for name, pkg in APPS.items():
        info = dev.adb.shell(f"dumpsys package {pkg} | grep -E 'versionName|lastUpdateTime'")
        apps[name] = " ".join(info.split()) or "not installed"
    state, _ = observe(dev)
    return {"model": dev.model, "android": dev.android, "screen": [dev.capabilities.width, dev.capabilities.height], "apps": apps,
            "foreground": [state.package, state.activity], "secure": state.secure, "camera": camera_on(state),
            "time": datetime.now().isoformat(timespec="seconds")}


def save_look(dev: Any, label: str, private: bool = False) -> Path:
    """NN-label.xml (masked) and NN-label.txt (the agent's view) in the repo; NN-label.png in SHOTS, never on a secure
    screen or while a camera viewfinder is open. `private` (a feed: other people's names and captions): all three go
    to SHOTS, nothing to the repo."""
    where = SHOTS if private else RECON
    where.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(p.name[:2]) for d in (RECON, SHOTS) if d.exists() for p in d.glob("[0-9][0-9]-*")), default=0)
    stem = f"{n:02d}-{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')}"
    state, xml = observe(dev)
    (where / f"{stem}.xml").write_text(xml)
    cam = camera_on(state)
    head = (f"# {state.package}/{state.activity} secure={state.secure} camera={cam} "
            f"{datetime.now().isoformat(timespec='seconds')}\n")
    (where / f"{stem}.txt").write_text(head + state.compact + "\n")
    print(head + state.compact)
    shot = ""
    if not state.secure and not cam:
        SHOTS.mkdir(parents=True, exist_ok=True)
        (SHOTS / f"{stem}.png").write_bytes(dev.screencap_png())
        shot = f"; screenshot {SHOTS / (stem + '.png')} (outside the repo: `keep {stem}` after checking it)"
    saved = where / stem if private else (RECON / stem).relative_to(REPO)
    print(f"\nsaved {saved}.xml/.txt{shot}{' (camera open: no screenshot)' if cam else ''}{' (private: not in the repo)' if private else ''}")
    return where / stem


def keep(stem: str) -> int:
    src = SHOTS / f"{stem}.png"
    if not src.exists():
        sys.exit(f"no {src}")
    shutil.copyfile(src, RECON / src.name)
    print(f"kept {(RECON / src.name).relative_to(REPO)}")
    return 0


def swipe(dev: Any, direction: str) -> None:
    """The finger's way: `up` drags up (shows what's below), as a scroll of the screen's middle."""
    w, h = dev.capabilities.width, dev.capabilities.height
    cx, cy = w // 2, h // 2
    dx, dy = {"up": (0, -h // 3), "down": (0, h // 3), "left": (-w // 3, 0), "right": (w // 3, 0)}[direction]
    got = dev._act_sync(Action(kind="swipe", x=cx, y=cy, x2=cx + dx, y2=cy + dy))
    print(f"swiped {direction}: {'ok' if got.ok else got.error}")


def setup_youtube(dev: Any, wait_s: float = 7) -> list[str]:
    """Before a YouTube run: a run that was force-stopped mid-edit can leave an autosave, and the next Create opens on
    "Continue your draft video?", which the routine doesn't expect (2 of 3 v2 replays). Open Create, answer that
    "Start over" (it drops the rehearsal's own unsaved edit), and force-stop on the empty camera, which leaves none
    (checked twice by hand, Nov 1)."""
    pkg = APPS["youtube"]
    dev.adb.shell(f"am force-stop {pkg}")
    dev._act_sync(Action(kind="launch", package=pkg))
    time.sleep(wait_s)
    done = []
    state, _ = observe(dev)
    create = next((e for e in state.numbered if (e.label or "").strip() == "Create"), None)
    if create is None:
        dev.adb.shell(f"am force-stop {pkg}")
        return ["no Create on YouTube's home: left it"]
    dev._act_sync(Action(kind="tap", element=create.number))
    time.sleep(4)
    state, _ = observe(dev)
    again = next((e for e in state.numbered if (e.label or "").strip() == "Start over"), None)
    if again is not None and any("Continue your draft video" in (e.label or "") for e in state.numbered):
        dev._act_sync(Action(kind="tap", element=again.number))
        done.append("draft prompt: Start over")
        time.sleep(3)
    dev.adb.shell(f"am force-stop {pkg}")
    return done + ["force-stopped on the camera"]


def tap_at(dev: Any, x: int, y: int) -> None:
    """A point, for what an app draws without an accessibility tree (TikTok's sound search results). Whatever element
    is under it gets safe_tap's refusals and the risk rule's verdict first."""
    state, _ = observe(dev)
    action = Action(kind="tap_point", x=x, y=y)
    v = classify(action, state, None)
    under = [e for e in state.numbered if e.bounds[0] <= x <= e.bounds[2] and e.bounds[1] <= y <= e.bounds[3]]
    for e in under:
        for w in (e.label, e.desc):
            if publishes(w, e.resource_id) or SOCIAL.match((w or "").strip()):
                sys.exit(f"REFUSED: ({x}, {y}) is on #{e.number} {w!r}: publishes or is social. Nothing was tapped.")
    if v.irreversible:
        sys.exit(f"REFUSED: ({x}, {y}) is irreversible by rule ({'; '.join(v.reasons)}). Nothing was tapped.")
    got = dev._act_sync(action)
    print(f"tapped ({x}, {y}) on {[e.label or e.resource_id for e in under][-1:] or 'nothing in the tree'}: {'ok' if got.ok else got.error}")


def open_app(dev: Any, pkg: str, fresh: bool) -> None:
    if fresh:
        dev.adb.shell(f"am force-stop {pkg}")
    got = dev._act_sync(Action(kind="launch", package=pkg))
    print(f"opened {NAMES[pkg]}{' (fresh)' if fresh else ''}: {'ok' if got.ok else got.error}")


# Instagram's Story composer, which instagram_take.leave_composer doesn't know (Back there only opens and closes "Discard
# edits?"): its Cancel, the dialog's Discard, then "Back to Home" from the Story gallery and camera. By id and label.
STORY_TAPS = (("cancel_button", "Cancel"), ("igds_alert_dialog_primary_button", "Discard"),
              ("gallery_cancel_button", "Back to Home"), ("camera_home_button", "Back to Home"))


def leave_story(dev: Any, max_steps: int = 8, wait_s: float = 1.3) -> list[str]:
    done: list[str] = []
    for _ in range(max_steps):
        state, _ = observe(dev)
        story = any(e.resource_id.endswith(("your_story_share_shortcut_button", "story_share_controls_action_bar")) for e in state.numbered)
        dialog = any((e.label or "") == "Discard" for e in state.numbered)
        story_camera = any(e.resource_id.endswith("cam_dest_story") and e.selected for e in state.elements)
        if not (story or dialog or story_camera):
            return done
        hit = next((e for rid, label in STORY_TAPS for e in state.numbered
                    if e.resource_id.endswith("/" + rid) and (e.label or "").strip() == label), None)
        if hit is None or classify(Action(kind="tap", element=hit.number), state, None).irreversible:
            done.append("story: nothing known to tap")
            return done
        dev._act_sync(Action(kind="tap", element=hit.number))
        done.append(f"story: {hit.label}")
        time.sleep(wait_s)
    return done


def leave(dev: Any, pkg: str, max_steps: int = 12, wait_s: float = 1.3) -> list[str]:
    """Out of the app's composer, keeping nothing: a dialog on the way gets its discard answer (LEAVE_OK), everything
    else gets Back, until the app's home (its bottom tabs) or another app is in front. Never taps anything that posts,
    saves or follows (NEVER). Instagram has its own, tested one (scripts/instagram_take.py `leave_composer`)."""
    if pkg == APPS["instagram"]:
        sys.path.insert(0, str(REPO / "scripts"))
        from instagram_take import leave_composer
        return leave_story(dev) + leave_composer(dev)
    if pkg in (APPS["tiktok"], APPS["youtube"]):
        # Both apps' exits ask with a discard labelled "Delete" (the rule flags it) or loop between the camera and its
        # close sheet; force-stopping leaves the unposted edit the same way, with nothing tapped. Measured on P3 and the
        # first runs (Nov 1). YouTube then offers "Continue your draft video?" once; a run answers it.
        dev.adb.shell(f"am force-stop {pkg}")
        return [f"force-stopped {NAMES[pkg]}"]
    done: list[str] = []
    for _ in range(max_steps):
        state, _ = observe(dev)
        if state.package != pkg:
            done.append(f"left {NAMES[pkg]} ({state.package})")
            return done
        labels = {(e.label or e.desc or "").strip().casefold() for e in state.numbered}
        if {"home", "profile"} <= labels and not camera_on(state):
            done.append("home")
            return done
        answer = next((e for e in state.numbered if e.kind == "Button" and LEAVE_OK.match((e.label or "").strip())
                       and not NEVER.search(e.label or "") and not classify(Action(kind="tap", element=e.number), state, None).irreversible),
                      None)
        # TikTok's "Delete · Discard" / "Drafts · Save draft": its discard says Delete, which the rule flags. Force-stopping
        # the app leaves the unsaved edit the same way, with nothing tapped.
        flagged = any(e.kind == "Button" and LEAVE_OK.match((e.label or "").split(" · ")[-1].strip())
                      and classify(Action(kind="tap", element=e.number), state, None).irreversible for e in state.numbered)
        if flagged:
            dev.adb.shell(f"am force-stop {pkg}")
            done.append("force-stopped (its discard is flagged irreversible by rule)")
            return done
        dialog = len(state.numbered) < 12  # a dialog's few buttons, not a screen that merely has a Cancel
        if answer is not None and dialog:
            dev._act_sync(Action(kind="tap", element=answer.number))
            done.append(f"tapped {answer.label!r}")
        else:
            dev._act_sync(Action(kind="back"))
            done.append("back")
        time.sleep(wait_s)
    done.append(f"stopped after {max_steps} steps on {observe(dev)[0].activity}")
    return done


# ---- the Post gate on a recorded screen -----------------------------------------------------------------------


def gate(dump: Path, pkg: str) -> int:
    """Every publishing-looking target on the recorded screen: the rule's verdict (no model label) and whether a post's
    request would let it through. 0 when the screen's publishing button is irreversible by rule and asks; 1 otherwise:
    then stop and tell the coordinator, with the dump. The rule is never widened here (policy/ is off limits)."""
    if dump.name.endswith(".json.gz"):  # a screen a run recorded (data/runs/<trace>/screens/NNN_before.json.gz)
        import gzip
        from routines.screens import screen_from_tree
        state = screen_from_tree(json.loads(gzip.open(dump).read()))
    else:
        state = build_state(dump.read_text(), pkg, "", *PIXEL5)
    request = f"the newest video in my phone's gallery to {NAMES[pkg]} with this caption"
    screen_text = " ".join(" ".join(x for x in (e.label, e.text, e.desc) if x) for e in state.numbered)
    rows, found, ok = [], 0, True
    for e in state.numbered:
        words = " ".join(x for x in (e.label, e.text, e.desc, e.resource_id.split("/")[-1]) if x)
        if not re.search(r"share|post|publish|upload|your story|close friends", words, re.I):
            continue
        v = classify(Action(kind="tap", element=e.number), state, None)
        by_rule = [r for r in v.reasons if r.startswith(("rule:", "screen:"))]
        auto = decide(ApprovalRules(), goal=request, source="web", app=pkg, routine=None, origin="agent", target=e.label or e.desc,
                      screen_text=screen_text)
        rows.append({"element": e.number, "kind": e.kind, "label": e.label, "text": e.text, "desc": e.desc, "id": e.resource_id,
                     "bounds": e.bounds, "risk": v.level, "reasons": v.reasons, "asks": auto is None})
        print(f"#{e.number:<3} {e.kind:9s} label={e.label!r} desc={e.desc!r} id={e.resource_id!r} "
              f"→ {v.level} {by_rule or ''}; {'asks' if auto is None else 'AUTO-APPROVED: ' + auto.why}")
        if e.kind == "Button" and (publishes(e.label, e.resource_id) or publishes(e.desc, None)):
            found += 1
            ok = ok and bool(by_rule) and auto is None
    ok = ok and found > 0
    out = dump.parent / (dump.name.removesuffix(".gz").removesuffix(".json").removesuffix(".xml") + ".gate.json")
    out.write_text(json.dumps({"dump": dump.name, "app": pkg, "request": request, "targets": rows, "post_gated": ok}, indent=1))
    print("\nPost gate: " + ("FIRES (irreversible by rule, and a post's request doesn't approve it)" if ok else
                             "DOES NOT MATCH: stop, and send the coordinator this dump; don't widen the rule"))
    return 0 if ok else 1


# ---- stage 1: compiling the first run under a new name ---------------------------------------------------------


def compile_run(trace: str, name: str, final_from_declined: bool, recompile: str | None = None, reuse_spec: bool = False) -> int:
    """Wonder compiles a declined first run (`confirmed`: it ended at the post the user declined, so it has no verified
    end); the routine is renamed (never instagram_post_reel or another existing name, backlog #43). With
    `final_from_declined`, the tap that was declined becomes the last step: its locator is built from the screen it was
    declined on, exactly as the compiler builds every other one, it is irreversible, and it has no after-check (it never
    ran)."""
    import asyncio
    import gzip
    from agent.trace import RUNS as TRACES
    from routines import locators
    from routines.compiler import compile_trace
    from routines.model import Check, Step, StepAction, dump_yaml
    from routines.screens import screen_from_tree
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", name):
        sys.exit(f"{name!r}: lower case, digits and _ only")
    if (REPO / "data" / "routines" / name).exists() and not recompile:
        sys.exit(f"{name!r} is already in the library: pick a new name (a compile under it would become its trial)")
    spec = None
    if reuse_spec:  # the Wonder answer the first compile paid for (its report), so a recompile costs no model call
        from models.schemas import CompiledRoutine
        spec = CompiledRoutine.model_validate(json.loads((ROUTINES / f"{name}.report.json").read_text())["wonder"])
    routine, report = asyncio.run(compile_trace(TRACES / trace, confirmed=True, spec=spec))
    changes = [f"compiled by showcase from {trace}, a first run declined at the post (eval/run_showcase.py)"
               + (f"; recompiled ({recompile})" if recompile else "")]
    if final_from_declined:
        records = [json.loads(x) for x in (TRACES / trace / "steps.jsonl").read_text().splitlines() if x.strip()]
        last = next((r for r in reversed(records) if r.get("kind") == "action" and (r.get("approval") or {}).get("approved") is False), None)
        if last is None:
            sys.exit("no declined tap in the trace")
        act = ((last.get("decision") or {}).get("action") or {})
        screen = screen_from_tree(json.loads(gzip.open(TRACES / trace / last["tree_before"]).read()))
        if act.get("type") != "tap" or not act.get("element"):
            sys.exit(f"the declined step is a {act.get('type')}, not a tap on an element")
        el = screen.element(int(act["element"]))
        if not (publishes(el.label, el.resource_id) or publishes(el.desc, None)):
            sys.exit(f"the declined tap is on {el.label!r} ({el.resource_id}), not the post button")
        loc = locators.build(el, screen)
        routine.steps.append(Step(id="tap_post", intent=f"Tap {el.label or el.desc} to publish", pre=[Check(kind="element_present", locator=loc)],
                                  action=StepAction(kind="tap", target=loc), risk="irreversible",
                                  note=f"trace step {last.get('step')}: the post tap the user declined (never ran, so no after-check)"))
        changes.append(f"its last step (tap {el.label or el.desc!r}) is the tap declined at step {last.get('step')}, "
                       "built from that screen; irreversible")
    routine = routine.model_copy(update={"routine": name, "changes": changes})
    ROUTINES.mkdir(parents=True, exist_ok=True)
    text = dump_yaml(routine)
    stem = f"{name}.recompiled" if recompile else name  # a recompile never overwrites the first compile or its report
    (ROUTINES / f"{stem}.yaml").write_text(text)
    (ROUTINES / f"{stem}.report.json").write_text(json.dumps({**report.__dict__, "trace": trace, "name": name, "recompile": recompile,
                                                              "final_from_declined": final_from_declined}, indent=1, default=str))
    print(text)
    print("# dropped:", *[f"#   step {n}: {w}" for n, w in report.dropped], sep="\n")
    print(f"# compiler {report.model}: {report.latency_s} s, ${report.cost_usd:.4f}")
    for w in report.warnings:
        print(f"# warning: {w}")
    print(f"saved {(ROUTINES / (stem + '.yaml')).relative_to(REPO)}")
    return 0


def add_routine(yaml_path: Path) -> int:
    """A compiled routine into this checkout's library (data/routines/<name>/), only if a step publishes and is
    irreversible, nothing after it, and every typed value comes from an input (so a replay types the new caption)."""
    from routines.model import has_slot, load_yaml
    from routines.store import RoutineStore
    r = load_yaml(yaml_path.read_text())
    post = [i for i, s in enumerate(r.steps) if s.action.target is not None and
            (publishes(s.action.target.text, s.action.target.resource_id) or publishes(s.action.target.desc, None))]
    problems = []
    if r.routine in ("instagram_post_reel", "doordash_order_meal"):
        problems.append(f"{r.routine} is a tuned routine: use a new name")
    if not post:
        problems.append("no step publishes")
    problems += [f"step {r.steps[i].id} publishes but is labeled {r.steps[i].risk}" for i in post if r.steps[i].risk != "irreversible"]
    if post and post[-1] != len(r.steps) - 1:
        problems.append(f"steps after the post: {[s.id for s in r.steps[post[-1] + 1:]]}")
    problems += [f"step {s.id} types a fixed value {s.action.value!r}" for s in r.steps
                 if s.action.kind == "type" and not has_slot(s.action.value or "")]
    if "phone" in r.inputs and r.inputs["phone"].type != "phone":  # agent-door: it would hide every tool's `phone` selector
        problems.append("an input named 'phone' that isn't a phone number: rename it")
    for p in problems:
        print(f"REFUSED: {p}")
    if problems:
        return 1
    added = RoutineStore().add(r, verification={"by": "showcase", "post_steps": [r.steps[i].id for i in post],
                                                "checked": time.strftime("%Y-%m-%d %H:%M")})
    print(f"added {added.routine} v{added.version} ({len(added.steps)} steps, inputs {list(added.inputs)}); "
          f"post at {[r.steps[i].id for i in post]}, irreversible")
    return 0


# ---- stage 1: runs on this session's API copy ------------------------------------------------------------------


def run_flow(args: argparse.Namespace) -> int:
    api = Copy(args.api, Path(args.api_dir))
    phone = next((d for d in api.get("/api/devices") if d.get("kind") == "phone" and d.get("state") == "device"), None)
    if phone is None:
        sys.exit("the copy sees no connected phone")
    t0 = time.time()
    marks: dict[str, float] = {}
    mark = lambda k: marks.setdefault(k, round(time.time() - t0, 1))  # noqa: E731
    say = lambda s: print(f"[{time.time() - t0:6.1f}s] {s}", flush=True)  # noqa: E731
    # A goal typed in the web app ("Post … to TikTok") is a direct request, and the approval rules let a button it names
    # through without asking (policy/approval_rules.py `names_action`) when the screen shows its details. So on this copy
    # the three apps are set to "always ask": every irreversible step asks, and this script declines it.
    rules = api.get("/api/settings/approvals")
    rules = rules.get("rules", rules)
    if any((rules.get("apps") or {}).get(p) != "always" for p in APPS.values()):
        rules = api.post("/api/settings/approvals", {**rules, "apps": {**(rules.get("apps") or {}), **{p: "always" for p in APPS.values()}}})
    if any((rules.get("apps") or {}).get(p) != "always" for p in APPS.values()):
        sys.exit(f"the copy didn't take 'always ask' for the three apps: {rules}")
    inputs = dict(kv.split("=", 1) for kv in getattr(args, "input", None) or [])
    pid = phone.get("id") or phone["avd"]  # /api/devices names a phone by `avd` ("phone-<serial>")
    if args.mode == "replay":
        body = {"phone": pid, "routine": args.routine, "inputs": inputs}
    else:
        # The first run is the agent's: naming the routine it will become (not in the library yet) skips the matcher,
        # which could otherwise pick instagram_post_reel for "a reel with this caption" (runner._plan: "routine … isn't
        # active: the agent does it instead").
        if (REPO / "data" / "routines" / args.as_).exists():
            sys.exit(f"{args.as_!r} is already in the library: a first run must be the agent's, under a new name")
        body = {"phone": pid, "goal": args.goal, "routine": args.as_}
    task = api.post("/api/tasks", body)
    tid = task["id"]
    say(f"task {tid}: {task['goal']!r} on {pid}")

    seen: set[str] = set()
    status = None
    approval_shot: str | None = None
    while time.time() - t0 < 900:
        got = api.get(f"/api/tasks/{tid}")
        task = got["task"]
        if task["status"] != status:
            status = task["status"]
            mark(status)
            say(f"task {status}{': ' + str(task.get('detail'))[:120] if task.get('detail') else ''}")
        if task.get("waiting_for") == "phone" and "phone_yes" not in marks:
            api.post(f"/api/tasks/{tid}/phone", {"allow": True})  # this copy's session: the phone is claimed for this run
            mark("phone_yes")
            say("said yes to using Envoy's phone (this copy's session)")
        elif status in PAUSED and not ended(task) and task.get("waiting_for") != "phone":
            n = len([k for k in marks if k.startswith('paused_')]) + 1
            if f"paused_{n - 1}" not in marks or marks.get(f"handback_{n - 1}"):
                mark(f"paused_{n}")
            # The app relaunching itself (TikTok after a force-stop: "came to the front on its own") isn't a person at
            # the phone, so this copy's session hands it back once. A real touch ("you touched…") waits for a person.
            if "on its own" in str(task.get("detail") or "") and f"handback_{n}" not in marks:
                api.post(f"/api/devices/{pid}/handback", {})
                mark(f"handback_{n}")
                say("handed back (the app came to the front on its own; nobody touched the phone)")
        for a in got["approvals"]:
            if a["id"] in seen:
                continue
            seen.add(a["id"])
            post = is_post(a)
            mark("post_asked" if post else f"asked_{len(seen)}")
            if post and a.get("screenshot"):  # what was on screen at the ask (which clip), kept outside the repo
                shot = api.http.get(f"/api/approvals/{a['id']}/shot")
                if shot.status_code == 200:
                    SHOTS.mkdir(parents=True, exist_ok=True)
                    shot_path = SHOTS / f"approval-{tid}.jpg"
                    shot_path.write_bytes(shot.content)
                    approval_shot = shot_path.name  # in SHOTS, outside the repo (never a full path: it names the Mac's user)
            say(f"approval asked: {a.get('description')!r} reasons={a.get('reasons')} {'(the post)' if post else '(NOT the post)'}")
            if a["status"] == "pending":
                api.decline(a["id"])
                say("declined here: nothing is posted")
        if ended(task):
            break
        time.sleep(1)
    got = api.get(f"/api/tasks/{tid}")
    task, steps, approvals = got["task"], got["steps"], got["approvals"]
    mark("end")
    auto = [s for s in steps if s.get("kind") == "approval" and "without asking" in (s.get("text") or "")]
    failures = []
    if not any(is_post(a) for a in approvals):
        failures.append("the post was never asked" + (" and the task ended done: check the profile now" if task["status"] == "done" else ""))
    if any(POST_WORDS.search(s.get("text") or "") for s in auto):
        failures.append(f"a publishing step went through without asking: {[s.get('text') for s in auto]}")
    if task["status"] == "done":
        failures.append("the run ended done")
    before = [a for a in approvals if not is_post(a) and (a.get("decided_by") == "user" or a["status"] in ("pending", "expired", "declined"))]
    if before:
        failures.append(f"asked about something before the post: {[a.get('description') for a in before]}")
    if any(a["status"] == "approved" for a in approvals if is_post(a)):  # this script only declines: someone else approved it
        failures.append(f"the post was approved: {[a.get('decided_by') for a in approvals if is_post(a) and a['status'] == 'approved']}")
    if args.mode == "replay" and task.get("routine") != args.routine:
        failures.append(f"the replay didn't run {args.routine} (task routine: {task.get('routine')!r})")
    posts = [asked_at(a) for a in approvals if is_post(a)]

    cost = spent(tid, t0 - 5)
    # How each routine step went (rung 0: matched at once; 4: a repair call; 5–6: the agent), from the routine's trace.
    from agent.trace import RUNS as TRACES
    routine_steps = []
    trace = TRACES / f"{tid}-r1" / "steps.jsonl"
    if args.mode == "replay" and trace.exists():
        for line in trace.read_text().splitlines():
            r = json.loads(line)
            if r.get("kind") == "routine_step":
                routine_steps.append({"id": r.get("id"), "status": r.get("status"), "rung": r.get("rung"),
                                      "score": r.get("score"), "rungs": r.get("rungs") or []})
    pkg = app_of(args.app) if args.app else task.get("app")  # the copy recorded a TikTok routine's task as Instagram's (Nov 1)
    result = {"mode": args.mode, "app": pkg, "time": datetime.fromtimestamp(t0).isoformat(timespec="seconds"), "request": body,
              "task": {k: task.get(k) for k in ("id", "status", "routine", "model_calls", "cost_usd", "traces", "detail", "device")},
              "steps": len(steps), "repairs": [s.get("text") for s in steps if "repair" in (s.get("text") or "").lower()][:10],
              "approvals": [{k: a.get(k) for k in ("description", "reasons", "status", "decided_by")} for a in approvals],
              "asked_at": posts, "approval_shot": approval_shot, "routine_steps": routine_steps, "auto_approved": [s.get("text") for s in auto], "marks_s": marks, "spent": cost, "ok": not failures,
              "failures": failures,
              "profile": os.environ.get("ENVOY_MODEL_PROFILE") or "hybrid"}
    if not args.no_cleanup and pkg:
        result["cleanup"] = leave(connect(), pkg)
    RUNS.mkdir(parents=True, exist_ok=True)
    app_name = NAMES.get(pkg or "", "app").lower()
    path = RUNS / f"{app_name}-{args.mode}-{datetime.fromtimestamp(t0):%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(result, indent=1, default=str))
    md = RUNS / "runs.md"
    if not md.exists():
        md.write_text("| when | app | mode | ok | task | routine | asked at | start → post asked | total | calls | $ | approvals |\n"
                      "|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    asked = "; ".join(f"{a.get('description')} → {a.get('status')}" for a in approvals)[:140]
    with md.open("a") as f:
        f.write(f"| {result['time']} | {NAMES.get(pkg or '', '?')} | {args.mode} | {'yes' if not failures else 'NO'} | {task['status']} | "
                f"{task.get('routine') or 'agent'} | {', '.join(posts) or 'never asked'} | {marks.get('post_asked', '–')} s | {marks['end']} s | "
                f"{cost['model_calls']} | {cost['cost_usd']} | {asked} |\n")
    say(f"saved {path.relative_to(REPO)}: {cost['model_calls']} model calls, ${cost['cost_usd']}")
    if failures:
        print("\n" + "\n".join(f"FAIL: {x}" for x in failures), flush=True)
        return 2
    say("OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("facts")
    p = sub.add_parser("open")
    p.add_argument("app")
    p.add_argument("--fresh", action="store_true")
    p = sub.add_parser("look")
    p.add_argument("label")
    p.add_argument("--private", action="store_true", help="a feed or anything with other people's content: nothing goes in the repo")
    p = sub.add_parser("tap")
    p.add_argument("query")
    p.add_argument("--nth", type=int, default=0)
    p.add_argument("--not-final", action="store_true", help="the target only opens a screen, though it has a publishing word")
    p.add_argument("--look", default=None, help="save the screen after the tap under this label")
    p.add_argument("--private", action="store_true", help="with --look: nothing goes in the repo")
    p.add_argument("--opens-sheet", action="store_true", help="a feed video's 'Share video…' icon (opens the share sheet)")
    p = sub.add_parser("tap-at")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("--look", default=None)
    p.add_argument("--private", action="store_true")
    p = sub.add_parser("type")
    p.add_argument("query")
    p.add_argument("text")
    p.add_argument("--nth", type=int, default=0)
    p = sub.add_parser("swipe")
    p.add_argument("direction", choices=["up", "down", "left", "right"])
    p = sub.add_parser("key")
    p.add_argument("key", choices=["back", "home"])
    p = sub.add_parser("push")
    p.add_argument("clip")
    p = sub.add_parser("gate")
    p.add_argument("dump")
    p.add_argument("--app", required=True)
    p = sub.add_parser("keep")
    p.add_argument("stem")
    p = sub.add_parser("leave")
    p.add_argument("app")
    sub.add_parser("setup-youtube")
    p = sub.add_parser("compile")
    p.add_argument("trace", help="data/runs/<trace>: a first run declined at the post")
    p.add_argument("--name", required=True, help="a new routine name (never one in the library)")
    p.add_argument("--final-from-declined", action="store_true")
    p.add_argument("--recompile", default=None, help="why (e.g. 'compiler fix ffde928'): recompile a routine already in the library")
    p.add_argument("--reuse-spec", action="store_true", help="reuse the first compile's Wonder answer (no model call)")
    p = sub.add_parser("add-routine")
    p.add_argument("yaml")
    for mode in ("first", "replay"):
        p = sub.add_parser(mode)
        p.add_argument("--app", default=None)
        if mode == "first":
            p.add_argument("--goal", required=True)
            p.add_argument("--as", dest="as_", required=True, help="the new routine's name (not in the library): the agent runs")
        else:
            p.add_argument("--routine", required=True)
            p.add_argument("--input", action="append", help="name=value, once per input")
        p.add_argument("--api", default=API)
        p.add_argument("--api-dir", default=os.environ.get("ENVOY_API_DIR") or "", help="the copy's data dir (its session_token)")
        p.add_argument("--no-cleanup", action="store_true")
        p.set_defaults(mode=mode)
    args = ap.parse_args()

    if args.cmd in ("first", "replay"):
        if not args.api_dir or Path(args.api_dir).resolve() == (REPO / "data" / "api").resolve():
            sys.exit("--api-dir (or ENVOY_API_DIR): the copy's data dir, never data/api")
        if not args.app:
            sys.exit("--app: which app the run is in (instagram, tiktok, youtube)")
        # A replay can fall back to the agent (the repair ladder's rung 5), so it waits on the rule too.
        if why := rule_gap(app_of(args.app), args.goal if args.cmd == "first" else args.routine):
            sys.exit(f"REFUSED: {why}")
        return run_flow(args)
    if args.cmd == "gate":
        return gate(Path(args.dump), app_of(args.app))
    if args.cmd == "keep":
        return keep(args.stem)
    if args.cmd == "compile":
        return compile_run(args.trace, args.name, args.final_from_declined, args.recompile, args.reuse_spec)
    if args.cmd == "add-routine":
        return add_routine(Path(args.yaml))
    if args.cmd == "push":
        print(json.dumps(push(Path(args.clip)), indent=1))
        return 0
    dev = connect()
    if args.cmd == "facts":
        print(json.dumps(facts(dev), indent=1))
    elif args.cmd == "open":
        open_app(dev, app_of(args.app), args.fresh)
    elif args.cmd == "look":
        save_look(dev, args.label, args.private)
    elif args.cmd == "tap":
        safe_tap(dev, args.query, args.nth, args.not_final, args.opens_sheet)
        if args.look:
            time.sleep(1.5)
            save_look(dev, args.look, args.private)
    elif args.cmd == "tap-at":
        tap_at(dev, args.x, args.y)
        if args.look:
            time.sleep(1.5)
            save_look(dev, args.look, args.private)
    elif args.cmd == "type":
        type_into(dev, args.query, args.text, args.nth)
    elif args.cmd == "swipe":
        swipe(dev, args.direction)
    elif args.cmd == "key":
        dev._act_sync(Action(kind=args.key))
    elif args.cmd == "setup-youtube":
        print("\n".join(setup_youtube(dev)))
    elif args.cmd == "leave":
        print("\n".join(leave(dev, app_of(args.app))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
