"""Cross-posting (api/crosspost.py and `cross_post` in mcp_server/server.py), offline.

The real task runner with fake phones; each app's routine is a fake that asks for its post's approval like the real
executor (api/approvals.py's WebApprover, decided here as the user would), counts a post when the approved tap runs, and
then ends done, fails, times out or hangs. The count is the thing that must never reach two.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.crosspost as crosspost_mod
import api.runner as runner_mod
from api.crosspost import RETRYABLE, CrossPost, Post, outcome, tapped
from api.events import EventBus
from api.runner import TaskRunner
from api.store import TaskStore
from memory.store import MemoryStore
from policy.approvals import ApprovalRequest
from test_crossapp import Pool
from test_routine_tools import LIB, called, listed
from test_mcp_link import make as make_env

IG, TT, YT = "com.instagram.android", "com.zhiliaoapp.musically", "com.google.android.youtube"
NAME = {IG: "Instagram", TT: "TikTok", YT: "YouTube"}
ROUTINE = {IG: "instagram_reel_song", TT: "tiktok_post_sound", YT: "youtube_short_sound"}

# What each app's routine does, run by run (the first item is popped each run; the last one stays):
#   post: asks for the post's approval; approved, the tap runs (a post) and the run ends done
#   fail: fails before its post step (no approval asked)
#   post_then_timeout: approved, the tap runs, then the run times out before its check
#   post_then_hang: approved, the tap runs, then the run hangs (the cross-post's limit stops it)
PLAN: dict[str, list[str]] = {}
POSTS: dict[str, int] = {}
SPANS: list[tuple[str, float, float]] = []
# The phone's gallery, newest last, and the clip Envoy last pushed. TikTok's post adds its own copy (as on the Pixel, Nov 2).
# With CLIP_CHECK on, the other routines check the newest item against the push before their first step, as the
# executor's clip check does (WS-A, C2), and stop without asking for anything on a mismatch.
GALLERY: list[str] = []
PUSHED: dict[str, str] = {}
CLIP_CHECK: list[bool] = [False]


class FakeExecutor:
    def __init__(self, gated, adapter=None, approver=None, config=None, app_notes=None) -> None:
        self.approver = approver

    async def run(self, routine, inputs, task_id, **kw):
        app = routine.app
        mode = PLAN[app].pop(0) if len(PLAN[app]) > 1 else PLAN[app][0]
        t0 = time.time()
        try:
            await asyncio.sleep(0.05)
            if CLIP_CHECK[0] and app != TT and GALLERY and GALLERY[-1] != PUSHED.get("name"):
                return SimpleNamespace(status="failed", outputs={}, model_calls=0, cost_at_standard_usd=0.0,
                                       detail=f"the gallery's newest video is {GALLERY[-1]} (saved by {TT}), not {PUSHED.get('name')}, "
                                              "the clip Envoy put on the phone: the routine takes the newest, so it would post the wrong one")
            if mode == "fail":
                return SimpleNamespace(status="failed", detail="couldn't find Create on the screen", outputs={}, model_calls=0,
                                       cost_at_standard_usd=0.0)
            req = ApprovalRequest(task_id, "goal", app, f'tap "Post" in {app} (routine {routine.routine} v1)', ["irreversible"], "screen",
                                  target="Post")
            if not (await asyncio.to_thread(self.approver.request, req)).approved:
                return SimpleNamespace(status="declined", detail="the user declined the approval", outputs={}, model_calls=0,
                                       cost_at_standard_usd=0.0)
            POSTS[app] = POSTS.get(app, 0) + 1  # the approved tap: a post
            if app == TT:
                GALLERY.append(f"tiktok-export-{POSTS[app]}.mp4")  # TikTok saves its own copy in DCIM/Camera
            if mode == "post_then_timeout":
                raise TimeoutError("the screen didn't settle after the tap")
            if mode == "post_then_hang":
                await asyncio.sleep(3600)
            return SimpleNamespace(status="done", detail="all steps and checks passed", outputs={}, model_calls=0, cost_at_standard_usd=0.0)
        finally:
            SPANS.append((app, t0, time.time()))


@pytest.fixture(autouse=True)
def fake_phone_work(monkeypatch, tmp_path):
    monkeypatch.setattr(runner_mod, "RoutineExecutor", FakeExecutor)
    monkeypatch.setattr(runner_mod, "after_run", lambda *a, **k: None)
    monkeypatch.setattr("api.approvals.SHOTS", tmp_path / "shots")
    monkeypatch.setattr(runner_mod, "SHOTS", tmp_path / "shots")
    PLAN.clear()
    POSTS.clear()
    SPANS.clear()
    PLAN.update({IG: ["post"], TT: ["post"], YT: ["post"]})
    GALLERY[:] = ["clip.mp4"]
    PUSHED.update(name="clip.mp4")
    CLIP_CHECK[0] = False


def make() -> tuple[TaskRunner, CrossPost]:
    store, bus, mem = TaskStore(":memory:"), EventBus(), MemoryStore(":memory:")
    r = TaskRunner(store, bus, Pool(), mem, SimpleNamespace(), adapter=SimpleNamespace())
    r.loop = asyncio.get_running_loop()
    r.approval_timeout_s = 20  # a test that fails mid-way doesn't leave an approval's thread waiting 15 min

    async def plan(tid, goal, routine_name, inputs, app):
        return SimpleNamespace(routine=routine_name, version=1, app=app), inputs, app, {}, 0

    async def remember(*a, **k):
        return None

    r._plan, r._remember = plan, remember
    return r, CrossPost(r)


def posts(*apps: str) -> list[Post]:
    return [Post(ROUTINE[a], a, NAME[a], f"Post the newest video to {NAME[a]}", {"caption": "one clip, three apps"}) for a in apps]


async def until(cond, timeout=10.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out waiting"
        await asyncio.sleep(0.01)


def kids(r, pid) -> list[dict]:
    return sorted((t for t in r.store.list(limit=500) if t.get("parent") == pid), key=lambda t: t["created_at"])


async def decide(r, pid, app: str, yes: bool = True) -> None:
    """The user answers the post's approval for `app` in Envoy, once it is asked."""
    def pending():
        return next((a for a in r.store.approvals(status="pending") if (r.store.get(a["task_id"]) or {}).get("parent") == pid
                     and (r.store.get(a["task_id"]) or {}).get("app") == app), None)
    await until(lambda: pending() is not None and pending()["task_id"] in r.approvers)
    a = pending()
    r.approvers[a["task_id"]].decide(a["id"], yes, by="test")


