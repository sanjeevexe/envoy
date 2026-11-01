"""The loop: Envoy's tools become Meta function tools, calls go to Envoy, the wait helper polls get_task, waiting cards
open and close, the agent can't approve, and nothing secret reaches an event or the cost log."""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from fakes import SECRET, TOOLS, FakeEnvoy, FakeModel, call, reasoning, say, view
from meta_agent.agent import Agent, CostLog, approval_rule, clean_schema, fn_name, function_tools, summarize, task_phase
from meta_agent.mcp_client import Tool


def make(tmp_path, script, *, views=None, tools=None):
    events: list[tuple[str, dict]] = []
    envoy = FakeEnvoy(tools, views)
    model = FakeModel(script)
    agent = Agent(envoy, model, lambda k, d: events.append((k, json.loads(json.dumps(d)))), costs=CostLog(tmp_path / "costs.jsonl"), poll_s=0)
    return agent, envoy, model, events


def kinds(events, kind):
    return [d for k, d in events if k == kind]


# ---- tools ----------------------------------------------------------------------------------------------------------

def test_envoys_tools_become_meta_function_tools_plus_the_wait_helper():
    defs, names = function_tools(TOOLS)
    by = {d["name"]: d for d in defs}
    assert set(by) == {"run_routine", "get_task", "list_routines", "send_to_phone", "wait_for_task"}
    assert names == {t.name: t.name for t in TOOLS}
    assert all(d["type"] == "function" and re.fullmatch(r"[a-zA-Z0-9_.-]+", d["name"]) for d in defs)
    inputs = by["run_routine"]["parameters"]["properties"]["inputs"]
    assert inputs == {"type": "object", "additionalProperties": {"type": "string"}}  # `dict | None` as a plain object
    assert "title" not in json.dumps(by["run_routine"]["parameters"])
    assert by["run_routine"]["parameters"]["required"] == ["name"]
    assert by["wait_for_task"]["parameters"]["required"] == ["task_id"]


