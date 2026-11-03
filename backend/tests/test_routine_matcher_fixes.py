"""Routine and matcher fixes (Oct 28): a close call between two routines runs neither, Amazon's outputs are read by the
result row they belong to, Play's listing opens for an app the learned list didn't show, and an output a page draws
without an accessibility tree (Chrome's Wikipedia) is read from the screenshot under one check, at compile time and on
every rerun.

tests/traces/routine_fixes holds envoy-real recordings: the Phase 7 Amazon and Play Store traces with Wonder's cached
compile answers, Amazon's results for "USB-C cable" (a second input, whose first rows differ in shape), Play's Search tab
(the suggestions that showed Duolingo), the Chrome Wikipedia trace whose article page has no tree (its last
screenshot shrunk; the account's address replaced), and the DoorDash first-restaurant routine Phase 7 compiled
(doordash_search.yaml).
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import routines.executor as executor_mod
from agent.trace import TraceWriter
from devices.screen import build_state
from devices.types import ActionResult
from models.schemas import CompiledRoutine, MatchOutput, ScreenReadOutput
from policy.approvals import ScriptedApprover
from routines import screen_read
from routines.compiler import NotCompilable, compile_trace, load_trace, screen_only
from routines.executor import ExecConfig, RoutineExecutor, extract_value
from routines.matcher import RoutineMatcher
from routines.model import Extract, Routine, load_yaml
from routines.screens import load_tree
from routines.store import RoutineStore

HERE = Path(__file__).parent
REPO = HERE.parents[1]
FX = HERE / "traces" / "routine_fixes"
FAST = ExecConfig(pre_timeout_s=0.6, post_timeout_s=0.6, stable_s=0.2, poll_s=0.01, patch_screenshots=False)


@pytest.fixture(autouse=True)
def traces_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_mod, "TraceWriter", lambda tid: TraceWriter(tid, root=tmp_path))


class NoModel:
    def call(self, *a, **kw):
        raise AssertionError("no model call expected")


def compiled(trace: str, spec: str) -> Routine:
    d = FX / trace
    routine, _ = asyncio.run(compile_trace(d, adapter=NoModel(), spec=CompiledRoutine.model_validate_json((d / spec).read_text())))
    return routine


# ---- 1. the matcher on a vague request ------------------------------------------------------------------------------

class Picks:
    """The match model, confidently choosing `routine` (as it chose the first-restaurant routine for the latte)."""

    def __init__(self, routine: str, inputs: dict[str, str]) -> None:
        self.routine, self.inputs = routine, inputs

    def call(self, job, content, **kw):
        from models.schemas import InputValue
        out = MatchOutput(routine=self.routine, confident=True,
                          inputs=[InputValue(name=k, value=v, source="request") for k, v in self.inputs.items()])
        return SimpleNamespace(parsed=out, cost_usd=0.0, cost_at_standard_usd=0.0)


def doordash_store(tmp_path: Path) -> RoutineStore:
    """The DoorDash first-restaurant routine Phase 7 compiled, and a menu-item price routine next to it. The routine is a
    pinned copy (eval/results/final/real_compiled/doordash_search.yaml at e18e434): the final evaluation recompiled it."""
    search = load_yaml((FX / "doordash_search.yaml").read_text())
    price = search.model_copy(update={
        "routine": "doordash_get_item_price", "intent": "Get the price of a menu item on DoorDash",
        "description": "Searches DoorDash for a menu item and returns its price at the first store that has it.",
        "patterns": ["price of an item on DoorDash", "how much is this on DoorDash", "what does this cost on DoorDash"],
        "outputs": ["item_price"]})
    store = RoutineStore(tmp_path / "routines")
    for r in (search, price):
        store.add(r.model_copy(update={"status": "active"}))
    return store


def test_a_vague_request_between_two_close_routines_runs_neither(tmp_path):
    store = doordash_store(tmp_path)
    m = asyncio.run(RoutineMatcher(store, Picks("doordash_search_restaurants", {"search_query": "Caffè Latte"}))
                    .match("a Caffè Latte on DoorDash"))
    assert m.routine is None and m.model_calls == 1
    assert set(m.ambiguous) == {"doordash_search_restaurants", "doordash_get_item_price"}
    assert m.stage.startswith("close call")


def test_a_request_that_names_what_it_wants_still_runs_the_routine(tmp_path):
    store = doordash_store(tmp_path)
    price = asyncio.run(RoutineMatcher(store, Picks("doordash_get_item_price", {"search_query": "Caffè Latte"}))
                        .match("what's the price of a Caffè Latte on DoorDash"))
    assert price.routine is not None and price.routine.routine == "doordash_get_item_price" and not price.ambiguous
    first = asyncio.run(RoutineMatcher(store, Picks("doordash_search_restaurants", {"search_query": "pizza"}))
                        .match("what's the first restaurant DoorDash shows for pizza"))
    assert first.routine is not None and first.routine.routine == "doordash_search_restaurants"
    assert first.inputs == {"search_query": "pizza"}


def test_the_skylark_matching_set_has_no_close_calls():
    """Two ways to check in report the same thing, and a paraphrase scores below the floor: the model's pick stands."""
    from routines.matcher import close_call
    store = RoutineStore(REPO / "data" / "routines")
    if not store.active():
        pytest.skip("no SkyLark routines in this checkout")
    m = RoutineMatcher(store, NoModel())
    for request, family in [("Check me in for my Denver flight", "check_in"), ("Check me in", "check_in"),
                            ("Which gate is my Boise flight at?", "gate"), ("Is SL 1190 on time?", "flight_status"),
                            ("Change my seat to 22A", "change_seat")]:
        cands = m.shortlist(request)
        for chosen in [r for r, _ in cands if family in r.routine]:
            assert close_call(request, chosen, cands) is None, (request, chosen.routine)


