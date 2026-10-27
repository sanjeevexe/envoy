"""Run one agent task on an emulator and print what happened.

  uv run --project backend python scripts/run_task.py "check me in for my flight to Chicago" --skylark
  uv run --project backend python scripts/run_task.py "what's my gate?" --skylark --variant 2

--skylark prepares SkyLark Air (reset fixtures, chosen layout variant, cold launch) and marks the run
as test-app data. Irreversible actions ask for approval in the terminal unless --approve-all is given
(only allowed with --skylark, our own test app).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from agent.loop import AgentRunner, RunConfig
from devices.emulator import EmulatorDevice
from policy.approvals import ScriptedApprover, TerminalApprover
from testapps.skylark import SkyLark


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("goal")
    ap.add_argument("--avd", default="envoy-test")
    ap.add_argument("--skylark", action="store_true", help="prepare SkyLark Air first (test app)")
    ap.add_argument("--variant", type=int, default=0)
    ap.add_argument("--memory", default="", help="notes the agent may use, e.g. 'Last name: Patel'")
    ap.add_argument("--approve-all", action="store_true", help="approve irreversible steps (test app only)")
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--task-id")
    args = ap.parse_args()
    if args.approve_all and not args.skylark:
        print("--approve-all is only allowed on our own test app (--skylark)", file=sys.stderr)
        return 2

    device = EmulatorDevice(args.avd).connect()
    if args.skylark:
        SkyLark(device.serial).prepare(variant=args.variant)
    approver = ScriptedApprover(approve=True) if args.approve_all else TerminalApprover()
    config = RunConfig(max_steps=args.max_steps, data_scope="test_app" if args.skylark else "real")
    result = await AgentRunner(device, approver=approver, config=config).run(args.goal, task_id=args.task_id, memory=args.memory)

    print(json.dumps({k: v for k, v in result.__dict__.items()}, indent=2, default=str))
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
