"""Cross-app answers (api/crossapp.py), offline: fake phones, a fake model, the real task runner.

The runner's own path is kept (its phone choice, the per-phone lease, statuses, approvals); only the routine's work on
the phone is a fake that sleeps, so two parts on two phones can be seen overlapping in time.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from PIL import Image

import api.runner as runner_mod
from agent.trace import TraceWriter
from api.chat import chat
from api.crossapp import (CombinedAnswer, CrossApp, LeadInput, LeadPart, LeadSplit, Part, Split, apps_in, built_answer, check_split,
                          may_span_apps, verified)
from api.devices import Lease
from api.events import EventBus
from api.runner import APP_NAMES, TaskRunner
from api.store import TaskStore
from memory.retrieval import Retriever
from memory.store import MemoryStore
from models.schemas import ChatRoute
from policy.approvals import ApprovalRequest

SKYLARK, SB, DD, MAPS = "com.skylark.air", APP_NAMES["starbucks"], APP_NAMES["doordash"], APP_NAMES["google maps"]


# ---- fakes ---------------------------------------------------------------------------------------


class FakeAdapter:
    def __init__(self, replies: dict) -> None:
        self.replies, self.jobs = replies, []

    def call(self, job, content, **kw):
        name = job if isinstance(job, str) else job.name
        self.jobs.append(name)
        r = self.replies[name]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(parsed=r(content) if callable(r) else r, cost_at_standard_usd=0.001)


def spec(example: str = "") -> SimpleNamespace:
    return SimpleNamespace(type="text", example=example)


class Routines:
    def active(self):
        return [SimpleNamespace(app=SB, intent="Check how many calories are in a Starbucks drink", inputs={"drink_name": spec("Caffè Latte")}),
                SimpleNamespace(app=DD, intent="Search DoorDash for food", inputs={"search_query": spec("pizza")}),
                SimpleNamespace(app=SKYLARK, intent="Get the gate of a flight", inputs={"trip_city": spec("Denver")})]


def screen(pkg: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(package=pkg or "", activity=f"{pkg}.ui.MenuItemActivity", timestamp=time.time(), has_password_field=False,
                           secure=False, elements=[], numbered=[], compact="")


class Phone:
    frame_s = 0.0  # how long a screenshot takes (on an emulator, a gRPC call)

    def __init__(self) -> None:
        self.pkg: str | None = None

    async def launch(self, app, fresh=False):
        self.pkg = app

    async def wait_until_settled(self):
        return screen(self.pkg)

    async def observe(self, screenshot=False):
        return screen(self.pkg)

    def frame(self, width, timeout=5):
        time.sleep(self.frame_s)
        return Image.new("RGB", (width, width * 2))


class Pool:
    """Two emulators, as routing knows them: SkyLark on envoy-test, real apps on envoy-real."""

    def __init__(self) -> None:
        self.leases = {a: Lease(a) for a in ("envoy-test", "envoy-real")}
        self.phones: dict = {}
        self.devs = {a: Phone() for a in self.leases}

    def refresh_phones(self):
        return []

    async def device(self, avd):
        return self.devs[avd]

    def start_watch(self, *a, **k):
        pass

    def stop_watch(self, *a, **k):
        pass

    def gated(self, avd, device):
        return device

    def hand_back(self, *a, **k):
        pass

    @staticmethod
    def avd_for(app):
        return "envoy-test" if app == SKYLARK else "envoy-real"


# What each app's routine does on its phone: (seconds, outputs, status, asks for an approval)
WORK: dict[str, tuple] = {}
SPANS: list[tuple[str, float, float]] = []
TRACED: dict[str, int] = {}  # app → how many steps its routine traces (each gets a screenshot)


class FakeExecutor:
    def __init__(self, gated, adapter=None, approver=None, config=None, app_notes=None) -> None:
        self.gated, self.approver = gated, approver

    async def run(self, routine, inputs, task_id, **kw):
        delay, outputs, status, approve = WORK[routine.app]
        t0 = time.time()
        if approve:
            req = ApprovalRequest(task_id, "goal", routine.app, 'Tap "Place order"', ["irreversible"], "screen", target="Place order")
            if not (await asyncio.to_thread(self.approver.request, req)).approved:
                status = "declined"
        steps = TRACED.get(routine.app, 0)
        for i in range(steps):
            for listen in list(TraceWriter.listeners):
                listen(task_id, {"kind": "action", "decision": {"action": {"type": "tap"}}, "target": {"label": f"step {i + 1}"}})
            await asyncio.sleep(delay / steps)
        if not steps:
            await asyncio.sleep(delay)
        SPANS.append((routine.app, t0, time.time()))
        return SimpleNamespace(status=status, detail="all steps and checks passed" if status == "done" else status,
                               outputs=outputs if status == "done" else {}, model_calls=0, cost_at_standard_usd=0.0)


@pytest.fixture(autouse=True)
def fake_phone_work(monkeypatch, tmp_path):
    monkeypatch.setattr(runner_mod, "RoutineExecutor", FakeExecutor)
    monkeypatch.setattr(runner_mod, "after_run", lambda *a, **k: None)
    monkeypatch.setattr("api.approvals.SHOTS", tmp_path / "shots")
    monkeypatch.setattr(runner_mod, "SHOTS", tmp_path / "shots")
    WORK.clear()
    SPANS.clear()
    TRACED.clear()
    WORK.update({SKYLARK: (0.5, {"gate": "B22"}, "done", False), SB: (0.5, {"calories": "190"}, "done", False),
                 DD: (0.5, {"first_restaurant_name": "Philz Coffee"}, "done", False)})


def make(combine=None, remember_s: float = 0):
    store, bus, mem = TaskStore(":memory:"), EventBus(), MemoryStore(":memory:")
    adapter = FakeAdapter({"combine": combine or (lambda c: CombinedAnswer(answer="Starbucks says 190 calories; DoorDash's first latte place is Philz Coffee.",
                                                                           cites=[]))})
    r = TaskRunner(store, bus, Pool(), mem, SimpleNamespace(), adapter=adapter)
    r.loop = asyncio.get_running_loop()

    async def plan(tid, goal, routine_name, inputs, app):
        return SimpleNamespace(routine=f"routine_{app}", version=1, app=app), inputs, app, {}, 0

    async def remember(*a, **k):
        await asyncio.sleep(remember_s)
        return None

    r._plan, r._remember = plan, remember
    return r, CrossApp(r, Routines(), mem, adapter), adapter


def parts(*apps: str) -> list[Part]:
    label = {SKYLARK: "gate", SB: "Caffè Latte calories at Starbucks", DD: "first latte place on DoorDash", MAPS: "drive time"}
    return [Part(a, {SKYLARK: "SkyLark", SB: "Starbucks", DD: "DoorDash", MAPS: "Google Maps"}[a], label[a], f"look it up in {a}") for a in apps]


async def finish(r, pid, timeout=10):
    await asyncio.wait_for(asyncio.shield(r.jobs[pid]), timeout)


def spans_overlap(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[1], b[1]))


# ---- the lead step and chat ------------------------------------------------------------------------


def test_the_prefilter_needs_two_apps_or_a_second_question():
    assert apps_in("What's a Caffè Latte at Starbucks vs on DoorDash?") == {SB, DD}
    assert apps_in("What's my gate, and how long is the drive from 1 Hacker Way to SFO?") == {SKYLARK, MAPS}
    assert may_span_apps("What's a Caffè Latte at Starbucks vs on DoorDash?")
    assert may_span_apps("What's my gate, and how long is the drive from 1 Hacker Way to SFO?")
    assert may_span_apps("What's my gate, and what's my seat?")  # one app and a second question: the lead decides
    for one in ("What's the price of AA batteries on Amazon?", "Check me in for my flight to Chicago", "What's my gate?",
                "How many calories are in a Caffè Latte at Starbucks?", "Change my seat to 21C", "hi"):
        assert not may_span_apps(one), one
    assert apps_in("play the top song on YouTube Music") == {APP_NAMES["youtube music"]}


class SpyRunner:
    def __init__(self, crossapp=None) -> None:
        self.started: list = []
        if crossapp is not None:
            self.crossapp = crossapp

    def start(self, goal, source, **kw):
        self.started.append((goal, source, kw))
        return {"id": f"task-{len(self.started)}", "goal": goal, "status": "queued"}


class SpyCross:
    def __init__(self) -> None:
        self.calls: list = []

    def start(self, message, split, source, **kw):
        self.calls.append((message, split, source))
        return {"id": "task-parent", "goal": message, "kind": "crossapp", "status": "running"}


def chat_adapter(lead_reply=None):
    replies = {"chat": lambda c: ChatRoute(kind="task", goal=c.split("\n")[0].removeprefix("REQUEST: "), reply="")}
    if lead_reply is not None:
        replies["lead"] = lead_reply
    return FakeAdapter(replies)


@pytest.mark.parametrize("message", ["What's the price of AA batteries on Amazon?", "Check me in for my flight to Chicago",
                                     "How many calories are in a Caffè Latte at Starbucks?"])
def test_a_one_app_request_takes_the_normal_path_untouched(message):
    """Same model calls, same task started, same reply as a runner with no cross-app answers at all."""
    def run(runner):
        adapter = chat_adapter(lead_reply=AssertionError("the lead must not be called"))
        out = asyncio.run(chat(message, adapter=adapter, memory=None, runner=runner, routines=Routines()))
        return out, adapter.jobs, runner.started
    cross = SpyCross()
    with_cross, without = run(SpyRunner(cross)), run(SpyRunner())
    assert with_cross[1] == without[1] == ["chat"]
    assert with_cross[2] == without[2] and len(without[2]) == 1
    assert {k: v for k, v in with_cross[0].items() if k != "task"} == {k: v for k, v in without[0].items() if k != "task"}
    assert cross.calls == []


def test_when_the_lead_says_one_app_chat_goes_on_as_before():
    message = "What's my gate, and what's my seat?"
    single = LeadSplit(multi_app=False, parts=[], relation="separate")
    cross = SpyCross()
    a1, r1 = chat_adapter(lead_reply=single), SpyRunner(cross)
    out = asyncio.run(chat(message, adapter=a1, memory=None, runner=r1, routines=Routines()))
    a2, r2 = chat_adapter(), SpyRunner()
    plain = asyncio.run(chat(message, adapter=a2, memory=None, runner=r2, routines=Routines()))
    assert a1.jobs == ["lead", "chat"] and a2.jobs == ["chat"]
    assert r1.started == r2.started and cross.calls == []
    assert out["model_calls"] == plain["model_calls"] + 1 and out["reply"] == plain["reply"]


def test_a_failing_lead_falls_back_to_the_normal_path():
    cross = SpyCross()
    a, r = chat_adapter(lead_reply=RuntimeError("timeout")), SpyRunner(cross)
    asyncio.run(chat("What's a Caffè Latte at Starbucks vs on DoorDash?", adapter=a, memory=None, runner=r, routines=Routines()))
    assert a.jobs == ["lead", "chat"] and len(r.started) == 1 and cross.calls == []


def test_a_cross_app_request_becomes_one_parent_task():
    message = "How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?"
    split = LeadSplit(multi_app=True, relation="separate", parts=[
        LeadPart(app="starbucks", label="Caffè Latte calories", goal="Check how many calories are in a Caffè Latte at Starbucks",
                 inputs=[LeadInput(name="drink_name", value="Caffè Latte")]),
        LeadPart(app="doordash", label="first latte place", goal="Search DoorDash for latte and report the first restaurant",
                 inputs=[LeadInput(name="search_query", value="latte")])])
    cross = SpyCross()
    a, r = chat_adapter(lead_reply=split), SpyRunner(cross)
    out = asyncio.run(chat(message, adapter=a, memory=None, runner=r, routines=Routines()))
    assert a.jobs == ["lead"] and r.started == []  # the parent starts the parts, not chat
    (msg, got, source), = cross.calls
    assert msg == message and source == "chat"
    assert [(p.app, p.inputs) for p in got.parts] == [(SB, {"drink_name": "Caffè Latte"}), (DD, {"search_query": "latte"})]
    assert out["kind"] == "task" and "Starbucks and DoorDash" in out["reply"] and out["task"]["kind"] == "crossapp"


def test_the_split_keeps_only_known_apps_and_inputs_from_the_request():
    message = "Compare a Caffè Latte at Starbucks with DoorDash"
    out = LeadSplit(multi_app=True, relation="compare", parts=[
        LeadPart(app="starbucks", label="latte", goal="Check a Caffè Latte at Starbucks",
                 inputs=[LeadInput(name="drink_name", value="Caffè Latte"), LeadInput(name="size_name", value="Grande"),
                         LeadInput(name="drink_name2", value="Caffè Latte")]),
        LeadPart(app="uber eats", label="latte", goal="Check Uber Eats", inputs=[]),
        LeadPart(app="com.dd.doordash", label="latte", goal="Check a Caffè Latte on DoorDash",
                 inputs=[LeadInput(name="search_query", value="Mocha")])])
    split = check_split(out, message, Routines())
    assert [(p.app, p.inputs) for p in split.parts] == [(SB, {"drink_name": "Caffè Latte"}), (DD, {})]
    assert any("size_name" in d for d in split.dropped)  # not an input of the routine (and not in the request)
    assert any("drink_name2" in d for d in split.dropped)  # not an input of Starbucks' routines
    assert any("uber eats" in d for d in split.dropped)
    assert any("Mocha" in d and "not in the request" in d for d in split.dropped)  # a value the user didn't say
    one = LeadSplit(multi_app=True, relation="compare", parts=[LeadPart(app="starbucks", label="a", goal="x", inputs=[]),
                                                              LeadPart(app="starbucks", label="b", goal="y", inputs=[])])
    assert check_split(one, message, Routines()) is None  # one app is the normal path
    many = LeadSplit(multi_app=True, relation="separate", parts=[LeadPart(app=a, label=a, goal=a, inputs=[])
                                                                 for a in ("starbucks", "doordash", "amazon", "skylark", "chrome")])
    assert len(check_split(many, message, Routines()).parts) == 4


# ---- parts on phones ---------------------------------------------------------------------------------


def test_parts_on_two_phones_run_at_the_same_time():
    async def scenario():
        r, cross, _ = make()
        t0 = time.time()
        parent = cross.start("What's my gate, and how many calories are in a Caffè Latte at Starbucks?", Split(parts(SKYLARK, SB)), "chat")
        await finish(r, parent["id"])
        return r, parent["id"], time.time() - t0
    r, pid, wall = asyncio.run(scenario())
    kids = [t for t in r.store.list() if t.get("parent") == pid]
    assert sorted(t["device"] for t in kids) == ["envoy-real", "envoy-test"]
    assert len(SPANS) == 2 and spans_overlap(*SPANS) > 0.4  # both phones busy at once
    assert wall < 0.85  # about one part's time, not two (0.5 s each)
    timeline = next(s for s in r.store.steps(pid) if s["kind"] == "timeline")
    assert timeline["overlap_s"] > 0.4 and all(p["phone_at"] and p["ended_at"] for p in timeline["parts"])
    assert r.store.approvals() == []  # a read-only question asks for nothing
    parent = r.store.get(pid)
    assert parent["status"] == "done" and parent["kind"] == "crossapp" and parent["device"] in (None, "envoy-real, envoy-test")


def test_parts_that_need_the_same_phone_wait_for_it():
    async def scenario():
        r, cross, _ = make()
        t0 = time.time()
        parent = cross.start("Starbucks vs DoorDash", Split(parts(SB, DD)), "chat")
        await finish(r, parent["id"])
        return r, parent["id"], time.time() - t0
    r, pid, wall = asyncio.run(scenario())
    assert len(SPANS) == 2 and spans_overlap(*SPANS) == 0
    assert wall >= 0.95
    kids = [t for t in r.store.list() if t.get("parent") == pid]
    assert {t["device"] for t in kids} == {"envoy-real"}
    waited = [s["text"] for t in kids for s in r.store.steps(t["id"]) if "waiting for envoy-real" in (s.get("text") or "")]
    assert len(waited) == 1


def test_sequential_runs_one_part_at_a_time_even_on_two_phones():
    async def scenario():
        r, cross, _ = make()
        parent = cross.start("gate and calories", Split(parts(SKYLARK, SB)), "chat", sequential=True)
        await finish(r, parent["id"])
        return r, parent["id"]
    r, pid = asyncio.run(scenario())
    assert len(SPANS) == 2 and spans_overlap(*SPANS) == 0
    assert next(s for s in r.store.steps(pid) if s["kind"] == "timeline")["overlap_s"] == 0


def test_parts_are_ordinary_tasks_with_the_users_words():
    async def scenario():
        r, cross, _ = make()
        p = parts(SB, DD)
        p[0].inputs = {"drink_name": "Caffè Latte"}
        parent = cross.start("Starbucks vs DoorDash for a Caffè Latte", Split(p), "voice")
        await finish(r, parent["id"])
        return r, parent["id"]
    r, pid = asyncio.run(scenario())
    kids = sorted((t for t in r.store.list() if t.get("parent") == pid), key=lambda t: t["created_at"])
    assert [t["app"] for t in kids] == [SB, DD]
    assert all(t["request"] == "Starbucks vs DoorDash for a Caffè Latte" and t["source"] == "voice" for t in kids)
    assert kids[0]["inputs"] == {"drink_name": "Caffè Latte"} and kids[0]["kind"] == "routine"
    assert r.store.get(pid).get("parent") is None


# ---- combining ------------------------------------------------------------------------------------------


VALUES = [{"label": "latte at Starbucks", "app_name": "Starbucks", "status": "done", "result": "price: $5.45"},
          {"label": "latte on DoorDash", "app_name": "DoorDash", "status": "done", "result": "price: $6.55"}]


def test_the_combined_answer_uses_only_values_the_parts_returned():
    ok = CombinedAnswer(answer="A Caffè Latte is $5.45 at Starbucks and $6.55 on DoorDash, $1.10 more.",
                        cites=[{"part": 1, "value": "$5.45"}, {"part": 2, "value": "$6.55"}])
    assert verified(ok, "latte Starbucks vs DoorDash", VALUES) == ok.answer  # the difference of two prices is allowed
    invented = CombinedAnswer(answer="It's $4.95 at Starbucks and $6.55 on DoorDash.", cites=[{"part": 2, "value": "$6.55"}])
    assert verified(invented, "latte Starbucks vs DoorDash", VALUES) is None
    wrong_cite = CombinedAnswer(answer="Starbucks is cheaper.", cites=[{"part": 1, "value": "$6.55"}])
    assert verified(wrong_cite, "q", VALUES) is None
    gate = [{"status": "done", "result": "gate: B22"}, {"status": "done", "result": "35 min"}]
    cites = [{"part": 1, "value": "B22"}, {"part": 2, "value": "35 min"}]
    assert verified(CombinedAnswer(answer="Gate B22, 35 min from 1 Hacker Way.", cites=cites), "drive from 1 Hacker Way", gate) is not None
    assert verified(CombinedAnswer(answer="Gate B23, 35 min from 1 Hacker Way.", cites=cites[1:]), "drive from 1 Hacker Way", gate) is None


def test_verification_wants_whole_numbers_and_a_cite_from_every_part():
    q = "latte Starbucks vs DoorDash"
    both = [{"part": 1, "value": "$5.45"}, {"part": 2, "value": "$6.55"}]
    assert verified(CombinedAnswer(answer="It's $5 at Starbucks and $6.55 on DoorDash.", cites=both[1:]), q, VALUES) is None  # a piece of 5.45
    assert verified(CombinedAnswer(answer="$5.45 at Starbucks, 45 calories, $6.55 on DoorDash.", cites=both), q, VALUES) is None
    assert verified(CombinedAnswer(answer="Starbucks is $5.45.", cites=both[:1]), q, VALUES) is None  # DoorDash answered: cite it
    assert verified(CombinedAnswer(answer="Starbucks is $5.45, DoorDash more.", cites=both), q, VALUES) is None  # $6.55 isn't in the answer
    names = [{"status": "done", "result": "first restaurant name: Blue Bottle"}, {"status": "done", "result": "calories: 190"}]
    assert verified(CombinedAnswer(answer="DoorDash shows Peets Coffee first; 190 calories.", cites=[{"part": 2, "value": "190"}]), "q", names) is None
    ok = CombinedAnswer(answer="DoorDash shows Blue Bottle first; a latte is 190 calories.",
                        cites=[{"part": 1, "value": "Blue Bottle"}, {"part": 2, "value": "190"}])
    assert verified(ok, "q", names) == ok.answer


def test_overlap_counts_time_with_two_or_more_phones_busy_once():
    from api.crossapp import busy_together
    assert busy_together([(0, 1), (0, 1), (0, 1)]) == 1.0  # three phones at once for 1 s: 1 s, not 3
    assert busy_together([(0, 2), (1, 3)]) == 1.0
    assert busy_together([(0, 1), (1, 2)]) == 0.0  # one ends as the next starts
    assert busy_together([(0, 5)]) == 0.0
    failed = [VALUES[0], {"label": "x", "app_name": "DoorDash", "status": "failed", "result": "", "why": "no address"}]
    assert built_answer(failed) == "Starbucks: price: $5.45; DoorDash: couldn't check (no address)."


def test_an_invented_value_is_replaced_by_the_answer_built_from_the_parts():
    async def scenario():
        r, cross, _ = make(combine=lambda c: CombinedAnswer(answer="Starbucks says 250 calories.", cites=[]))
        parent = cross.start("calories and first latte place", Split(parts(SB, DD)), "chat")
        await finish(r, parent["id"])
        return r, parent["id"]
    r, pid = asyncio.run(scenario())
    parent = r.store.get(pid)
    assert parent["result"] == "Starbucks: calories: 190; DoorDash: first restaurant name: Philz Coffee."
    answer = next(s for s in r.store.steps(pid) if s["kind"] == "answer")
    for v in answer["values"]:  # every value with where and when it was read, from the part's own last screen
        assert v["screen"] == "MenuItemActivity" and v["time"] and v["app_name"] in ("Starbucks", "DoorDash")
    assert set(answer["sources"]) == {"Caffè Latte calories at Starbucks", "first latte place on DoorDash"}
    assert all(" · MenuItemActivity · " in line for line in answer["sources"].values())


def test_a_failing_combine_call_still_answers():
    async def scenario():
        r, cross, _ = make(combine=RuntimeError("model down"))
        parent = cross.start("calories and first latte place", Split(parts(SB, DD)), "chat")
        await finish(r, parent["id"])
        return r.store.get(parent["id"])
    parent = asyncio.run(scenario())
    assert parent["status"] == "done" and "Philz Coffee" in parent["result"]


def test_one_part_failing_gives_a_partial_answer_and_all_failing_a_failed_task():
    WORK[DD] = (0.1, {}, "failed", False)

    async def scenario(apps, combine=None):
        r, cross, adapter = make(combine=combine)
        parent = cross.start("q", Split(parts(*apps)), "chat")
        await finish(r, parent["id"])
        return r.store.get(parent["id"]), adapter.jobs
    partial, jobs = asyncio.run(scenario((SB, DD), combine=lambda c: CombinedAnswer(answer="Starbucks says 190 calories; DoorDash couldn't be checked.",
                                                                                    cites=[{"part": 1, "value": "190"}])))
    assert partial["status"] == "done" and partial["detail"] == "no answer from DoorDash" and jobs == ["combine"]
    WORK[SB] = (0.1, {}, "failed", False)
    failed, jobs = asyncio.run(scenario((SB, DD)))
    assert failed["status"] == "failed" and jobs == []  # nothing to combine: no model call
    assert "Starbucks: couldn't check" in failed["result"]


# ---- live status, approvals, stop -----------------------------------------------------------------------


def test_the_parent_waits_on_you_when_a_part_does_and_a_declined_part_is_said():
    WORK[SB] = (0.2, {"calories": "190"}, "done", True)

    async def scenario():
        r, cross, _ = make(combine=lambda c: CombinedAnswer(answer="DoorDash's first latte place is Philz Coffee; Starbucks was declined.",
                                                            cites=[{"part": 2, "value": "Philz Coffee"}]))
        parent = cross.start("q", Split(parts(SKYLARK, SB)), "chat")
        pid = parent["id"]
        for _ in range(300):  # the approval is stored a moment before its task says it waits
            await asyncio.sleep(0.01)
            pending, seen = r.store.approvals(status="pending"), r.store.get(pid)
            if pending and seen["status"] == "waiting_approval":
                break
        assert pending, "the Starbucks part should ask"
        child = pending[0]["task_id"]
        assert r.store.get(child)["parent"] == pid
        r.approvers[child].decide(pending[0]["id"], False, by="test")
        await finish(r, pid)
        return r, pid, seen
    r, pid, seen = asyncio.run(scenario())
    assert seen["status"] == "waiting_approval" and seen["detail"].startswith("Starbucks:")
    answer = next(s for s in r.store.steps(pid) if s["kind"] == "answer")
    assert {v["app_name"]: v["status"] for v in answer["values"]} == {"SkyLark": "done", "Starbucks": "declined"}
    assert r.store.get(pid)["detail"] == "no answer from Starbucks"


def test_the_parent_shows_each_answer_as_it_comes_in():
    WORK[SB] = (0.6, {"calories": "190"}, "done", False)
    WORK[SKYLARK] = (0.1, {"gate": "B22"}, "done", False)

    async def scenario():
        r, cross, _ = make()
        parent = cross.start("q", Split(parts(SKYLARK, SB)), "chat")
        for _ in range(100):
            await asyncio.sleep(0.01)
            mid = r.store.get(parent["id"])
            if "gate: B22" in (mid.get("result") or ""):
                break
        await finish(r, parent["id"])
        return mid
    mid = asyncio.run(scenario())
    assert mid["status"] == "running" and mid["result"] == "SkyLark: gate: B22 · Starbucks: checking…"


def test_stopping_the_parent_keeps_a_part_that_already_answered():
    WORK[SB] = (0.1, {"calories": "190"}, "done", False)
    WORK[DD] = (5, {}, "done", False)

    async def scenario():
        r, cross, _ = make(remember_s=1.0)  # the Starbucks part is still writing memory when you press Stop
        parent = cross.start("q", Split(parts(SB, DD)), "chat")
        kids: list = []
        for _ in range(200):
            await asyncio.sleep(0.01)
            kids = sorted((t for t in r.store.list() if t.get("parent") == parent["id"]), key=lambda t: t["created_at"])
            if kids and kids[0]["status"] == "done":
                break
        assert r.stop(parent["id"])
        with pytest.raises(asyncio.CancelledError):
            await r.jobs[parent["id"]]
        await asyncio.gather(*(r.jobs[k["id"]] for k in kids), return_exceptions=True)
        return [r.store.get(k["id"])["status"] for k in kids]
    assert asyncio.run(scenario()) == ["done", "stopped"]


def test_stopping_the_parent_stops_its_parts():
    WORK[SB] = (5, {}, "done", False)
    WORK[DD] = (5, {}, "done", False)

    async def scenario():
        r, cross, _ = make()
        parent = cross.start("q", Split(parts(SB, DD)), "chat")
        await asyncio.sleep(0.2)
        assert r.stop(parent["id"])
        with pytest.raises(asyncio.CancelledError):
            await r.jobs[parent["id"]]
        kids = [t["id"] for t in r.store.list() if t.get("parent") == parent["id"]]
        await asyncio.gather(*(r.jobs[k] for k in kids), return_exceptions=True)
        return r, parent["id"], kids
    r, pid, kids = asyncio.run(scenario())
    assert r.store.get(pid)["status"] == "stopped"
    assert [r.store.get(k)["status"] for k in kids] == ["stopped", "stopped"]


# ---- memory ---------------------------------------------------------------------------------------------


def test_the_combined_answer_is_remembered_with_each_part_as_its_source():
    async def scenario():
        r, cross, _ = make()
        parent = cross.start("How many calories in a Caffè Latte, and the first latte place on DoorDash?", Split(parts(SB, DD)), "chat")
        await finish(r, parent["id"])
        return r, parent["id"]
    r, pid = asyncio.run(scenario())
    mem = r.memory
    (note,) = mem.entities("Note")
    (fact,) = mem.current_facts(note["id"])
    assert fact["attribute"] == "body" and "Philz Coffee" in fact["value"]
    src = mem.source(fact["source"])
    assert src["kind"] == "cross-app answer" and src["reference"]["task_id"] == pid
    assert [(p["app"], p["screen"], bool(p["captured_at"])) for p in src["reference"]["parts"]] == [(SB, "MenuItemActivity", True),
                                                                                                    (DD, "MenuItemActivity", True)]
    assert Retriever(mem).where(fact["source"]).startswith("cross-app answer, ")
    assert any(s["kind"] == "memory" for s in r.store.steps(pid))


def test_a_screen_is_named_by_its_activity_or_else_its_title():
    from api.crossapp import screen_name
    el = lambda label, kind="Text", bar=False: SimpleNamespace(label=label, kind=kind, status_bar=bar)  # noqa: E731
    assert screen_name(SimpleNamespace(activity="com.dd.DashboardActivity", numbered=[])) == "DashboardActivity"
    obfuscated = SimpleNamespace(activity="com.starbucks.dIu", numbered=[el("9:41", bar=True), el("Back", "Button"), el("Caffè Latte")])
    assert screen_name(obfuscated) == 'the "Caffè Latte" screen'


# ---- pushes, screenshots and MCP -------------------------------------------------------------------------


def test_a_cross_app_question_pushes_once_with_its_answer(tmp_path):
    from api.push import Pusher, VapidKeys

    async def scenario():
        r, cross, _ = make()
        pusher = Pusher(r.store, VapidKeys(tmp_path), "https://envoy.example", send=lambda *a, **k: None)
        sent = []
        pusher.notify = lambda kind, title, body, path, **kw: sent.append((kind, title, path))  # type: ignore[method-assign]
        r.bus.listeners.append(pusher.on_event)
        parent = cross.start("Gate and calories?", Split(parts(SKYLARK, SB)), "chat")
        await finish(r, parent["id"])
        one = r.start("How many calories are in a Caffè Latte at Starbucks?", "chat", app=SB)
        await asyncio.wait_for(asyncio.shield(r.jobs[one["id"]]), 10)
        return parent["id"], one["id"], sent
    pid, tid, sent = asyncio.run(scenario())
    # The parts are quiet; the parent's answer pushes, and a task on its own still does.
    assert [(k, path) for k, _, path in sent] == [("task", f"/?task={pid}"), ("task", f"/?task={tid}")]
    assert sent[0][1] == "Done: Gate and calories?"


def test_step_screenshots_never_hold_up_the_other_phone(monkeypatch):
    """Each traced step takes a screenshot (0.15 s here, a gRPC call on an emulator). Taken on the event loop, six of
    them would stall both parts by 0.9 s; taken in a thread, the parts still overlap. Steps keep their order."""
    monkeypatch.setattr(Phone, "frame_s", 0.15)
    TRACED.update({SKYLARK: 3, SB: 3})

    async def scenario():
        r, cross, _ = make()
        t0 = time.time()
        parent = cross.start("What's my gate, and how many calories are in a Caffè Latte at Starbucks?", Split(parts(SKYLARK, SB)), "chat")
        await finish(r, parent["id"])
        return r, parent["id"], time.time() - t0
    r, pid, wall = asyncio.run(scenario())
    assert len(SPANS) == 2 and spans_overlap(*SPANS) > 0.4
    assert wall < 0.85
    for kid in (t for t in r.store.list() if t.get("parent") == pid):
        taps = [s for s in r.store.steps(kid["id"]) if s["kind"] == "action"]
        assert [s["text"] for s in taps] == ['tap "step 1"', 'tap "step 2"', 'tap "step 3"']
        assert all(s.get("shot") for s in taps) and kid["status"] == "done"
    assert r.pending_steps == {}


def test_mcp_run_task_asks_the_lead_for_a_cross_app_question():
    from mcp_server.server import build_mcp
    message = "How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?"
    split = LeadSplit(multi_app=True, relation="separate", parts=[
        LeadPart(app="starbucks", label="Caffè Latte calories", goal="Check how many calories are in a Caffè Latte at Starbucks",
                 inputs=[LeadInput(name="drink_name", value="Caffè Latte")]),
        LeadPart(app="doordash", label="first latte place", goal="Search DoorDash for latte and report the first restaurant", inputs=[])])

    def run(goal, lead_reply):
        cross = SpyCross()
        runner = SpyRunner(cross)
        adapter = FakeAdapter({"lead": lead_reply})
        server = build_mcp(SimpleNamespace(runner=runner, adapter=adapter, routines=Routines()), 8713, base="https://envoy.example")
        res = asyncio.run(server.call_tool("run_task", {"goal": goal}))
        return json.loads(res.content[0].text), adapter.jobs, runner.started, cross.calls

    out, jobs, started, calls = run(message, split)
    assert jobs == ["lead"] and started == [] and out["task_id"] == "task-parent"
    (msg, got, source), = calls
    assert msg == message and source == "mcp" and [p.app for p in got.parts] == [SB, DD]
    assert out["parts"] == ["Caffè Latte calories", "first latte place"]
    # One app: no lead call, the task starts as before; a failing lead: the same.
    out, jobs, started, calls = run("Check me in for my flight to Chicago", AssertionError("the lead must not be called"))
    assert jobs == [] and calls == [] and [s[:2] for s in started] == [("Check me in for my flight to Chicago", "mcp")]
    assert "parts" not in out
    out, jobs, started, calls = run(message, RuntimeError("timeout"))
    assert jobs == ["lead"] and calls == [] and len(started) == 1


def test_stop_closes_a_task_whose_run_already_ended_needing_you():
    """Nov 2: a Story run hit the agent's step limit and ended needing you. With no run behind it, Stop used to do
    nothing and the card stayed under Needs you; now Stop closes it. A finished task stays as it was."""
    async def scenario():
        r, _, _ = make()
        t = r.store.create("Post the newest gallery video to an Instagram story with a poll sticker", "mcp")
        r.store.update(t["id"], status="needs_you", detail="the agent could not finish (step_limit); asking the user")
        done = r.store.create("q", "chat")
        r.store.update(done["id"], status="done")
        return r, t["id"], done["id"]
    r, tid, did = asyncio.run(scenario())
    assert r.stop(tid) and r.store.get(tid)["status"] == "stopped" and r.store.get(tid)["waiting_for"] is None
    assert not r.stop(did) and r.store.get(did)["status"] == "done"
    assert not r.stop("task-no-such-id")