# ---- 2a. Amazon: outputs read in their result row -------------------------------------------------------------------

def test_amazon_reads_the_first_result_and_its_price_from_one_row():
    r = compiled("amazon_trace", "amazon.spec.json")
    ex = r.steps[-1].extract
    assert ex["first_result_product"].first_row and ex["first_result_product"].below == "Results"
    assert ex["first_result_price"].row_of == "first_result_product" and not ex["first_result_price"].first_in_list
    learned = load_tree(FX / "amazon_trace" / "screens" / "003_before.json.gz")
    out = {n: extract_value(e, learned, {"search_query": "aa batteries"}, ex) for n, e in ex.items()}
    assert "Energizer MAX AA Batteries" in out["first_result_product"] and out["first_result_price"] == "$19.44"


def test_amazon_on_a_new_search_does_not_mix_two_rows():
    """USB-C cable: the first price in the list ($9.99, a 2-pack) used to be reported with the product under it
    (XIAWAO, $8.49 in a "Limited time deal" row of another shape). Now both come from the first row under Results."""
    ex = compiled("amazon_trace", "amazon.spec.json").steps[-1].extract
    s = load_tree(FX / "amazon_usbc_results.json.gz")
    out = {n: extract_value(e, s, {"search_query": "USB-C cable"}, ex) for n, e in ex.items()}
    assert out["first_result_product"].startswith("Anker USB C to USB C Cable, 60W") and out["first_result_price"] == "$9.99"
    # And the deal row's own price is read from its row, whatever its shape.
    xiawao = "Sponsored Ad - XIAWAO USB C Cable 6 Pack, Braided USB A to Type C Cord Fast Charging"
    assert executor_mod.in_row(xiawao, r"\$\d+\.\d+", s) == "$8.49"


# ---- 2b. Play Store: the listing opens for any app ------------------------------------------------------------------

