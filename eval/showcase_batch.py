"""B1, the showcase reliability batch, as eval/results/showcase-batch/PROTOCOL.md fixes it, on the eval-final tag.

  uv run --project backend python eval/showcase_batch.py songs --tag-dir <checkout at eval-final>
      The library check before the batch, search only (nothing is added, nothing is posted): songs 06-10 in Instagram's,
      TikTok's and YouTube's libraries, through each routine's own steps up to its search results.
  uv run --project backend python eval/showcase_batch.py run --api http://127.0.0.1:8764 --api-dir <copy> --tag-dir <checkout>
          [--only R01,T01] [--from R03] [--gap 120]
      The 40 attempts in the protocol's order, each from its starting state, each declined at the final button by
      eval/run_showcase.py replay. One record per attempt in attempts/<code>.json, one row per attempt in attempts.md.
  uv run --project backend python eval/showcase_batch.py report
      RESULTS.md's tables from the records.

The API copy runs from the clean checkout at the tag (--tag-dir); this script and run_showcase.py only drive it over HTTP
and drive the phone with `adb -s <serial>`. Every approval is declined. Approval screenshots stay outside the repo.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import run_showcase as rs  # noqa: E402  (sets up the backend's path)

OUT = REPO / "eval" / "results" / "showcase-batch"
ATTEMPTS = OUT / "attempts"
CLIPS = Path(os.environ.get("SHOWCASE_BATCH_CLIPS") or rs.SHOTS / "batch-clips")  # synthetic clips, outside the repo


@dataclass(frozen=True)
class Workflow:
    code: str
    app: str  # run_showcase's app name
    routine: str
    final: str  # the button the post is asked at
    colour: tuple[int, int, int]


WORKFLOWS = {
    "R": Workflow("R", "instagram", "instagram_reel_song", "Share", (232, 120, 30)),
    "T": Workflow("T", "tiktok", "tiktok_post_sound", "Post", (40, 90, 220)),
    "S": Workflow("S", "youtube", "youtube_short_sound", "Upload Short", (210, 40, 40)),
    "P": Workflow("P", "instagram", "instagram_story_poll", "Your story", (130, 60, 190)),
}
SONGS = {**{n: ("golden hour", "JVKE") for n in range(1, 6)},
         6: ("Espresso", "Sabrina Carpenter"), 7: ("Flowers", "Miley Cyrus"), 8: ("As It Was", "Harry Styles"),
         9: ("Blinding Lights", "The Weeknd"), 10: ("Levitating", "Dua Lipa")}
ALTERNATES = {6: "Please Please Please", 7: "Wrecking Ball", 8: "Watermelon Sugar", 9: "Save Your Tears", 10: "Don't Start Now"}
POLLS = {1: ("Coffee", "Tea"), 2: ("Cats", "Dogs"), 3: ("Beach", "Mountains"), 4: ("Pizza", "Tacos"), 5: ("Morning", "Night"),
         6: ("Books", "Films"), 7: ("Summer", "Winter"), 8: ("Sneakers", "Boots"), 9: ("Sweet", "Savory"), 10: ("City", "Country")}
STATES = {1: "cold", 4: "cold", 7: "cold", 10: "cold", 2: "open", 5: "open", 8: "open", 3: "draft", 6: "draft", 9: "draft"}
ORDER = [f"{w}{n:02d}" for n in range(1, 11) for w in "RTSP"]
CLASSES = ["outcome unknown", "failed", "person stepped in", "agent fallback", "repair", "no repair"]

# The step each routine's draft is made up to (its editor), and the step its song search shows results by.
DRAFT_UNTIL = {"R": ("instagram_reel_song", "tap_newest_video_thumbnail"), "P": ("instagram_reel_song", "tap_newest_video_thumbnail"),
               "T": ("tiktok_post_sound", "tap_next_after_gallery"), "S": ("youtube_short_sound", "tap_add_selected_video")}
SEARCH_UNTIL = {"R": ("instagram_reel_song", "find_tap_matching_track"), "T": ("tiktok_post_sound", "wait_for_sound_results"),
                "S": ("youtube_short_sound", "find_select_sound_result")}
BOT = re.compile(r"captcha|verify (it'?s you|you'?re (a )?human|your (identity|account))|suspicious|unusual activity|"
                 r"try again later|confirm it'?s you|account (is |has been )?(suspended|restricted|disabled|locked)|"
                 r"log ?in to (continue|instagram|tiktok)|sign ?in to (continue|youtube)", re.I)


# ---- the schedule ------------------------------------------------------------------------------------------------

def attempt(code: str, swaps: dict[int, str] | None = None) -> dict[str, Any]:
    """An attempt's fixed facts: workflow, starting state, clip label, inputs (PROTOCOL.md's tables)."""
    w, n = code[0], int(code[1:])
    wf = WORKFLOWS[w]
    title, artist = SONGS[n]
    if swaps and n in swaps:
        title = swaps[n]
    if w == "R":
        inputs = {"song_title": title, "song_artist": artist, "caption": f"Envoy batch {code} · test"}
    elif w == "T":
        inputs = {"sound_title": title, "sound_artist": artist, "caption": f"Envoy batch {code} · test"}
    elif w == "S":
        inputs = {"sound_title": title, "sound_artist": artist, "short_title": f"Envoy batch {code} · test"}
    else:
        a, b = POLLS[n]
        inputs = {"poll_question": f"Envoy batch {code}: which one?", "poll_option_1": a, "poll_option_2": b}
    return {"code": code, "workflow": w, "routine": wf.routine, "app": wf.app, "final": wf.final, "state": STATES[n],
            "clip_label": f"BATCH {code}", "inputs": inputs, "song": None if w == "P" else {"title": title, "artist": artist}}


# ---- outcome classes (PROTOCOL.md: the first that fits) ---------------------------------------------------------

_DECLINED_ASK = re.compile(r"declin", re.I)


def outcome_checks(rec: dict[str, Any]) -> dict[str, str]:
    """clip / song / caption / poll: yes, no, not checkable (or n/a), from the run's own outcome checks (C2)."""
    w = rec["workflow"]
    oc = ((rec.get("replay") or {}).get("outcome_checks") or [])
    last = oc[-1] if oc else None
    out = {"clip": "not checkable", "song": "n/a" if w == "P" else "not checkable", "caption": "n/a" if w == "P" else "not checkable",
           "poll": "not checkable" if w == "P" else "n/a"}
    if last is None:
        return out
    probs = " ".join(last.get("problems") or [])
    if "newest" in probs:
        out["clip"] = "no"
    elif last.get("clip") == "checked":
        out["clip"] = "yes"
    if w != "P":
        picks = last.get("picks") or {}
        if picks:
            out["song"] = "yes" if all(v == "shown" for v in picks.values()) else "no"
        fields = {k: v for k, v in (last.get("fields") or {}).items() if k in ("caption", "short_title")}
        if fields:
            vals = list(fields.values())
            out["caption"] = "no" if any(v not in ("held", "not on the final screen") for v in vals) else \
                ("yes" if all(v == "held" for v in vals) else "not checkable")
    return out