async def ended(r, pid, timeout=10.0):
    await asyncio.wait_for(asyncio.shield(r.jobs[pid]), timeout)


def statuses(cp, pid) -> dict[str, str]:
    return {row["app_name"]: row["status"] for row in cp.view(pid)}


# ---- the outcome of a part ----------------------------------------------------------------------------


def test_an_approved_tap_that_ran_is_what_makes_an_ended_part_unknown():
    yes = {"status": "approved", "note": ""}
    moved = {"status": "approved", "note": "the screen changed before the action ran (gone: Post): asked again"}
    assert tapped([yes]) and not tapped([moved]) and not tapped([{"status": "declined"}, {"status": "expired"}])
    assert outcome({"status": "done"}, [yes], ended=True) == "done"
    assert outcome({"status": "failed"}, [yes], ended=True) == "unknown"
    assert outcome({"status": "stopped"}, [yes], ended=True) == "unknown"
    assert outcome({"status": "failed"}, [moved], ended=True) == "failed"  # said yes, but nothing ran: safe to try again
    assert outcome({"status": "declined"}, [{"status": "declined"}], ended=True) == "declined"
    assert outcome({"status": "needs_you"}, [], ended=True) == "failed"
    assert outcome({"status": "waiting_approval"}, [], ended=False) == "waiting"
    assert outcome({"status": "running"}, [yes], ended=False) == "verifying"
    assert outcome({"status": "running"}, [], ended=False) == "running"
    late = {"status": "approved", "note": "", "decided_at": 200.0}  # said yes after the part had ended at 100
    assert not tapped([late], before=100.0) and tapped([late], before=300.0)
    assert outcome({"status": "running"}, [late], ended=True, ended_at=100.0) == "failed"  # a stopped part reads "running" again