def test_play_input_is_what_the_user_said_not_the_listing_title():
    r = compiled("play_trace", "play_rating.spec.json")
    assert r.inputs["app_name"].example == "Duolingo"  # Wonder had "Duolingo: Learn Languages": a new app never matched


class Play:
    """Play's Search tab as recorded (its suggestions show Duolingo, not Wikipedia); tapping "Search or ask Play" opens
    the search field, and typing an app and pressing Enter shows its results."""

    def __init__(self) -> None:
        self.at, self.acts = "tab", []
        results = build_state((HERE / "screens" / "playstore_search.xml").read_text(), "com.android.vending",
                              "com.android.vending.AssetBrowserActivity", 1080, 2400)
        self.screens = {"tab": load_tree(FX / "play_search_tab.json.gz"), "field": results, "results": results}

    async def observe(self, screenshot: bool = False):
        return self.screens[self.at]

    async def act(self, a):
        el = self.screens[self.at].numbered[a.element - 1] if a.element else None
        self.acts.append((a.kind, el.label if el else None, a.text))
        if self.at == "tab" and a.kind == "tap" and el is not None and el.label == "Search or ask Play":
            self.at = "field"
        elif self.at == "field" and a.kind == "type" and a.submit:
            self.at = "results"
        return ActionResult(ok=True, duration_ms=1.0)


def test_play_searches_for_an_app_its_suggestions_do_not_show():
    r = compiled("play_trace", "play_rating.spec.json")
    find = r.model_copy(update={"steps": [r.steps[r.step_index("find_open_app_listing")]], "outputs": [], "done": []})
    phone = Play()
    ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    out = asyncio.run(ex.run(find, {"app_name": "Wikipedia"}, launch="never", allow_agent=False, allow_repair=False))
    assert out.status == "done", out.detail
    assert ("tap", "Search or ask Play", None) in phone.acts and ("type", "", "Wikipedia") in [(k, "", t) for k, _, t in phone.acts]
    assert out.model_calls == 0


class Still:
    """One screen that never changes; records every action."""

    def __init__(self, screen) -> None:
        self.screen, self.acts = screen, []

    async def observe(self, screenshot: bool = False):
        return self.screen

    async def act(self, a):
        self.acts.append(a)
        return ActionResult(ok=True, duration_ms=1.0)


def test_a_list_choice_never_types_into_a_field_that_is_not_a_search_box():
    """SkyLark's My Trips has a find-a-trip form (confirmation code, last name) above the list. Searching typed the trip's
    city into the code field and pressed Enter on every past_trip run (~10 s each). On a screen with a message or comment
    box, Enter could send it."""
    trips = build_state((HERE / "screens" / "skylark_trips.xml").read_text(), "com.skylark.air",
                        "com.skylark.air.MainActivity", 1080, 2400)
    assert [e for e in trips.numbered if e.editable]  # the form's fields are there
    phone = Still(trips)
    ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    assert asyncio.run(ex._search_for(None, "Detroit", trips, executor_mod.StepRun("find_trip"))) is False
    assert phone.acts == []


def test_play_does_not_search_when_the_list_shows_the_app():
    r = compiled("play_trace", "play_rating.spec.json")
    find = r.model_copy(update={"steps": [r.steps[r.step_index("find_open_app_listing")]], "outputs": [], "done": []})
    phone = Play()
    ex = RoutineExecutor(phone, adapter=NoModel(), approver=ScriptedApprover(approve=False), config=FAST)
    out = asyncio.run(ex.run(find, {"app_name": "Duolingo"}, launch="never", allow_agent=False, allow_repair=False))
    assert out.status == "done" and not [a for a in phone.acts if a[0] == "type"]


# ---- 3. Chrome / Wikipedia: an output read from the screenshot ------------------------------------------------------