def classify(rec: dict[str, Any]) -> str:
    rp = rec.get("replay")
    if rec.get("harness_error") or not rp:
        return "outcome unknown"
    steps = rp.get("routine_steps") or []
    asked = rp.get("asked_at") or []
    approved = any(a.get("status") == "approved" for a in rp.get("approvals") or [])
    checks = rec.get("checks") or outcome_checks(rec)
    if approved or rec.get("stop_rule") or not rp.get("ok") or rec["final"] not in asked or "no" in checks.values():
        return "failed"
    # Rung 6 also marks the full agent stopping because its final ask was declined; that isn't a person.
    person_rung = any((s.get("rung") or 0) >= 6 and not any(_DECLINED_ASK.search(r) for r in s.get("rungs") or []) for s in steps)
    if rec.get("interventions") or person_rung:
        return "person stepped in"
    if any((s.get("rung") or 0) >= 5 or s.get("status") == "agent" for s in steps):
        return "agent fallback"
    if any((s.get("rung") or 0) == 4 for s in steps):
        return "repair"
    return "no repair"


# ---- the phone ---------------------------------------------------------------------------------------------------

def make_clip(label: str, colour: tuple[int, int, int], out: Path) -> Path:
    """8 s, 1080x1920, H.264, silent picture of its label (PROTOCOL.md: synthetic, no people or places)."""
    from PIL import Image, ImageDraw, ImageFont
    out.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1080, 1920), colour)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 230)
    for i, line in enumerate(label.split()):
        w = d.textlength(line, font=font)
        d.text(((1080 - w) / 2, 620 + i * 300), line, font=font, fill=(255, 255, 255))
    png = out.with_suffix(".png")
    img.save(png)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", str(png), "-t", "8", "-an", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-r", "30", str(out)], check=True)
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sh(cmd: list[str], timeout: float = 1200, cwd: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)


