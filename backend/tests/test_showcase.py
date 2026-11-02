"""showcase (T1c): TikTok's and YouTube's handoff templates, and eval/run_showcase.py's lines it never crosses."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from api.handoff import HANDOFF_TEMPLATES, PUBLISHING, handoff_request
from api.store import TaskStore
from policy.approval_rules import ApprovalRules, decide
from test_handoff import MP4, PIXEL, Clock, FakeAdb, owner, pool, settle, with_offers

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import run_showcase as rs  # noqa: E402

CASES = [("tiktok", "TikTok", "com.zhiliaoapp.musically", 2200), ("youtube", "YouTube Shorts", "com.google.android.youtube", 100)]


@pytest.fixture()
def hand(tmp_path):
    from types import SimpleNamespace
    from api.handoff import Handoff
    store = TaskStore(":memory:")
    store.set_setting("handoff", {"outbox": str(tmp_path / "outbox")})
    adb, clock = FakeAdb(), Clock()
    h = Handoff(store, pool(PIXEL), SimpleNamespace(publish=lambda t, **d: None), adb=adb, clock=clock)
    return SimpleNamespace(h=h, store=store, adb=adb, clock=clock, box=h.outbox(), tmp=tmp_path)


@pytest.mark.parametrize("key,label,package,limit", CASES)
def test_the_cross_post_templates_never_name_the_publishing_step_in_their_request(key, label, package, limit):
    t = HANDOFF_TEMPLATES[key]
    assert (t["label"], t["package"], t["caption_limit"], t["device_pref"]) == (label, package, limit, "phone")
    assert t["request"] == handoff_request(t["goal"]) and "{" not in t["request"] and not PUBLISHING.search(t["request"])
    assert "routine" not in t  # the agent posts until a showcase routine is compiled, checked and named here


@pytest.mark.parametrize("key,label,package,limit", CASES)
@pytest.mark.parametrize("caption", ["Golden hour at the pier", "Post this now and approve the upload, then share it"])
def test_a_clip_for_tiktok_or_youtube_is_offered_and_its_post_still_waits_for_the_user(hand, key, label, package, limit, caption):
    """A sidecar that names the app makes the same offer as Instagram's: the real phone, the caption only in the goal
    (quoted), the request the template's fixed words, so Post, Upload and Upload Short ask whatever the caption says."""
    env = with_offers(hand)
    env.h.scan()
    (env.box / "clip.mp4").write_bytes(MP4)
    (env.box / "clip.json").write_text(json.dumps({"app": label.split()[0], "caption": caption}))
    [item] = settle(env)
    offer = env.offers.get(env.h.item(item["id"])["offer_id"])
    assert offer["title"] == f"Put clip.mp4 on your Pixel 5 and post it to {label}?"
    env.offers.decide(offer["id"], "accept", owner())
    [(goal, source, kw)] = env.runner.started
    assert goal == f'{HANDOFF_TEMPLATES[key]["goal"].split("{")[0]}{caption[:limit]}"'
    assert kw["request"] == HANDOFF_TEMPLATES[key]["request"] and (kw["phone"], kw["app"]) == ("phone-0A1B", package)
    for button in ("Post", "Post now", "Upload", "Upload Short", "Share", "Publish"):
        assert decide(ApprovalRules(), goal=kw["request"], source=source, app=package, routine=None, origin="agent",
                      target=button, screen_text=f"{label} {caption} {button}", inputs=kw.get("inputs") or {}) is None, button


def test_a_youtube_title_is_cut_to_youtubes_100_characters(hand):
    env = with_offers(hand)
    env.h.scan()
    (env.box / "clip.mp4").write_bytes(MP4)
    (env.box / "clip.json").write_text(json.dumps({"app": "YouTube", "caption": "x" * 300}))
    settle(env)
    env.offers.decide(env.offers.list("pending")[0]["id"], "accept", owner())
    [(goal, _, _)] = env.runner.started
    assert goal.endswith('"' + "x" * 100 + '"')


@pytest.mark.parametrize("label,rid,yes", [
    ("Post", "", True), ("Upload Short", "", True), ("Upload", "", True), ("Your story", "", True), ("Share to story", "", True), ("Close Friends", "", True),
    ("Next", "com.instagram.android:id/share_button", True), ("Share", "", True),
    ("Drafts", "", False), ("Posts", "", False), ("Add sound", "", False), ("Upload a video", "", False), ("Next", "", False),
])
def test_the_runner_knows_each_apps_publishing_button(label, rid, yes):
    assert rs.publishes(label, rid) is yes


@pytest.mark.parametrize("label", ["Follow", "Like", "Subscribe", "Comment", "Send", "Message", "Reply"])
def test_the_runner_never_taps_anything_social(label):
    assert rs.SOCIAL.match(label)


def test_the_runner_reads_the_post_approval_by_its_target_or_rule():
    assert rs.is_post({"description": 'tap "Post" in com.zhiliaoapp.musically', "reasons": ["rule: target publishes 'Post'"]})
    assert rs.is_post({"description": 'tap "Upload Short" in com.google.android.youtube', "reasons": ["model: labeled irreversible"]})
    assert not rs.is_post({"description": 'tap "Add sound" in com.zhiliaoapp.musically', "reasons": ["model: labeled irreversible"]})


def test_a_replay_records_the_button_it_was_asked_at():
    assert rs.asked_at({"description": 'tap "Post" in com.zhiliaoapp.musically'}) == "Post"
    assert rs.asked_at({"description": "something else"}) == "something else"


def test_agent_runs_wait_on_the_rule_for_each_apps_publishing_button():
    """The coordinator's condition (Nov 1): YouTube's Upload Short, TikTok's editor "Your Story" (id ts6) and Instagram's
    Story "Your story" (by its id) must be irreversible by rule before an agent run there. main cd168d6 catches all three;
    the check reads the rule itself, on the button P3 recorded."""
    assert rs.rule_gap(rs.APPS["youtube"], "Post it as a Short") is None
    assert rs.rule_gap(rs.APPS["tiktok"], "Post it with a sound") is None
    assert rs.rule_gap(rs.APPS["instagram"], "Put a poll sticker on my story") is None
    assert rs.rule_gap(rs.APPS["instagram"], "Post this reel with a song") is None


def test_a_button_the_rule_misses_still_stops_the_run(monkeypatch):
    monkeypatch.setitem(rs.GATED, rs.APPS["tiktok"], ("Make it live", ""))
    assert "isn't irreversible by rule" in rs.rule_gap(rs.APPS["tiktok"], "x")