# ---- the run ---------------------------------------------------------------------------------------------


def test_one_parent_task_runs_a_part_per_destination_one_after_another():
    async def scenario():
        r, cp = make()
        parent = cp.start(posts(IG, TT, YT), "mcp")
        pid = parent["id"]
        for app in (IG, YT, TT):  # TikTok last (SAVES_COPY)
            await decide(r, pid, app)
        await ended(r, pid)
        return r, cp, pid
    r, cp, pid = asyncio.run(scenario())
    parent = r.store.get(pid)
    assert parent["status"] == "done" and parent["kind"] == "crossapp" and parent["goal"] == "Post to Instagram, YouTube and TikTok"
    assert parent["result"] == "Instagram: done · YouTube: done · TikTok: done"
    parts = kids(r, pid)
    assert [(p["app"], p["routine"], p["status"]) for p in parts] == [(IG, ROUTINE[IG], "done"), (YT, ROUTINE[YT], "done"), (TT, ROUTINE[TT], "done")]
    assert POSTS == {IG: 1, TT: 1, YT: 1}
    spans = sorted(SPANS, key=lambda s: s[1])
    assert all(a[2] <= b[1] for a, b in zip(spans, spans[1:]))  # one after another, never two at once
    assert [row["attempts"] for row in cp.view(pid)] == [1, 1, 1]


@pytest.mark.parametrize("mode", ["post_then_timeout", "post_then_hang"])
def test_a_timeout_right_after_the_post_tap_is_outcome_unknown_and_nothing_posts_twice(mode, monkeypatch):
    """Planted right after the post tap: the run times out (or hangs until the cross-post stops it) before its check.
    The post may exist, so TikTok is outcome unknown, the user is asked to check, and no retry posts there again."""
    monkeypatch.setattr(crosspost_mod, "PART_LIMIT_S", 0.5)
    PLAN.update({TT: [mode], YT: ["fail", "post"]})

    async def scenario():
        r, cp = make()
        pid = cp.start(posts(IG, TT, YT), "mcp")["id"]
        await decide(r, pid, IG)
        await decide(r, pid, TT)
        await ended(r, pid)
        first = (r.store.get(pid), statuses(cp, pid), next(row for row in cp.view(pid) if row["app_name"] == "TikTok"))
        again = cp.retry(pid, "mcp")  # only YouTube, which failed before its post step
        await decide(r, pid, YT)
        await ended(r, pid)
        once_more = cp.retry(pid, "mcp")
        return r, cp, pid, first, again, once_more
    r, cp, pid, (parent, seen, tiktok), again, once_more = asyncio.run(scenario())
    assert seen == {"Instagram": "done", "TikTok": "unknown", "YouTube": "failed"}
    assert parent["status"] == "needs_you" and parent["detail"].startswith("Check TikTok yourself: the post tap went through")
    assert "Envoy won't post there again" in parent["detail"] and "a retry runs only YouTube" in parent["detail"]
    assert "check this one" in parent["result"] and "Check TikTok yourself" in tiktok["text"]
    assert again["retrying"] == ["YouTube"] and again["left_alone"] == [{"app": "Instagram", "status": "done"}, {"app": "TikTok", "status": "unknown"}]
    assert "TikTok saves its own copy" in again["heads_up"][0]["text"]  # it may have posted, so its copy may be the newest
    assert POSTS == {IG: 1, TT: 1, YT: 1}  # TikTok's tap ran once, and nothing ran it again
    assert [p["app"] for p in kids(r, pid)].count(TT) == 1
    assert statuses(cp, pid) == {"Instagram": "done", "TikTok": "unknown", "YouTube": "done"}
    assert "error" in once_more and "TikTok is unknown" in once_more["error"] and "the user checks that app" in once_more["error"]
    assert r.store.get(pid)["status"] == "needs_you"