def py(*args: str, timeout: float = 1200, cwd: Path = REPO) -> subprocess.CompletedProcess:
    """In `cwd`'s checkout: the replay, the push and the take setup run in the tag's own checkout, where the copy writes
    its run traces (run_showcase.py reads each run's steps and outcome checks from them)."""
    return sh(["uv", "run", "--project", "backend", "python", *args], timeout=timeout, cwd=cwd)


def force_stop(dev: Any, pkg: str) -> None:
    dev.adb.shell(f"am force-stop {pkg}")


def home(dev: Any) -> None:
    dev.adb.shell("input keyevent KEYCODE_HOME")


def instagram_reset(args: argparse.Namespace) -> str:
    """scripts/instagram_take.py: answers "Keep editing your draft?" and checks Create opens the gallery, then home."""
    r = py("scripts/instagram_take.py", "--api", args.api, "--api-dir", args.api_dir, "--outbox", args.outbox, timeout=180,
           cwd=Path(args.tag_dir))
    return (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]


def run_steps(dev: Any, tag_dir: Path, routine: str, until: str, inputs: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    """The routine's own steps up to and including `until`, from a fresh launch, with no repair, no agent and every
    approval declined (none of these steps asks). How a draft is made and a song is looked up without a post."""
    from policy.approvals import ScriptedApprover
    from routines.executor import RoutineExecutor
    from routines.model import load_yaml
    lib = tag_dir / "data" / "routines" / routine
    v = json.loads((lib / "index.json").read_text())["active"]
    r = load_yaml((lib / f"v{v}.yaml").read_text())
    ids = [s.id for s in r.steps]
    r = r.model_copy(update={"steps": r.steps[: ids.index(until) + 1]})
    full = {n: inputs.get(n) or (spec.example or "x") for n, spec in r.inputs.items()}
    ex = RoutineExecutor(dev, approver=ScriptedApprover(approve=False))
    out = asyncio.run(ex.run(r, full, launch="fresh", allow_repair=False, allow_agent=False))
    return out.status, [{"id": s.id, "status": s.status, "rung": s.rung, "rungs": s.rungs} for s in out.steps]


def tap_label(dev: Any, pattern: str) -> str | None:
    state, _ = rs.observe(dev)
    rx = re.compile(pattern, re.I)
    el = next((e for e in state.numbered if e.kind == "Button" and rx.search(e.label or "")), None)
    if el is None:
        return None
    from devices.types import Action
    dev._act_sync(Action(kind="tap", element=el.number))
    return el.label


def set_state(dev: Any, a: dict[str, Any], args: argparse.Namespace) -> list[str]:
    """The attempt's starting state, as PROTOCOL.md describes it. Returns what was done, for the record."""
    w, pkg = a["workflow"], rs.APPS[a["app"]]
    did: list[str] = []
    if w in "RP":
        did.append(f"instagram_take: {instagram_reset(args)[:120]}")
    elif w == "S":
        did.append("setup_youtube: " + "; ".join(rs.setup_youtube(dev))[:120])
    force_stop(dev, pkg)
    if a["state"] == "cold":
        home(dev)
        did.append("force-stopped; launcher in front")
    elif a["state"] == "open":
        rs.open_app(dev, pkg, False)
        time.sleep(8 if w == "T" else 6)
        s, _ = rs.observe(dev)
        did.append(f"launched; {s.package == pkg and 'on the app' or 'NOT on the app: ' + s.package}, {s.activity.rsplit('.', 1)[-1]}")
    else:  # draft: made with the gallery's newest clip before this attempt's clip is pushed (an older clip)
        routine, until = DRAFT_UNTIL[w]
        status, steps = run_steps(dev, Path(args.tag_dir), routine, until, {})
        done = ", ".join(f"{s['id']}:{s['status']}" for s in steps)
        did.append(f"draft: {routine} up to {until}: {status} ({done})")
        if w in "RPT":
            dev.adb.shell("input keyevent KEYCODE_BACK")
            time.sleep(1.5)
            got = tap_label(dev, r"save draft|^drafts")
            did.append(f"back, then {'tapped ' + repr(got) if got else 'no Save draft offered'}")
            time.sleep(2)
        force_stop(dev, pkg)
        home(dev)
        did.append("force-stopped")
    return did


def stop_rule(dev: Any, rec: dict[str, Any]) -> str | None:
    """PROTOCOL.md's stop rules, after an attempt: a bot check or login wall, any sign of a publish, the phone gone."""
    st = sh(["adb", "-s", dev.serial, "get-state"], timeout=15)
    if st.stdout.strip() != "device":
        return "the phone is not connected"
    rp = rec.get("replay") or {}
    if any(a.get("status") == "approved" for a in rp.get("approvals") or []):
        return "an approval was approved: something may have been published"
    detail = str((rp.get("task") or {}).get("detail") or "")
    if "sign-in needed" in detail:
        return f"sign-in needed: {detail[:120]}"
    s, _ = rs.observe(dev)
    text = " ".join(f"{e.label} {e.desc or ''}" for e in s.numbered)
    if (m := BOT.search(text)):
        return f"{m.group(0)!r} on screen ({s.package})"
    return None


# ---- one attempt -------------------------------------------------------------------------------------------------

def copy_ok(args: argparse.Namespace, tag_dir: Path) -> dict[str, Any]:
    tag = sh(["git", "-C", str(tag_dir), "rev-parse", "eval-final"]).stdout.strip()
    head = sh(["git", "-C", str(tag_dir), "rev-parse", "HEAD"]).stdout.strip()
    # Code only: the copy writes its run history into data/ and the replays into eval/results/, as expected.
    dirty = sh(["git", "-C", str(tag_dir), "status", "--porcelain", "--untracked-files=no", "--", "backend", "scripts",
                "eval/*.py", "agents"]).stdout.strip()
    driver = sh(["git", "rev-parse", "HEAD"]).stdout.strip()
    driver_dirty = bool(sh(["git", "status", "--porcelain", "--untracked-files=no", "--", "eval/showcase_batch.py",
                            "eval/run_showcase.py", "eval/run_creator.py"]).stdout.strip())
    subs = sqlite3.connect(f"file:{Path(args.api_dir) / 'envoy.db'}?mode=ro", uri=True).execute("select count(*) from push_subs").fetchone()[0]
    return {"tag": tag, "copy_head": head, "copy_clean": not dirty, "driver": driver, "driver_dirty": driver_dirty, "push_subs": subs}


def routine_version(rp: dict[str, Any]) -> int | None:
    for a in rp.get("approvals") or []:
        if (m := re.search(r"\(routine \w+ v(\d+)\)", a.get("description") or "")):
            return int(m.group(1))
    return None


def run_attempt(dev: Any, a: dict[str, Any], args: argparse.Namespace, versions: dict[str, Any]) -> dict[str, Any]:
    tag_dir = Path(args.tag_dir)
    rec: dict[str, Any] = {**a, "versions": versions, "started": datetime.now().isoformat(timespec="seconds")}
    t0 = time.time()
    try:
        rec["setup"] = set_state(dev, a, args)
        clip = make_clip(a["clip_label"], WORKFLOWS[a["workflow"]].colour, CLIPS / f"batch-{a['code'].lower()}.mp4")
        p = py("eval/run_showcase.py", "push", str(clip), "--api-dir", args.api_dir, timeout=180, cwd=tag_dir)
        got = json.loads(p.stdout[p.stdout.index("{"):]) if "{" in p.stdout else {}
        rec["clip"] = {"file": clip.name, "sha256": sha256(clip), "remote_path": got.get("remote_path"), "media_uri": got.get("media_uri")}
        cmd = ["eval/run_showcase.py", "replay", "--app", a["app"], "--routine", a["routine"], "--api", args.api, "--api-dir", args.api_dir]
        for k, v in a["inputs"].items():
            cmd += ["--input", f"{k}={v}"]
        r = py(*cmd, timeout=1100, cwd=tag_dir)
        log = r.stdout + ("\n" + r.stderr[-2000:] if r.returncode not in (0, 1) else "")
        (ATTEMPTS / f"{a['code']}.log").write_text(log)
        saved = re.search(r"saved (eval/results/showcase/runs/\S+\.json)", r.stdout)
        if not saved:
            rec["harness_error"] = f"no replay record (exit {r.returncode}): {(r.stderr or r.stdout)[-300:]}"
        else:
            rp = json.loads((tag_dir / saved.group(1)).read_text())
            rec["replay"] = rp
            rec["replay_file"] = saved.group(1)
            rec["routine_version"] = routine_version(rp)
            shot = rs.SHOTS / rp["approval_shot"] if rp.get("approval_shot") else None
            rec["approval_shot"] = {"file": shot.name, "sha256": sha256(shot)} if shot and shot.exists() else None
            rec["interventions"] = [ln.strip() for ln in r.stdout.splitlines()
                                    if re.search(r"task taken_over|handed back|touched", ln)]
    except Exception as e:  # noqa: BLE001 - kept as "outcome unknown", never dropped
        rec["harness_error"] = f"{type(e).__name__}: {e}"[:400]
    idx = tag_dir / "data" / "routines" / a["routine"] / "index.json"
    try:
        rec["active_after"] = json.loads(idx.read_text())["active"]
    except Exception:  # noqa: BLE001
        rec["active_after"] = None
    rec["ended"] = datetime.now().isoformat(timespec="seconds")
    rec["wall_s"] = round(time.time() - t0, 1)
    try:
        rec["stop_rule"] = stop_rule(dev, rec)
    except Exception as e:  # noqa: BLE001
        rec["stop_rule"] = f"couldn't check the phone: {type(e).__name__}"
    rec["checks"] = outcome_checks(rec)
    rec["class"] = classify(rec)
    return rec


def row(rec: dict[str, Any]) -> str:
    rp = rec.get("replay") or {}
    marks = rp.get("marks_s") or {}
    sp = rp.get("spent") or {}
    c = rec.get("checks") or {}
    song = rec["song"]["title"] if rec.get("song") else "—"
    note = rec.get("harness_error") or rec.get("stop_rule") or "; ".join(rp.get("failures") or []) or ""
    return (f"| {rec['code']} | {rec['state']} | {song} | v{rec.get('routine_version') or '?'}→v{rec.get('active_after') or '?'} | "
            f"{', '.join(rp.get('asked_at') or []) or '—'} | {marks.get('post_asked', '—')} | {sp.get('model_calls', '—')} | "
            f"{sp.get('cost_usd', '—')} | **{rec['class']}** | {c.get('clip')} | {c.get('song')} | {c.get('caption')} | {c.get('poll')} | "
            f"{note[:140]} |")


HEADER = ("| Attempt | State | Song | Version (run→after) | Asked at | Time to ask (s) | Calls | $ | Class | Clip | Song | Caption | Poll | Note |\n"
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")


def write_table() -> None:
    recs = [json.loads((ATTEMPTS / f"{c}.json").read_text()) for c in ORDER if (ATTEMPTS / f"{c}.json").exists()]
    (OUT / "attempts.md").write_text("# The batch's attempts, in run order\n\nEvery attempt is kept (PROTOCOL.md).\n\n" + HEADER +
                                     "\n".join(row(r) for r in sorted(recs, key=lambda r: r["started"])) + "\n")


def cmd_run(args: argparse.Namespace) -> int:
    ATTEMPTS.mkdir(parents=True, exist_ok=True)
    tag_dir = Path(args.tag_dir)
    versions = copy_ok(args, tag_dir)
    print("versions:", json.dumps(versions))
    if versions["tag"] != versions["copy_head"] or not versions["copy_clean"]:
        sys.exit("the copy's checkout isn't a clean checkout of eval-final")
    if versions["push_subs"]:
        sys.exit(f"the copy has {versions['push_subs']} push subscriptions")
    swaps = json.loads((OUT / "songs.json").read_text()).get("swaps", {}) if (OUT / "songs.json").exists() else {}
    swaps = {int(k): v for k, v in swaps.items()}
    codes = args.only.split(",") if args.only else ORDER[ORDER.index(args.start):] if args.start else ORDER
    dev = rs.connect()
    last_end = 0.0
    for code in codes:
        if (ATTEMPTS / f"{code}.json").exists() and not args.redo:
            print(f"{code}: already recorded, skipped")
            continue
        wait = args.gap - (time.time() - last_end)
        if last_end and wait > 0:
            time.sleep(wait)
        a = attempt(code, swaps)
        print(f"== {datetime.now():%H:%M:%S} {code} {a['state']} {a['inputs']}", flush=True)
        rec = run_attempt(dev, a, args, versions)
        (ATTEMPTS / f"{code}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        write_table()
        last_end = time.time()
        print(f"   {rec['class']} · asked {((rec.get('replay') or {}).get('asked_at'))} · checks {rec['checks']} · "
              f"{((rec.get('replay') or {}).get('spent') or {}).get('model_calls', '?')} calls · {rec['wall_s']} s", flush=True)
        if rec.get("stop_rule"):
            print(f"STOP: {rec['stop_rule']}")
            return 2
    return 0


# ---- the library check -------------------------------------------------------------------------------------------

def cmd_songs(args: argparse.Namespace) -> int:
    from routines.screens import contains_value
    dev = rs.connect()
    tag_dir = Path(args.tag_dir)
    results: dict[str, Any] = {"when": datetime.now().isoformat(timespec="seconds"), "checks": [], "swaps": {}}
    songs = {n: SONGS[n] for n in range(6, 11)} if not args.alternates else {n: (ALTERNATES[n], SONGS[n][1]) for n in args.alternates}
    for n, (title, artist) in songs.items():
        for w in "RTS":
            routine, until = SEARCH_UNTIL[w]
            names = ("song_title", "song_artist") if w == "R" else ("sound_title", "sound_artist")
            if w in "R":
                instagram_reset(args)
            elif w == "S":
                rs.setup_youtube(dev)
            status, steps = run_steps(dev, tag_dir, routine, until, dict(zip(names, (title, artist))))
            time.sleep(2)
            s, _ = rs.observe(dev)
            shown = any(contains_value(e.label, title) and contains_value(e.label, artist) for e in s.numbered)
            shot = rs.SHOTS / f"songs-{w}-{n:02d}-{re.sub(r'[^a-z0-9]+', '-', title.lower())}.png"
            try:
                shot.write_bytes(asyncio.run(dev.screenshot()))
            except Exception:  # noqa: BLE001
                shot = None
            found = "yes" if (status == "done" and w != "T") or shown else ("see screenshot" if w == "T" else "no")
            results["checks"].append({"n": n, "title": title, "artist": artist, "app": w, "status": status, "found": found,
                                      "steps": steps, "screenshot": shot.name if shot else None})
            print(f"{n:02d} {title} / {artist} in {w}: {found} ({status})", flush=True)
            force_stop(dev, rs.APPS[WORKFLOWS[w].app])
            home(dev)
    (OUT / ("songs-alternates.json" if args.alternates else "songs.json")).write_text(json.dumps(results, indent=1, ensure_ascii=False))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    recs = [json.loads((ATTEMPTS / f"{c}.json").read_text()) for c in ORDER if (ATTEMPTS / f"{c}.json").exists()]
    lines = ["# Showcase reliability batch: results", "", f"{len(recs)} of {len(ORDER)} attempts recorded (PROTOCOL.md).", ""]
    lines += ["| Workflow | " + " | ".join(CLASSES) + " | All checks yes | Median s to ask | Calls (Envoy's replay) | $ |",
              "| --- | " + " | ".join("---" for _ in CLASSES) + " | --- | --- | --- | --- |"]
    for w, wf in WORKFLOWS.items():
        rs_ = [r for r in recs if r["workflow"] == w]
        if not rs_:
            continue
        times = sorted(((r.get("replay") or {}).get("marks_s") or {}).get("post_asked") for r in rs_
                       if ((r.get("replay") or {}).get("marks_s") or {}).get("post_asked") is not None)
        med = times[len(times) // 2] if times else "—"
        calls = sum(((r.get("replay") or {}).get("spent") or {}).get("model_calls", 0) for r in rs_)
        usd = round(sum(((r.get("replay") or {}).get("spent") or {}).get("cost_usd", 0.0) for r in rs_), 4)
        allyes = sum(1 for r in rs_ if all(v in ("yes", "n/a") for v in (r.get("checks") or {}).values()))
        lines.append(f"| {wf.routine} ({w}) | " + " | ".join(str(sum(1 for r in rs_ if r['class'] == c)) for c in CLASSES) +
                     f" | {allyes}/{len(rs_)} | {med} | {calls} | {usd} |")
    (OUT / "RESULTS-tables.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "songs"):
        p = sub.add_parser(name)
        p.add_argument("--api", default=rs.API)
        p.add_argument("--api-dir", required=True)
        p.add_argument("--outbox", required=True)
        p.add_argument("--tag-dir", required=True)
        if name == "run":
            p.add_argument("--only", default="")
            p.add_argument("--from", dest="start", default="")
            p.add_argument("--gap", type=float, default=120.0)
            p.add_argument("--redo", action="store_true")
        else:
            p.add_argument("--alternates", type=lambda s: [int(x) for x in s.split(",")], default=None,
                           help="check these attempts' alternates instead (e.g. 6,9)")
    sub.add_parser("report")
    args = ap.parse_args()
    return {"run": cmd_run, "songs": cmd_songs, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