class Reads:
    """The screen_read model: answers in order."""

    def __init__(self, *answers: ScreenReadOutput) -> None:
        self.answers, self.calls = list(answers), []

    def call(self, job, content, **kw):
        self.calls.append(job)
        assert job == "screen_read" and any(p.get("type") == "input_image" for p in content)
        return SimpleNamespace(parsed=self.answers.pop(0), cost_usd=0.001, cost_at_standard_usd=0.001)


EIFFEL = ScreenReadOutput(found=True, page_title="Eiffel Tower", quote="Opened 15 May 1889; 136 years ago", value="15 May 1889")
CHROME_SPEC = CompiledRoutine.model_validate({
    "name": "chrome_wikipedia_opening_year", "intent": "Find when a landmark opened on Wikipedia",
    "description": "Opens Wikipedia in Chrome, searches for the landmark and reads when it opened.",
    "patterns": ["when did this landmark open", "what year did it open"],
    "inputs": [{"name": "landmark", "type": "text", "description": "The landmark", "example": "Eiffel Tower", "from_memory": None}],
    "steps": [], "outputs": [{"name": "opened", "near": "Opened", "example": "15 May 1889"}], "data_values": []})


def test_a_run_unverified_only_for_lack_of_a_tree_can_compile(tmp_path):
    d = tmp_path / "chrome"
    shutil.copytree(FX / "chrome_trace", d)
    run, _ = load_trace(d)  # no NotCompilable: the answer is on the screenshot, not missing
    assert run["status"] == "done_unverified" and screen_only(d, run)
    # An unverified run whose last screen has a tree is still refused: the check could look, and didn't find it.
    amazon = tmp_path / "amazon"
    shutil.copytree(FX / "amazon_trace", amazon)
    other = {**json.loads((amazon / "run.json").read_text()), "status": "done_unverified",
             "check": {"passed": False, "detail": "none of ['x'] is visible on the current screen"}}
    (amazon / "run.json").write_text(json.dumps(other))
    assert not screen_only(amazon, other)
    with pytest.raises(NotCompilable):
        load_trace(amazon)


def test_the_compiler_keeps_a_screenshot_output_only_if_the_recorded_screenshot_reads_the_answer(tmp_path):
    d = tmp_path / "chrome"
    shutil.copytree(FX / "chrome_trace", d)
    r, rep = asyncio.run(compile_trace(d, adapter=Reads(EIFFEL), spec=CHROME_SPEC))
    ex = r.steps[-1].extract["opened"]
    assert r.outputs == ["opened"] and ex.from_screenshot == screen_read.shape_of("15 May 1889") and rep.model_calls == 1
    wrong = ScreenReadOutput(found=True, page_title="Eiffel Tower", quote="Height 330 m (1,083 ft)", value="330 m")
    # "… tell me the year it opened" is a question: with its only output dropped, nothing is compiled (Oct 31; before, a
    # routine that answered nothing was kept).
    with pytest.raises(NotCompilable, match="opened.*dropped"):
        asyncio.run(compile_trace(d, adapter=Reads(wrong), spec=CHROME_SPEC))


def test_every_screenshot_read_passes_the_same_check():
    shape, eiffel = screen_read.shape_of("15 May 1889"), {"landmark": "Eiffel Tower"}
    assert screen_read.accept(EIFFEL, shape, eiffel)[0] == "15 May 1889"
    liberty = ScreenReadOutput(found=True, page_title="Statue of Liberty", quote="Dedicated October 28, 1886", value="October 28, 1886")
    assert screen_read.accept(liberty, shape, {"landmark": "Statue of Liberty"})[0] == "October 28, 1886"
    assert screen_read.accept(liberty, shape, eiffel)[0] is None  # the wrong page
    assert screen_read.accept(EIFFEL.model_copy(update={"value": "Gustave Eiffel"}), shape, eiffel)[0] is None  # not a date
    assert screen_read.accept(EIFFEL.model_copy(update={"quote": "Height 330 m"}), shape, eiffel)[0] is None  # not quoted
    assert screen_read.accept(ScreenReadOutput(found=False, page_title="", quote="", value=""), shape, eiffel)[0] is None