@pytest.mark.parametrize("youtube", ["approved", "ran out of time"])
def test_partial_failure_a_retry_finishes_only_tiktok_and_youtube_and_instagram_posts_once(youtube):
    """Instagram done, YouTube waiting for its approval, TikTok still to run (it runs last). A retry while YouTube waits
    has nothing to run and leaves Instagram alone. Then TikTok fails, after YouTube was approved (the retry runs only
    TikTok) or after YouTube's wait ran out without a yes (it runs YouTube and TikTok). Instagram posts once."""
    PLAN.update({TT: ["fail", "post"]})

    async def scenario():
        r, cp = make()
        pid = cp.start(posts(IG, TT, YT), "mcp")["id"]
        await decide(r, pid, IG)
        await until(lambda: statuses(cp, pid) == {"Instagram": "done", "YouTube": "waiting", "TikTok": "queued"})
        mid = (r.store.get(pid)["status"], cp.retry(pid, "mcp"))
        if youtube == "approved":
            await decide(r, pid, YT)
        else:  # its approval expired: nothing was posted there, so it is unfinished
            a = next(a for a in r.store.approvals(status="pending") if (r.store.get(a["task_id"]) or {}).get("app") == YT)
            r.store.decide_approval(a["id"], "expired", "timeout", "no answer in time: not done, never auto-approved")
            r.approvers[a["task_id"]]._events[a["id"]].set()
        await ended(r, pid)
        failed = statuses(cp, pid)
        again = cp.retry(pid, "mcp")
        for app in ([TT] if youtube == "approved" else [YT, TT]):
            await decide(r, pid, app)
        await ended(r, pid)
        return r, cp, pid, mid, failed, again
    r, cp, pid, (waiting, early), failed, again = asyncio.run(scenario())
    assert waiting == "waiting_approval"
    assert early["error"].startswith("nothing to retry: Instagram is done; YouTube is waiting; TikTok is queued")
    if youtube == "approved":
        assert failed == {"Instagram": "done", "YouTube": "done", "TikTok": "failed"}
        assert again["retrying"] == ["TikTok"]
    else:
        assert failed == {"Instagram": "done", "YouTube": "declined", "TikTok": "failed"}
        assert again["retrying"] == ["YouTube", "TikTok"] and again["left_alone"] == [{"app": "Instagram", "status": "done"}]
    assert "heads_up" not in again  # TikTok hadn't posted
    assert POSTS == {IG: 1, TT: 1, YT: 1}
    assert statuses(cp, pid) == {"Instagram": "done", "TikTok": "done", "YouTube": "done"} and r.store.get(pid)["status"] == "done"
    assert {row["app_name"]: row["attempts"] for row in cp.view(pid)} == {"Instagram": 1, "TikTok": 2, "YouTube": 1 if youtube == "approved" else 2}
    assert [p["app"] for p in kids(r, pid)].count(IG) == 1


def test_tiktok_runs_last_so_no_other_post_picks_its_copy_of_the_clip():
    """TikTok saves its own copy of every post in the gallery (DCIM/Camera on the Pixel, Nov 2), and the other routines
    take the gallery's newest video. Given first, it still runs after Instagram and YouTube, and each posts the clip."""
    CLIP_CHECK[0] = True

    async def scenario():
        r, cp = make()
        pid = cp.start(posts(TT, IG, YT), "mcp")["id"]
        for app in (IG, YT, TT):
            await decide(r, pid, app)
        await ended(r, pid)
        return r, cp, pid
    r, cp, pid = asyncio.run(scenario())
    assert [p["app"] for p in kids(r, pid)] == [IG, YT, TT] and [row["app_name"] for row in cp.view(pid)] == ["Instagram", "YouTube", "TikTok"]
    assert r.store.get(pid)["status"] == "done" and POSTS == {IG: 1, YT: 1, TT: 1}
    assert "(TikTok last: it saves its own copy of the post in the gallery)" in next(s for s in r.store.steps(pid) if s["kind"] == "plan")["text"]


