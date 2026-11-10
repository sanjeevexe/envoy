"""Agent changes from the Nov 2026 AndroidWorld round (docs/androidworld-results.md), offline: the step budget in every step,
a done on the last step, replans that know what was done, what a scroll did to the list, and which row an unlabeled
control belongs to."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent.loop import AgentRunner, RunConfig, _scroll_note
from agent.trace import TraceWriter
from devices.screen import build_state
from devices.types import Action, ActionResult
from models.prompts import PLAN_INSTRUCTIONS, STEP_INSTRUCTIONS, plan_input, step_input
from models.schemas import Plan, StepOutput, SuccessCheck
from policy.approvals import ScriptedApprover


def _attrs(clickable: bool = False, scrollable: bool = False) -> str:
    return (f'checkable="false" checked="false" enabled="true" focusable="false" focused="false" '
            f'scrollable="{str(scrollable).lower()}" long-clickable="false" password="false" selected="false" '
            f'clickable="{str(clickable).lower()}"')


def _node(text: str = "", rid: str = "", cls: str = "android.widget.TextView", bounds: str = "[0,0][1080,100]",
          clickable: bool = False, scrollable: bool = False, children: str = "", pkg: str = "com.example.music") -> str:
    rid = f"{pkg}:id/{rid}" if rid else ""
    return (f'<node index="0" text="{text}" resource-id="{rid}" class="{cls}" package="{pkg}" content-desc="" '
            f'{_attrs(clickable, scrollable)} bounds="{bounds}">{children}</node>')


def _screen(body: str, pkg: str = "com.example.music", activity: str = "Main"):
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
           + _node(cls="android.widget.FrameLayout", bounds="[0,0][1080,2400]", children=body, pkg=pkg) + "</hierarchy>")
    return build_state(xml, pkg, f"{pkg}.{activity}", 1080, 2400)


SONGS = [f"Song {i:02d}" for i in range(20)]
ROW_H = 100
LIST_TOP, LIST_BOTTOM = 400, 1400  # ten rows fit; a scroll drags 2 × 0.3 × 1000 = 600 px, six rows


def song_list(first: int, offset_px: int = 0):
    """The list scrolled so that row `first` starts at the top, with an extra shift in pixels (a partial scroll)."""
    rows = ""
    for i, title in enumerate(SONGS):
        y = LIST_TOP + (i - first) * ROW_H - offset_px
        if y + ROW_H <= LIST_TOP or y >= LIST_BOTTOM:
            continue
        rows += _node(cls="android.widget.LinearLayout", bounds=f"[0,{y}][1080,{y + ROW_H}]", children=(
            _node(title, rid="title", bounds=f"[0,{y}][900,{y + ROW_H}]", clickable=True)
            + _node(rid="menu", cls="android.widget.ImageButton", bounds=f"[900,{y}][1080,{y + ROW_H}]", clickable=True)))
    lst = _node(rid="recycler", cls="androidx.recyclerview.widget.RecyclerView", bounds=f"[0,{LIST_TOP}][1080,{LIST_BOTTOM}]",
                scrollable=True, children=rows)
    return _screen(_node("Songs", rid="toolbar_title", bounds="[0,200][1080,300]") + lst)


def test_an_unlabeled_control_in_a_list_row_says_which_row():
    s = song_list(0)
    line = next(l for l in s.compact.split("\n") if "(id: menu)" in l)
    assert line.endswith('(in row "Song 00")')  # was: [3] Button (id: menu), with nothing tying it to its song
    menu = next(e for e in s.numbered if e.resource_id.endswith("menu"))
    assert menu.label == "" and menu.row == "Song 00"  # policy, routines and checks still see no label
    # a clickable row that merges its children's text is the menu's row label
    row = _node(cls="android.widget.LinearLayout", bounds="[0,400][1080,500]", clickable=True, children=(
        _node("Golden Days", bounds="[0,400][700,500]") + _node(rid="more", cls="android.widget.ImageButton",
                                                               bounds="[900,400][1080,500]", clickable=True)))
    s2 = _screen(_node(rid="list", cls="android.widget.ListView", bounds="[0,400][1080,1400]", scrollable=True, children=row))
    assert '(id: more) (in row "Golden Days")' in s2.compact
    # outside a list, nothing changes
    s3 = _screen(_node(rid="settings", cls="android.widget.ImageButton", bounds="[0,200][100,300]", clickable=True))
    assert "in row" not in s3.compact
    # a "list" whose rows are whole pages (the home screen's pager) has no rows to speak of
    page = _node(cls="android.widget.FrameLayout", bounds="[0,200][1080,2200]", children=(
        _node(rid="search_card", cls="android.widget.ImageButton", bounds="[0,300][1080,500]", clickable=True)
        + _node("Gmail", bounds="[0,900][270,1100]", clickable=True)))
    s4 = _screen(_node(rid="workspace", cls="android.widget.ScrollView", bounds="[0,200][1080,2200]", scrollable=True, children=page))
    assert "(id: search_card)" in s4.compact and "in row" not in s4.compact


def test_a_scroll_says_how_many_new_items_came_into_view_and_when_the_list_ends():
    down = Action(kind="scroll", direction="down", element=2)
    a, b = song_list(0), song_list(6)
    assert next(e for e in a.numbered if e.number == 2).kind == "List"
    assert _scroll_note(a, b, down, True) == "6 new items came into view; there may be more"
    # the last page: the list could move only 4 rows of the 6 dragged
    c = song_list(10)
    assert _scroll_note(b, c, down, True) == "4 new items came into view; this is the end of the list (the list moved less than a full scroll)"
    # already at the end: nothing moved
    assert _scroll_note(c, c, down, False) == "the list did not move: it is already at the end of the list"
    up = Action(kind="scroll", direction="up", element=2)
    assert _scroll_note(c, c, up, False) == "the list did not move: it is already at the top of the list"
    assert _scroll_note(c, song_list(4), up, True) == "6 new items came into view; there may be more"
    # a swipe that moves the content like a scroll is reported the same way; a tap or another screen is not
    swipe = Action(kind="swipe", x=540, y=1300, x2=540, y2=700)
    assert _scroll_note(a, b, swipe, True) == "6 new items came into view; there may be more"
    assert _scroll_note(a, b, Action(kind="tap", element=3), True) is None
    other = _screen(_node("Settings", rid="other_title", bounds="[0,200][1080,300]"))
    assert _scroll_note(a, other, down, True) is None
    # items already seen earlier in the task are not new: back up to the top of a list read once
    from collections import Counter
    from agent.loop import _row_key, _rows
    seen = Counter(map(_row_key, _rows(a))) | Counter(map(_row_key, _rows(b)))
    assert _scroll_note(b, a, up, True, seen) == "0 new items came into view (10 you had already seen); there may be more"
    assert _scroll_note(a, b, down, True, Counter(map(_row_key, _rows(a)))) == "6 new items came into view (4 you had already seen); there may be more"
    # a view outside the list that comes and goes as it scrolls (a collapsing header) changes the signature, not the list
    b.signature = "another"
    assert _scroll_note(a, b, down, True) == "6 new items came into view; there may be more"


def test_the_step_prompt_explains_the_budget_and_the_last_step():
    assert "- STEPS LEFT: shown once the task is near its step limit" in STEP_INSTRUCTIONS
    assert "On the last step, say done if SCREEN or REMEMBERED shows the goal is done, or shows the complete answer" in STEP_INSTRUCTIONS
    assert "Never guess: if part of the goal or the answer is still unchecked, use fail and say what you found" in STEP_INSTRUCTIONS
    assert "STEPS LEFT" not in step_input("g", "s", step=5, max_steps=10)  # 6 left: not yet
    assert "STEPS LEFT: 5 of 10\n" in step_input("g", "s", step=6, max_steps=10)
    assert "STEPS LEFT: 1 of 10 (this is the last step)\n" in step_input("g", "s", step=10, max_steps=10)
    assert "STEPS LEFT" not in step_input("g", "s", step=1, max_steps=25)  # a real app's first step looks as it did
    assert "STEPS LEFT" not in step_input("g", "s")  # callers that give no budget (replays, the safety probe) are unchanged


def test_a_replan_is_told_what_was_done_and_kept():
    text = plan_input("Add three songs", "SCREEN", tried="Songs ×4", done_so_far="step 3: tap [14] → screen changed",
                      remembered="- Added Golden Days")
    assert "DONE SO FAR (the agent's actions in this task, oldest first):\nstep 3: tap [14] → screen changed" in text
    assert "REMEMBERED (what the agent kept from screens it left):\n- Added Golden Days" in text
    assert "DONE SO FAR" not in plan_input("Add three songs", "SCREEN", done_so_far="x")  # only with a replan
    assert "Never plan to redo finished work" in PLAN_INSTRUCTIONS


class Model:
    """Answers the plan, then the given step outputs in order (the last one repeats)."""

    def __init__(self, *steps: dict) -> None:
        self.steps, self.prompts, self.plan_prompts = list(steps), [], []

    def call(self, job, content, **kw):
        if job == "plan":
            self.plan_prompts.append(content[0]["text"])
            parsed = Plan(app=None, subgoals=["Open the app"], success_check=SuccessCheck(kind="text_visible", value="Saved", field_hint=None))
        else:
            self.prompts.append(content[0]["text"])
            parsed = StepOutput.model_validate(self.steps.pop(0) if len(self.steps) > 1 else self.steps[0])
        return SimpleNamespace(parsed=parsed, usage={}, cost_usd=0.0, cost_at_standard_usd=0.0)


def step(action: dict, remember: str = "") -> dict:
    return {"reason": "next", "action": action, "expected_result": "something", "risk": "read", "remember": remember}


class Songs:
    """The song list: scrolls move six rows, a tap on a row opens its page, back comes back."""

    def __init__(self) -> None:
        self.first, self.page, self.actions = 0, False, []

    async def wait_until_settled(self, timeout_s: float = 5):
        if self.page:
            return _screen(_node("Song page", rid="song_title", bounds="[0,200][1080,300]")
                           + _node("Add to playlist", rid="add", bounds="[0,400][1080,500]", clickable=True)
                           + _node("Share", rid="share", bounds="[0,500][1080,600]", clickable=True), activity="Song")
        return song_list(self.first)

    async def act(self, action):
        self.actions.append(action)
        if action.kind == "scroll":
            self.first = min(10, self.first + 6) if action.direction == "down" else max(0, self.first - 6)
        elif action.kind == "tap":
            self.page = True
        elif action.kind == "back":
            self.page = False
        return ActionResult(ok=True, duration_ms=1.0)


def test_each_step_carries_the_budget_and_a_scroll_reports_the_lists_end(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    scroll = step({"type": "scroll", "direction": "down", "element": 2})
    model = Model(scroll, scroll, scroll, step({"type": "done", "result": "20 songs"}))
    res = asyncio.run(AgentRunner(Songs(), model, ScriptedApprover(True), RunConfig(max_steps=6, data_scope="test_app"))
                      .run("How many songs are there?", task_id="songs", memory=""))
    assert "STEPS LEFT" not in model.prompts[0] and "STEPS LEFT: 3 of 6\n" in model.prompts[3]
    assert "6 new items came into view (4 you had already seen); there may be more" in model.prompts[1]
    assert "4 new items came into view (6 you had already seen); this is the end of the list" in model.prompts[2]
    assert "the list did not move: it is already at the end of the list" in model.prompts[3]
    assert res.status in ("done", "done_unverified")


def test_a_done_on_the_last_step_is_accepted_though_the_plans_check_disagrees(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    # the plan's check wants "Saved", which the screen never shows; before, the rejected done ended the run at the step limit
    model = Model(step({"type": "scroll", "direction": "down", "element": 2}), step({"type": "done", "result": "Renamed it"}))
    res = asyncio.run(AgentRunner(Songs(), model, ScriptedApprover(True), RunConfig(max_steps=2, data_scope="test_app"))
                      .run("Rename the song", task_id="last", memory=""))
    assert res.status == "done_unverified" and res.result == "Renamed it"
    assert "STEPS LEFT: 1 of 2 (this is the last step)" in model.prompts[1]
    # with steps left, the first rejection still goes back to the model, as before
    model = Model(step({"type": "done", "result": "Renamed it"}))
    res = asyncio.run(AgentRunner(Songs(), model, ScriptedApprover(True), RunConfig(max_steps=5, data_scope="test_app"))
                      .run("Rename the song", task_id="early", memory=""))
    assert res.status == "done_unverified" and len(model.prompts) == 2


def test_a_replan_from_going_in_circles_sees_the_history_and_what_was_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(TraceWriter.__init__, "__defaults__", (tmp_path,))
    # open a song, back to the list, again and again: the list's 4th visit replans
    tap, back = step({"type": "tap", "element": 3}, remember="Added Song 00 to the playlist"), step({"type": "back"})
    model = Model(tap, back, tap, back, tap, back, step({"type": "done", "result": "ok"}))
    asyncio.run(AgentRunner(Songs(), model, ScriptedApprover(True), RunConfig(max_steps=10, data_scope="test_app"))
                .run("Add three songs to the playlist", task_id="circles", memory=""))
    assert len(model.plan_prompts) == 2
    first, replan = model.plan_prompts
    assert "DONE SO FAR" not in first and "REPLANNING" in replan
    assert "DONE SO FAR (the agent's actions in this task, oldest first):\nstep 1: tap [3]" in replan
    assert "REMEMBERED (what the agent kept from screens it left):\n- Added Song 00 to the playlist" in replan
    assert any("rewritten from what you have done so far" in p for p in model.prompts)


def long_file(offsets: dict[str, int] | None = None):
    body = " ".join(f"recipe{i}|10 mins|steps" for i in range(600))  # ~13,000 characters in one EditText, like recipes.txt
    field = _node(body, rid="editor", cls="android.widget.EditText", bounds="[0,400][1080,2000]")
    lst = _node(rid="scroller", cls="android.widget.ScrollView", bounds="[0,400][1080,2000]", scrollable=True, children=field)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
           + _node(cls="android.widget.FrameLayout", bounds="[0,0][1080,2400]", pkg="net.example.notes",
                   children=_node("recipes", rid="toolbar", bounds="[0,200][1080,300]", pkg="net.example.notes")
                   + lst.replace("com.example.music", "net.example.notes")) + "</hierarchy>")
    return build_state(xml, "net.example.notes", "net.example.notes.Doc", 1080, 2400,
                       text_offsets=offsets), body


def test_a_text_longer_than_its_cap_is_shown_in_parts_and_a_scroll_moves_to_the_next():
    from devices.android import AndroidDevice

    s, body = long_file()
    text = next(e for e in s.numbered if e.text_key)
    assert text.label.endswith(f"[characters 1-4,000 of {len(body):,}; scroll down on it for the next part]")
    assert text.full_label == body  # routines still read the whole text
    # the device moves the part shown when the model scrolls the list that holds the text (or the text itself)
    dev = AndroidDevice("emulator-0")
    dev._last = s
    lst = next(e for e in s.numbered if e.kind == "List")
    dev._page_text(lst, "down")
    assert dev._text_offsets == {text.text_key: 3800}
    s2, _ = long_file(dev._text_offsets)
    t2 = next(e for e in s2.numbered if e.text_key)
    assert t2.label.startswith("…" + body[3800:3830]) and "[characters 3,801-7,800 of" in t2.label
    note = _scroll_note(s, s2, Action(kind="scroll", direction="down", element=lst.number), True)
    assert note == f"the long text [{t2.number}] now shows characters 3,801-7,800 of {len(body):,}; scroll down on it for the next part"
    # to the last part, which says so, and no further
    for _ in range(5):
        dev._last = long_file(dev._text_offsets)[0]
        dev._page_text(lst, "down")
    last = next(e for e in long_file(dev._text_offsets)[0].numbered if e.text_key)
    assert last.label.endswith(f"of {len(body):,}; this is the end of it]") and body[-20:] in last.label
    dev._page_text(lst, "up")
    assert dev._text_offsets[text.text_key] == len(body) - 3800 - 3800