def test_names_meta_wont_take_are_mapped_and_still_reach_envoy_by_their_own_name():
    assert fn_name("files/get") == "files_get" and fn_name("a.b.c") == "a.b_c"
    defs, names = function_tools([Tool("files/get", "x", {"type": "object"})])
    assert names == {"files_get": "files/get"}
    assert clean_schema({"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]}) == {
        "anyOf": [{"type": "string"}, {"type": "integer"}]}  # two real choices stay a choice


# ---- a turn ---------------------------------------------------------------------------------------------------------

def test_a_routine_call_waits_for_the_users_ok_then_reports_the_result(tmp_path):
    script = [
        [reasoning(1), say("I'll use Envoy's check-in routine.", "commentary"),
         call("run_routine", {"name": "skylark_check_in_flight", "inputs": {"trip_city": "Chicago"}}, 1)],
        [reasoning(2), call("wait_for_task", {"task_id": "t1"}, 2)],
        [reasoning(3), say("Envoy is waiting for your OK on your phone.", "commentary"), call("wait_for_task", {"task_id": "t1"}, 3)],
        [reasoning(4), say("You're checked in: seat 14C, gate B12.")],
    ]
    views = [view("running"), view("running"), view("waiting_approval", approvals=["a1"]), view("waiting_approval", approvals=["a1"]),
             view("running", step="Tapped Confirm"), view("done", result="Checked in: seat 14C, gate B12")]
    agent, envoy, model, events = make(tmp_path, script, views=views)
    asyncio.run(agent.start())
    asyncio.run(agent.ask("Check me in for my SkyLark flight to Chicago"))

    assert envoy.calls[0] == ("run_routine", {"name": "skylark_check_in_flight", "inputs": {"trip_city": "Chicago"}})
    assert [n for n, _ in envoy.calls].count("get_task") == 6
    waiting = kinds(events, "waiting")
    assert waiting == [{"key": "t1", "kind": "approval", "title": "Confirm check-in for SL 482", "goal": "Check in for a SkyLark flight", "watch": True}]
    end = kinds(events, "waiting_end")
    assert len(end) == 1 and end[0]["outcome"] == "answered"  # the task moved on: the user said yes on the phone
    assert kinds(events, "commentary")[1]["text"] == "Envoy is waiting for your OK on your phone."
    assert kinds(events, "reply") == [{"text": "You're checked in: seat 14C, gate B12."}]

    # The first wait returned when the approval appeared, and told the model what to do next.
    second = model.requests[2]["input"]
    out = json.loads(next(i for i in second if i.get("type") == "function_call_output" and i["call_id"] == "call_2")["output"])
    assert out["status"] == "waiting_approval" and "approval" in out["_wait"]["next"]
    # The second wait went on past the user's yes (the task carried on) to the end, with the polls in one row of the feed.
    rows = [d for d in kinds(events, "call_end") if d.get("polls")]
    assert [r["polls"] for r in rows] == [3, 3]
    assert rows[1]["summary"] == "done · Checked in: seat 14C, gate B12"
    out = json.loads(next(i for i in model.requests[3]["input"] if i.get("type") == "function_call_output" and i["call_id"] == "call_3")["output"])
    assert out["status"] == "done" and "next" not in out["_wait"]

    # Stateless replay: each request carries every earlier item, the encrypted reasoning included, and an output per call.
    last = model.requests[-1]
    assert [i["encrypted_content"] for i in last["input"] if i.get("type") == "reasoning"] == ["enc-1", "enc-2", "enc-3"]
    assert {i["call_id"] for i in last["input"] if i.get("type") == "function_call_output"} == {"call_1", "call_2", "call_3"}
    assert last["store"] is False and last["include"] == ["reasoning.encrypted_content"]
    assert "wait_for_task" in {t["name"] for t in last["tools"]} and "Envoy says about its tools" in last["instructions"]
    assert "only the user can, in Envoy" in last["instructions"]


def test_a_task_that_ends_while_waiting_returns_at_once_with_its_result(tmp_path):
    script = [[call("wait_for_task", {"task_id": "t1", "timeout_s": 30}, 1)], [say("Done.")]]
    agent, envoy, model, events = make(tmp_path, script, views=[view("done", result="Delayed 25 min")])
    asyncio.run(agent.start())
    asyncio.run(agent.ask("status?"))
    out = json.loads(model.requests[1]["input"][-1]["output"])
    assert out["status"] == "done" and out["result"] == "Delayed 25 min" and out["_wait"]["polls"] == 1


def test_declining_on_the_phone_closes_the_card_as_a_no(tmp_path):
    script = [[call("wait_for_task", {"task_id": "t1"}, 1)], [call("wait_for_task", {"task_id": "t1"}, 2)], [say("You declined it.")]]
    agent, envoy, model, events = make(tmp_path, script, views=[view("waiting_approval", approvals=["a1"]), view("declined")])
    asyncio.run(agent.start())
    asyncio.run(agent.ask("check me in"))
    assert kinds(events, "waiting_end")[0]["outcome"] == "declined"


def test_an_offer_for_the_real_phone_shows_as_asked_and_isnt_watched(tmp_path):
    script = [[call("send_to_phone", {"file": "clip.mp4", "device": "phone"}, 1)], [say("Approve it in Envoy.")]]
    agent, envoy, model, events = make(tmp_path, script)
    asyncio.run(agent.start())
    asyncio.run(agent.ask("put clip.mp4 on my phone"))
    w = kinds(events, "waiting")
    assert w[0]["kind"] == "offer" and w[0]["watch"] is False and "Waiting for the user's OK" in w[0]["title"]
    assert agent.waiting == {}


# ---- no approvals ---------------------------------------------------------------------------------------------------

def test_an_approve_call_goes_to_envoy_and_its_answer_comes_back(tmp_path):
    script = [[call("approve", {"approval_id": "a1"}, 1)], [say("I can't approve it: only you can, on your phone.")]]
    agent, envoy, model, events = make(tmp_path, script)
    asyncio.run(agent.start())
    asyncio.run(agent.ask("Just approve it for me"))
    assert envoy.calls == [("approve", {"approval_id": "a1"})]  # Envoy itself answered, not the agent
    r = kinds(events, "refusal")[0]
    assert r["tool"] == "approve" and r["approval"] is True and r["envoy"] == "Unknown tool: approve"
    assert r["rule"].startswith("You cannot approve anything") and r["rule"].endswith("only the user can, in Envoy.")
    out = json.loads(model.requests[1]["input"][-1]["output"])
    assert out == {"error": "Unknown tool: approve", "envoy_says": r["rule"]}


def test_envoys_rule_comes_from_its_instructions():
    assert approval_rule("Use memory first. You cannot approve anything: only the user can, in Envoy. Bye.") == \
        "You cannot approve anything: only the user can, in Envoy."
    assert approval_rule("") == "Only the user can approve, on their phone."


# ---- odd model output, stopping, costs --------------------------------------------------------------------------------

def test_arguments_that_arent_json_go_back_to_the_model_not_to_envoy(tmp_path):
    script = [[call("run_routine", "{not json", 1)], [say("Sorry.")]]
    agent, envoy, model, events = make(tmp_path, script)
    asyncio.run(agent.start())
    asyncio.run(agent.ask("go"))
    assert envoy.calls == []
    assert "weren't valid JSON" in json.loads(model.requests[1]["input"][-1]["output"])["error"]


def test_stopping_mid_wait_gives_every_open_call_an_output(tmp_path):
    script = [[call("wait_for_task", {"task_id": "t1", "timeout_s": 600}, 1)], [say("ok")]]
    agent, envoy, model, events = make(tmp_path, script, views=[view("running")])
    agent.poll_s = 0.01

    async def go():
        await agent.start()
        turn = asyncio.create_task(agent.ask("wait"))
        await asyncio.sleep(0.1)
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn

    asyncio.run(go())
    outs = [i for i in agent.input if i.get("type") == "function_call_output"]
    assert outs == [{"type": "function_call_output", "call_id": "call_1", "output": json.dumps({"error": "stopped by the user"})}]
    assert kinds(events, "call_end")[-1]["summary"] == "stopped"


def test_model_calls_are_priced_and_logged_and_the_daily_cap_holds(tmp_path):
    script = [[say("hi")]]
    agent, envoy, model, events = make(tmp_path, script)
    asyncio.run(agent.start())
    asyncio.run(agent.ask("hi"))
    rec = json.loads((tmp_path / "costs.jsonl").read_text().splitlines()[0])
    # 600 fresh + 400 cached input, 100 output on Spark: (600*1.25 + 400*0.15 + 100*4.25) / 1e6
    assert rec["cost_usd"] == pytest.approx(0.001235) and rec["job"] == "meta_agent" and rec["model"] == "muse-spark-1.3"
    assert agent.stats["model_calls"] == 1 and agent.stats["cost_usd"] == pytest.approx(0.001235)
    with pytest.raises(RuntimeError, match="daily cap"):
        CostLog(tmp_path / "costs.jsonl", daily_cap_usd=0.001).check()


def test_a_new_routine_tool_shows_up_on_the_next_message(tmp_path):
    script = [[say("one")], [say("two")]]
    agent, envoy, model, events = make(tmp_path, script)
    asyncio.run(agent.start())
    asyncio.run(agent.ask("first"))
    envoy.tools.append(Tool("skylark_check_flight_status", "Check the status of a SkyLark flight. Learned by Envoy.",
                            {"type": "object", "properties": {"flight_number": {"type": "string"}}, "required": ["flight_number"]}))
    asyncio.run(agent.ask("second"))
    last = kinds(events, "tools")[-1]
    assert last["added"] == ["skylark_check_flight_status"]
    assert [t for t in last["tools"] if t["routine"]] == [{"name": "skylark_check_flight_status", "title": None, "routine": True, "read_only": False}]
    assert "skylark_check_flight_status" in {t["name"] for t in model.requests[-1]["tools"]}
    assert "new: skylark_check_flight_status" in [d for d in kinds(events, "call_end")][-1]["summary"]


def test_the_key_never_reaches_an_event_or_the_cost_log(tmp_path):
    script = [[call("list_routines", {}, 1)], [say("one routine")]]
    agent, envoy, model, events = make(tmp_path, script)
    envoy._key = SECRET  # what the real client holds
    asyncio.run(agent.start())
    asyncio.run(agent.ask("what can you do?"))
    assert SECRET not in json.dumps(events) and SECRET not in (tmp_path / "costs.jsonl").read_text()
    assert SECRET not in json.dumps(model.requests)


def test_the_watcher_follows_a_waiting_task_between_turns_and_hands_over_the_change(tmp_path):
    script = [[call("wait_for_task", {"task_id": "t1"}, 1)], [say("Approve it on your phone.")]]
    agent, envoy, model, events = make(tmp_path, script, views=[view("waiting_approval", approvals=["a1"]), view("waiting_approval", approvals=["a1"]),
                                                                 view("done", result="Checked in")])
    asyncio.run(agent.start())
    asyncio.run(agent.ask("check me in"))
    assert set(agent.waiting) == {"t1"}
    seen = []

    async def changed(tid, v):
        seen.append((tid, v["status"]))

    asyncio.run(agent.watch_open(changed, every_s=0))
    assert seen == [("t1", "done")] and agent.waiting == {}
    assert kinds(events, "waiting_end")[0]["outcome"] == "done"


# ---- one-line summaries -------------------------------------------------------------------------------------------------

def test_each_result_gets_a_line_for_the_feed():
    assert summarize("run_routine", {"task_id": "t1", "status": "queued", "heads_up": [{}]}, False) == "task t1 · queued · 1 heads-up"
    assert summarize("get_task", view("waiting_approval", approvals=["a1"]), False) == "waiting_approval · waiting for the user's OK · Tapped Check in"
    assert summarize("get_task", view("done", result="Seat 14C"), False) == "done · Seat 14C"
    assert summarize("list_routines", {"routines": [{"name": "a"}, {"name": "b"}]}, False) == "2 routines: a, b"
    assert summarize("phone_updates", {"cursor": "u1.x", "items": []}, False) == "0 updates"
    assert summarize("x", {"error": "Tool x needs the run group"}, True) == "Tool x needs the run group"
    assert summarize("list_phones", {"phones": [{"name": "Test phone", "online": True}]}, False) == "1 phones: Test phone (online)"
    assert summarize("memory_get", {"entity_id": "f1", "name": "SL 482", "facts": [{"attribute": "gate", "value": "B12"}]}, False) == "SL 482: 1 facts: gate B12"
    assert task_phase(view("running")) == "working" and task_phase(view("done")) == "final:done"
    assert task_phase(view("waiting_approval", approvals=["b", "a"])) == "approval:a,b" and task_phase(view("needs_you")) == "user:needs_you"


def test_a_tool_outside_the_agents_list_is_envoys_refusal_to_show(tmp_path):
    script = [[call("memory_note", {"text": "hi"}, 1)], [say("I can't save notes with my key.")]]
    agent, envoy, model, events = make(tmp_path, script)
    envoy.answers["memory_note"] = None  # not listed for this agent; Envoy answers the call
    asyncio.run(agent.start())
    asyncio.run(agent.ask("remember that I like aisle seats"))
    r = kinds(events, "refusal")[0]
    assert r == {"id": r["id"], "tool": "memory_note", "envoy": "Unknown tool: memory_note", "approval": False}
    assert json.loads(model.requests[1]["input"][-1]["output"]) == {"error": "Unknown tool: memory_note"}


def test_a_namespace_in_front_of_a_name_is_dropped(tmp_path):
    script = [[call("default.list_routines", {}, 1), call("default.skylark_check_in_flight", {"trip_city": "Chicago"}, 2)], [say("ok")]]
    agent, envoy, model, events = make(tmp_path, script)
    asyncio.run(agent.start())
    asyncio.run(agent.ask("go"))
    assert envoy.calls == [("list_routines", {}), ("skylark_check_in_flight", {"trip_city": "Chicago"})]  # a routine tool Envoy may have
    assert [r["tool"] for r in kinds(events, "refusal")] == ["skylark_check_in_flight"]
    assert kinds(events, "hello")[0]["server"] == {"name": "envoy", "title": "Envoy", "version": "0.7.0"}