def test_a_retry_after_tiktok_posted_asks_for_the_clip_again_and_the_clip_check_stops_a_wrong_post():
    """TikTok before another part: Instagram failed, YouTube and TikTok posted, and TikTok's copy is now the newest video.
    The retry says to send the clip again first; run without it, the clip check stops Instagram before any step (not
    posted, so it can be retried); with the clip sent again, Instagram posts it, once."""
    CLIP_CHECK[0] = True
    PLAN.update({IG: ["fail", "post"]})

    async def scenario():
        r, cp = make()
        pid = cp.start(posts(IG, YT, TT), "mcp")["id"]
        await decide(r, pid, YT)
        await decide(r, pid, TT)
        await ended(r, pid)
        first = cp.retry(pid, "mcp")
        await ended(r, pid)
        stopped = (statuses(cp, pid), (r.store.get(kids(r, pid)[-1]["id"]) or {}).get("detail"), POSTS.get(IG))
        GALLERY.append("clip-again.mp4")  # send_to_phone puts the clip on the phone again: the newest, and the last push
        PUSHED.update(name="clip-again.mp4")
        second = cp.retry(pid, "mcp")
        await decide(r, pid, IG)
        await ended(r, pid)
        return r, cp, pid, first, stopped, second
    r, cp, pid, first, stopped, second = asyncio.run(scenario())
    assert first["retrying"] == ["Instagram"] and first["heads_up"][0]["level"] == "warn"
    assert "TikTok saves its own copy of what it posts" in first["heads_up"][0]["text"] and "send_to_phone" in first["heads_up"][0]["text"]
    assert stopped[0] == {"Instagram": "failed", "YouTube": "done", "TikTok": "done"}
    assert f"saved by {TT}" in stopped[1] and stopped[2] is None  # stopped before its first step: nothing posted
    assert second["retrying"] == ["Instagram"]
    assert statuses(cp, pid) == {"Instagram": "done", "YouTube": "done", "TikTok": "done"} and POSTS == {IG: 1, YT: 1, TT: 1}


def test_a_retry_that_runs_tiktok_too_keeps_it_last():
    PLAN.update({IG: ["fail", "post"], TT: ["fail", "post"]})

    async def scenario():
        r, cp = make()
        pid = cp.start(posts(TT, IG), "mcp")["id"]
        await ended(r, pid)
        again = cp.retry(pid, "mcp")
        await decide(r, pid, IG)
        await decide(r, pid, TT)
        await ended(r, pid)
        return r, pid, again
    r, pid, again = asyncio.run(scenario())
    assert again["retrying"] == ["Instagram", "TikTok"] and "heads_up" not in again  # TikTok hadn't posted: nothing to say
    assert [p["app"] for p in kids(r, pid)] == [IG, TT, IG, TT] and POSTS == {IG: 1, TT: 1}


def test_two_posts_in_one_app_are_told_apart_by_their_routines():
    async def scenario():
        r, cp = make()
        story = Post("instagram_story_poll", IG, "Instagram", "Post a story with a poll", {"poll_question": "Which?"})
        pid = cp.start([*posts(IG), story, *posts(TT)], "mcp")["id"]
        await decide(r, pid, IG)
        await decide(r, pid, IG, yes=False)
        await decide(r, pid, TT)
        await ended(r, pid)
        parent = r.store.get(pid)
        again = cp.retry(pid, "mcp")
        await decide(r, pid, IG, yes=False)
        await ended(r, pid)
        return parent, again
    parent, again = asyncio.run(scenario())
    assert parent["goal"] == "Post to Instagram (instagram_reel_song), Instagram (instagram_story_poll) and TikTok"
    assert parent["result"] == "Instagram (instagram_reel_song): done · Instagram (instagram_story_poll): not posted (declined) · TikTok: done"
    assert again["retrying"] == ["Instagram (instagram_story_poll)"] and POSTS == {IG: 1, TT: 1}


