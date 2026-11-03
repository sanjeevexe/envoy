"""B1's driver (eval/showcase_batch.py) follows eval/results/showcase-batch/PROTOCOL.md: the fixed schedule and inputs,
and the outcome taxonomy taken in the protocol's order, with the outcome checks reported beside it."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import showcase_batch as sb  # noqa: E402


def test_the_schedule_is_the_protocols_interleaved_order_with_its_states():
    assert len(sb.ORDER) == 40 and sb.ORDER[:4] == ["R01", "T01", "S01", "P01"] and sb.ORDER[-1] == "P10"
    assert [sb.STATES[n] for n in range(1, 11)] == ["cold", "open", "draft", "cold", "open", "draft", "cold", "open", "draft", "cold"]
    assert sb.attempt("R01")["inputs"] == {"song_title": "golden hour", "song_artist": "JVKE", "caption": "Envoy batch R01 · test"}
    assert sb.attempt("S07")["inputs"] == {"sound_title": "Flowers", "sound_artist": "Miley Cyrus", "short_title": "Envoy batch S07 · test"}
    assert sb.attempt("P03")["inputs"] == {"poll_question": "Envoy batch P03: which one?", "poll_option_1": "Beach", "poll_option_2": "Mountains"}
    assert sb.attempt("T09", {9: "Save Your Tears"})["inputs"]["sound_title"] == "Save Your Tears"  # a recorded swap, same artist


def _rec(w: str, *, asked=("Share",), ok=True, rungs=(0,), notes=(), checks=None, status="declined", interventions=(), approved=False):
    a = sb.attempt(f"{w}01")
    steps = [{"id": f"s{i}", "status": "agent" if r >= 5 else "done", "rung": r, "rungs": list(notes) if r >= 5 else []} for i, r in enumerate(rungs)]
    rp = {"asked_at": list(asked), "ok": ok, "routine_steps": steps, "task": {"status": status},
          "approvals": [{"status": "approved" if approved else "declined"}],
          "outcome_checks": [checks] if checks else []}
    return {**a, "replay": rp, "interventions": list(interventions)}


GOOD = {"picks": {"song_title": "shown"}, "fields": {"caption": "held"}, "clip": "checked", "problems": []}


def test_each_class_in_the_protocols_order():
    assert sb.classify({**sb.attempt("R01")}) == "outcome unknown"
    assert sb.classify(_rec("R", checks=GOOD)) == "no repair"
    assert sb.classify(_rec("R", rungs=(0, 1, 2, 3), checks=GOOD)) == "no repair"  # wait, relaxed, pop-up: still no repair
    assert sb.classify(_rec("R", rungs=(0, 4), checks=GOOD)) == "repair"
    assert sb.classify(_rec("R", rungs=(0, 6), notes=("full agent: …", "ask the user: agent failed: User declined the Share"))) == "agent fallback"
    assert sb.classify(_rec("R", rungs=(0, 6), notes=("ask the user: the screen never came",))) == "person stepped in"
    assert sb.classify(_rec("R", checks=GOOD, interventions=("[ 40.0s] task taken_over: you touched the phone",))) == "person stepped in"
    assert sb.classify(_rec("R", asked=(), ok=False)) == "failed"  # never asked at Share
    assert sb.classify(_rec("R", checks=GOOD, approved=True)) == "failed"
    wrong = {**GOOD, "clip": "checked", "problems": ["the gallery's newest video is x.mp4 …"]}
    assert sb.classify(_rec("R", checks=wrong)) == "failed"


def test_outcome_checks_say_yes_no_or_not_checkable_never_assume():
    rec = _rec("R", checks=GOOD)
    assert sb.outcome_checks(rec) == {"clip": "yes", "song": "yes", "caption": "yes", "poll": "n/a"}
    assert sb.outcome_checks(_rec("R")) == {"clip": "not checkable", "song": "not checkable", "caption": "not checkable", "poll": "n/a"}
    story = _rec("P", asked=("Your story",), checks={"picks": {}, "fields": {"poll_question": "not on the final screen"},
                                                     "clip": "checked", "problems": []})
    assert sb.outcome_checks(story) == {"clip": "yes", "song": "n/a", "caption": "n/a", "poll": "not checkable"}
    off = _rec("S", asked=("Upload Short",), checks={"picks": {"sound_title": "shown"}, "fields": {"short_title": "not on the final screen"},
                                                       "clip": "not checkable", "problems": []})
    assert sb.outcome_checks(off) == {"clip": "not checkable", "song": "yes", "caption": "not checkable", "poll": "n/a"}