class Browser:
    """A page with no tree: the screenshot is all there is. Scrolling moves to the next screenshot."""

    def __init__(self) -> None:
        self.screen = load_tree(FX / "chrome_trace" / "screens" / "013_before.json.gz")
        self.acts = []

    async def observe(self, screenshot: bool = False):
        return self.screen

    async def screenshot(self):
        return (FX / "chrome_trace" / "screens" / "013_before.png").read_bytes()

    async def act(self, a):
        self.acts.append(a.kind)
        return ActionResult(ok=True, duration_ms=1.0)


def test_the_executor_reads_the_screenshot_and_scrolls_until_the_answer_is_there():
    routine = Routine.model_validate({
        "routine": "chrome_read", "app": "com.android.chrome", "intent": "read", "description": "read", "start": "current_screen",
        "outputs": ["opened"], "inputs": {"landmark": {"type": "text", "description": "x", "example": "Eiffel Tower"}},
        "steps": [{"id": "read", "intent": "read", "action": {"kind": "wait", "seconds": 0.01},
                   "extract": {"opened": Extract(near="Opened: when did {{landmark}} open?", from_screenshot=screen_read.shape_of("15 May 1889")).model_dump()}}]})
    not_yet = ScreenReadOutput(found=False, page_title="Eiffel Tower", quote="", value="")
    phone, model = Browser(), Reads(not_yet, EIFFEL)
    ex = RoutineExecutor(phone, adapter=model, approver=ScriptedApprover(approve=False), config=FAST)
    out = asyncio.run(ex.run(routine, {"landmark": "Eiffel Tower"}, launch="never", allow_agent=False, allow_repair=False))
    assert out.status == "done", out.detail
    assert out.outputs == {"opened": "15 May 1889"} and model.calls == ["screen_read"] * 2 and "scroll" in phone.acts
    # A read that fails the check is not an answer: the run fails rather than report it.
    wrong = ScreenReadOutput(found=True, page_title="Statue of Liberty", quote="Dedicated October 28, 1886", value="October 28, 1886")
    ex2 = RoutineExecutor(Browser(), adapter=Reads(*[wrong] * 7), approver=ScriptedApprover(approve=False), config=FAST)
    out2 = asyncio.run(ex2.run(routine, {"landmark": "Eiffel Tower"}, launch="never", allow_agent=False, allow_repair=False))
    assert out2.status != "done" and not out2.outputs.get("opened")


def test_a_badge_above_the_first_result_is_not_its_title():
    """envoy-real, a later "USB-C cable" search: "Featured from Amazon brands" sits above the first result's title."""
    ex = compiled("amazon_trace", "amazon.spec.json").steps[-1].extract
    s = load_tree(FX / "amazon_usbc_featured.json.gz")
    out = {n: extract_value(e, s, {"search_query": "USB-C cable"}, ex) for n, e in ex.items()}
    assert out["first_result_product"].startswith("Sponsored Ad - Amazon Official USB- C") and out["first_result_price"] == "$14.99"


def test_play_reads_the_rating_after_the_row_that_names_the_app():
    """Play's search shows sponsored apps' ratings first (Pandora 3.9 above Spotify): the rating is read after the row
    naming the asked-for app, and the search box that shows only the term is never that row."""
    r = compiled("play_trace", "play_rating.spec.json")
    assert r.steps[-1].extract["star_rating"].card == "{{app_name}}"
    results = build_state((HERE / "screens" / "playstore_search.xml").read_text(), "com.android.vending",
                          "com.android.vending.AssetBrowserActivity", 1080, 2400)
    m = executor_mod.list_choice(r.steps[-1].action.target, results, {"app_name": "Wikipedia"}, 0.7)
    assert m.ok and m.element.in_list and "Wikipedia" in m.element.label
