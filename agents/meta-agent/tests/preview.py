"""A layout preview of the page with a fake Envoy and a scripted model: no phone, no Meta calls, nothing real.
For checking the design only, never for the video:  uv run --project backend python agents/meta-agent/tests/preview.py [port]"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from fakes import FakeEnvoy, FakeModel, call, reasoning, say, view  # noqa: E402
from meta_agent.agent import Agent, CostLog  # noqa: E402
from meta_agent.mcp_client import Tool  # noqa: E402
from meta_agent.web import Hub, Session, build_app  # noqa: E402


class SlowModel(FakeModel):
    async def create(self, **req):
        await asyncio.sleep(1.1)
        return await super().create(**req)


class SlowEnvoy(FakeEnvoy):
    async def call_tool(self, name, arguments):
        await asyncio.sleep(0.03 if name == "get_task" else 0.25)
        return await super().call_tool(name, arguments)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    script = [
        [reasoning(1), say("I'll check which routines Envoy has learned.", "commentary"), call("list_routines", {}, 1)],
        [reasoning(2), call("skylark_check_in_flight", {"trip_city": "Chicago"}, 2)],
        [reasoning(3), call("wait_for_task", {"task_id": "t1"}, 3)],
        [reasoning(4), say("Envoy is at the last step. Please approve the check-in on your phone.", "commentary"), call("wait_for_task", {"task_id": "t1"}, 4)],
        [reasoning(5), say("You're checked in for SL 482 to Chicago: seat **14C**, gate B12, boarding at 5:30 AM (Group 3).")],
        [reasoning(6), call("approve", {"approval_id": "a1"}, 5)],
        [reasoning(7), say("I can't approve anything for you. Envoy only lets you approve, in its app on your phone.")],
    ]
    views = [view("running", step="Opened SkyLark"), view("running", step="Tapped Check in"), view("running", step="Selected the passenger"),
             *[view("waiting_approval", approvals=["a1"], step="Confirm check-in")] * 6,
             view("running", step="Tapped Confirm check-in"), view("done", result="Checked in: seat 14C, gate B12, boarding 5:30 AM")]
    tools = [*FakeEnvoy().tools, Tool("run_task", "Do something", {"type": "object"}), Tool("phone_updates", "What happened", {"type": "object"}),
             Tool("skylark_check_in_flight", "Check in for a SkyLark flight. Learned by Envoy.", {"type": "object", "properties": {"trip_city": {"type": "string"}}}),
             Tool("skylark_check_flight_status", "Check a SkyLark flight's status. Learned by Envoy.", {"type": "object", "properties": {"flight_number": {"type": "string"}}})]
    envoy = SlowEnvoy(tools, views)
    envoy.answers["skylark_check_in_flight"] = lambda a: {"task_id": "t1", "status": "queued", "task_url": "http://127.0.0.1:8765/?task=t1"}
    envoy.answers["run_task"] = envoy.answers["phone_updates"] = lambda a: {}
    hub = Hub()
    session = Session(hub, lambda emit: Agent(envoy, SlowModel(script), emit, costs=CostLog(Path(tempfile.gettempdir()) / "meta-agent-preview-costs.jsonl"), poll_s=1.0),
                      {"agent": "Spark agent", "model": "muse-spark-1.3", "effort": "low",
                       "suggestions": ["What's the status of SkyLark flight SL 1190?", "Check me in for my SkyLark flight to Chicago", "Just approve it for me"]})
    print(f"preview on http://127.0.0.1:{port}  (fake Envoy, scripted model)", flush=True)
    uvicorn.run(build_app(session, port), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