def test_a_declined_post_is_not_posted_and_the_parent_says_what_a_retry_would_run():
    async def scenario():
        r, cp = make()
        pid = cp.start(posts(IG, TT), "mcp")["id"]
        await decide(r, pid, IG)
        await decide(r, pid, TT, yes=False)
        await ended(r, pid)
        return r, cp, pid
    r, cp, pid = asyncio.run(scenario())
    parent = r.store.get(pid)
    assert statuses(cp, pid) == {"Instagram": "done", "TikTok": "declined"} and POSTS == {IG: 1}
    assert parent["status"] == "declined" and parent["detail"] == "Not posted: TikTok (declined); a retry runs only TikTok"
    assert parent["result"] == "Instagram: done · TikTok: not posted (declined)"


def test_the_parent_waits_on_the_user_while_a_post_waits_for_its_approval():
    async def scenario():
        r, cp = make()
        pid = cp.start(posts(IG, TT), "mcp")["id"]
        await until(lambda: r.store.get(pid)["status"] == "waiting_approval")
        seen = r.store.get(pid)
        await decide(r, pid, IG)
        await decide(r, pid, TT)
        await ended(r, pid)
        return seen
    seen = asyncio.run(scenario())
    assert seen["detail"].startswith("Instagram:") and seen["result"] == "Instagram: waiting for the user · TikTok: queued"


def test_stopping_the_cross_post_stops_its_part_and_runs_nothing_more():
    async def scenario():
        r, cp = make()
        pid = cp.start(posts(IG, TT), "mcp")["id"]
        await until(lambda: r.store.get(pid)["status"] == "waiting_approval" and r.store.approvals(status="pending"))
        part = kids(r, pid)[0]["id"]
        approver, asked = r.approvers[part], r.store.approvals(status="pending")[0]
        assert r.stop(pid)
        with pytest.raises(asyncio.CancelledError):
            await r.jobs[pid]
        await asyncio.gather(r.jobs[part], return_exceptions=True)
        stopped = (r.store.get(pid)["status"], r.store.get(part)["status"])
        result = r.store.get(pid)["result"]
        approver.decide(asked["id"], True, by="test")  # a yes after the stop reaches nothing: the part is gone
        await asyncio.sleep(0.1)
        return r, cp, pid, stopped, result
    r, cp, pid, stopped, result = asyncio.run(scenario())
    assert stopped == ("stopped", "stopped")
    assert statuses(cp, pid) == {"Instagram": "failed", "TikTok": "not_started"} and POSTS == {}  # not "unknown": no tap ran
    # The parent's own line says how each ended, not how it looked at the stop (Pixel, Nov 2: "YouTube: waiting for the user")
    assert result == "Instagram: not posted (failed) · TikTok: not posted (never started)"
    # TikTok never started, and nothing will start it now: a retry runs it (Pixel, Nov 2: the search sat at "queued")
    assert [row["label"] for row in cp.view(pid) if row["status"] in RETRYABLE] == ["Instagram", "TikTok"]


def test_outcomes_hold_after_a_restart_from_the_store_alone():
    PLAN.update({TT: ["post_then_timeout"], YT: ["fail"]})

    async def scenario():
        r, cp = make()
        pid = cp.start(posts(IG, TT, YT), "mcp")["id"]
        await decide(r, pid, IG)
        await decide(r, pid, TT)
        await ended(r, pid)
        fresh = TaskRunner(r.store, EventBus(), Pool(), MemoryStore(":memory:"), SimpleNamespace(), adapter=SimpleNamespace())
        fresh.loop = asyncio.get_running_loop()
        return statuses(CrossPost(fresh), pid)
    assert asyncio.run(scenario()) == {"Instagram": "done", "TikTok": "unknown", "YouTube": "failed"}


# ---- the MCP tool ------------------------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path, monkeypatch):
    e = make_env(tmp_path, monkeypatch)
    for name in ROUTINE.values():
        shutil.copytree(LIB / name, e.ctx.routines.root / name)
        e.ctx.sharing.set(name, True)
    e.started = []

    def start(posts, source, phone=None):
        e.started.append((posts, source, phone))
        return {"id": "task-cp", "status": "queued"}
    e.ctx.crosspost = SimpleNamespace(start=start, is_crosspost=lambda pid: pid == "task-cp", view=lambda pid: [])
    return e


def args(**inputs) -> list[dict]:
    return [{"routine": "instagram_reel_song", "inputs": {"song_title": "golden hour", "song_artist": "JVKE", "caption": "one clip"}},
            {"routine": "tiktok_post_sound", "inputs": {"sound_title": "golden hour", "sound_artist": "JVKE", "caption": "one clip"}},
            {"routine": "youtube_short_sound", "inputs": {"sound_title": "golden hour", "sound_artist": "JVKE", "short_title": "one clip"},
             **inputs}]


def test_cross_post_is_a_tool_that_returns_its_task_at_once(env):
    with TestClient(env.ctx.asgi) as c:
        tools = listed(c)
        err, text = called(c, "cross_post", {"posts": args()})
    t = tools["cross_post"]
    assert {"posts", "retry", "phone"} <= set(t["inputSchema"]["properties"])
    assert "outcome unknown" in t["description"] and "waits for the user's OK in Envoy" in t["description"]
    assert not err, text
    got = json.loads(text)
    assert got["task_id"] == "task-cp" and [p["app"] for p in got["posts"]] == ["Instagram", "YouTube", "TikTok"]  # TikTok last
    (chosen, source, phone), = env.started
    assert [p.routine for p in chosen] == [ROUTINE[IG], ROUTINE[YT], ROUTINE[TT]] and source == "mcp" and phone is None
    assert chosen[1].inputs == {"sound_title": "golden hour", "sound_artist": "JVKE", "short_title": "one clip"}
    assert chosen[2].app == TT and chosen[2].app_name == "TikTok"


@pytest.mark.parametrize("posts, says", [
    ([{"routine": "instagram_story_poll", "inputs": {}}], "isn't a routine the user shares with agents"),
    ([args()[0], args()[0]], "named twice"),
    ([{"routine": "tiktok_post_sound", "inputs": {"sound_title": "x", "sound_artist": "y", "caption": "z", "song": "q"}}], "has no input song"),
    ([{"routine": "tiktok_post_sound", "inputs": {"sound_title": "x", "sound_artist": "y"}}], "needs caption"),
    ([], "posts is empty"),
    (args() + [args()[0]] + [args()[1]], "at most 4"),
])
def test_cross_post_checks_every_destination_before_anything_starts(env, posts, says):
    with TestClient(env.ctx.asgi) as c:
        err, text = called(c, "cross_post", {"posts": posts})
    assert says in text and env.started == []


def test_cross_post_takes_posts_or_a_retry_and_get_task_shows_each_destination(env):
    env.ctx.crosspost.view = lambda pid: [{"app_name": "Instagram", "status": "done"}, {"app_name": "TikTok", "status": "failed"}]
    env.ctx.crosspost.retry = lambda pid, source: {"retrying": ["TikTok"], "left_alone": [{"app": "Instagram", "status": "done"}]}
    task = env.ctx.tasks.create("Post to Instagram and TikTok", "mcp", kind="crossapp")
    env.ctx.crosspost.is_crosspost = lambda pid: pid == task["id"]
    with TestClient(env.ctx.asgi) as c:
        neither = called(c, "cross_post", {})
        both = called(c, "cross_post", {"posts": args(), "retry": task["id"]})
        other = called(c, "cross_post", {"retry": "task-nope"})
        again = json.loads(called(c, "cross_post", {"retry": task["id"]})[1])
        seen = json.loads(called(c, "get_task", {"task_id": task["id"]})[1])
    assert all("give posts" in t for _, t in (neither, both)) and "no cross-post task-nope" in other[1]
    assert again["retrying"] == ["TikTok"] and again["task_id"] == task["id"]
    assert seen["posts"][1] == {"app_name": "TikTok", "status": "failed"}
    assert seen["retry"] == f"cross_post with retry={task['id']} runs only TikTok again"
