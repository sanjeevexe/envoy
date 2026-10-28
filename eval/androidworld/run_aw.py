"""AndroidWorld's suite, run by AndroidWorld's own runner, with Envoy (or a do-nothing agent) as the agent.

  eval/androidworld/aw.sh run_aw.py --stage harness --agent noop --tasks SystemWifiTurnOn,ExpenseDeleteSingle
  eval/androidworld/aw.sh run_aw.py --stage pilot --tasks …
  eval/androidworld/aw.sh run_aw.py --stage baseline                      # all 116 tasks, seed 30, pass@1
  eval/androidworld/aw.sh run_aw.py --stage baseline --split dev          # one half
  eval/androidworld/aw.sh run_aw.py --stage seeds --instances 1,2,3 …     # other seeds (routines experiment)

This is AndroidWorld's run.py with our emulator's ports and gRPC token, and Envoy as the agent: `create_suite`,
`suite_utils.run` with its resumable checkpointer, its `_run_task` (initialize → episode → is_successful → tear_down,
a task counting only if the agent said done) and its episode runner (home screen, `int(10 * complexity)` steps).
Nothing in AndroidWorld is changed.

`EnvoyAgent.step(goal)` runs one whole Envoy episode in a subprocess (Envoy's backend is Python 3.13), giving it only
the goal, the step budget and a run id (`envoy_episode.make_payload`). Envoy's `done` text goes to AndroidWorld's answer
channel; `done` is "Envoy ended the episode itself". Later steps in the episode do nothing.

Output, per stage: eval/results/androidworld/<stage>/
  run.json                      the setting: commits, seed, tasks, split, model, tier, agent config
  episodes/<Task>__s<seed>.json AndroidWorld's score and run time joined with Envoy's record
  traces/<Task>__s<seed>.jsonl.gz  a digest of Envoy's trace (full traces: data/runs/<run id>/, gitignored)
AndroidWorld's own checkpoint (resume after a crash): data/androidworld/<stage>/checkpoint/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from android_world import checkpointer as checkpointer_lib
from android_world import constants, registry, suite_utils
from android_world.agents import base_agent
from android_world.env import json_action

import aw_env

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "eval" / "results" / "androidworld"
WORK = REPO / "data" / "androidworld"
EC = constants.EpisodeConstants

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envoy_episode import make_payload  # noqa: E402  (pure function; the Envoy run itself is a subprocess)


API_URL = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/") + "/models"
OUTAGE_WAIT_S = 3600  # how long a stage waits for the model API before it stops (a resume reruns the task)


def api_reachable(timeout: float = 10) -> bool:
    """Any HTTP answer from the model API (401 without a key is fine) means the network path is up."""
    try:
        urllib.request.urlopen(API_URL, timeout=timeout)
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
    return True


def wait_for_api(limit_s: float = OUTAGE_WAIT_S, every_s: float = 30) -> bool:
    deadline = time.time() + limit_s
    while not api_reachable():
        if time.time() > deadline:
            return False
        time.sleep(every_s)
    return True


def api_unreachable(rec: dict[str, Any]) -> bool:
    return rec.get("status") == "error" and "APIConnectionError" in str(rec.get("result"))


def _envoy_env() -> dict[str, str]:
    """The environment for Envoy's subprocess: no trace of AndroidWorld's venv or path."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME")}
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "aw-venv" not in p)
    return env


class NoopAgent(base_agent.EnvironmentInteractingAgent):
    """Does nothing, calls no model, and says it is done at once: an untouched task must score 0."""

    def __init__(self, env) -> None:
        super().__init__(env, name="noop", transition_pause=None)

    def step(self, goal: str) -> base_agent.AgentInteractionResult:
        return base_agent.AgentInteractionResult(True, {"noop": True})


class HandAgent(base_agent.EnvironmentInteractingAgent):
    """The harness proof's person: waits while the task is done by hand over adb (in another shell), then submits.

    It writes the goal to data/androidworld/<stage>/hand/goal.txt and waits for hand/done.json ({"answer": "..." or null}).
    """

    def __init__(self, env, stage: str, timeout_s: float = 1800) -> None:
        super().__init__(env, name="hand", transition_pause=None)
        self.dir = WORK / stage / "hand"
        self.timeout_s = timeout_s

    def step(self, goal: str) -> base_agent.AgentInteractionResult:
        self.dir.mkdir(parents=True, exist_ok=True)
        done = self.dir / "done.json"
        done.unlink(missing_ok=True)
        (self.dir / "goal.txt").write_text(goal)
        aw_env.park_forwarder()  # same path as Envoy's episodes: the person may use uiautomator (dumps) meanwhile
        print(f"HAND: waiting for {done} — goal: {goal}", flush=True)
        deadline = time.time() + self.timeout_s
        while not done.exists():
            if time.time() > deadline:
                return base_agent.AgentInteractionResult(False, {"hand": "timed out"})
            time.sleep(1)
        answer = json.loads(done.read_text()).get("answer")
        done.unlink()
        print(f"HAND: forwarder restored in {aw_env.restore_forwarder(self.env):.1f} s", flush=True)
        (self.dir / "goal.txt").unlink(missing_ok=True)
        if answer:
            self.env.execute_action(json_action.JSONAction(action_type=json_action.ANSWER, text=answer))
        return base_agent.AgentInteractionResult(True, {"hand_answer": answer})


class EnvoyAgent(base_agent.EnvironmentInteractingAgent):
    def __init__(self, env, stage: str, config: dict[str, Any] | None = None, timeout_per_step_s: float = 90) -> None:
        super().__init__(env, name="envoy", transition_pause=None)
        self.stage = stage
        self.config = config or {}
        self.timeout_per_step_s = timeout_per_step_s
        self._ran = False
        self.last: dict[str, Any] | None = None

    def reset(self, go_home: bool = False) -> None:
        super().reset(go_home)
        # As AndroidWorld's own agents do (m3a, t3a, seeact): android_env turns on Developer options' pointer location,
        # whose crosshair and coordinate bar would otherwise be in every screenshot Envoy takes.
        self.env.hide_automation_ui()
        self._ran = False
        self.last = None

    def run_envoy(self, payload: dict[str, Any]) -> dict[str, Any]:
        work = WORK / self.stage / "episodes"
        work.mkdir(parents=True, exist_ok=True)
        rid = payload["run_id"]
        p_in, p_out, p_dig = work / f"{rid}.payload.json", work / f"{rid}.json", work / f"{rid}.jsonl.gz"
        p_in.write_text(json.dumps(payload))
        script = "envoy_routine.py" if payload["config"].get("mode") == "routine" else "envoy_episode.py"
        cmd = ["uv", "run", "--project", "backend", "python", f"eval/androidworld/{script}",
               "--payload", str(p_in), "--out", str(p_out), "--digest", str(p_dig)]
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, cwd=REPO, env=_envoy_env(), capture_output=True, text=True,
                                  timeout=payload["max_steps"] * self.timeout_per_step_s + 300)
            (work / f"{rid}.stderr.txt").write_text(proc.stderr[-20000:])
            if proc.returncode != 0 or not p_out.exists():
                return {"run_id": rid, "status": "error", "result": f"envoy exited {proc.returncode}: {proc.stderr[-800:]}",
                        "done": False, "answer": None, "wall_s": round(time.time() - t0, 1)}
        except subprocess.TimeoutExpired:
            return {"run_id": rid, "status": "error", "result": "envoy timed out", "done": False, "answer": None,
                    "wall_s": round(time.time() - t0, 1)}
        rec = json.loads(p_out.read_text())
        rec["wall_s"] = round(time.time() - t0, 1)
        return rec

    def step(self, goal: str) -> base_agent.AgentInteractionResult:
        if self._ran:  # the whole episode already ran inside the first step; AndroidWorld's loop runs out its budget
            return base_agent.AgentInteractionResult(False, {"envoy": "idle"})
        self._ran = True
        run_id = f"aw-{self.stage}-{dt.datetime.now().strftime('%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
        aw_env.park_forwarder()  # see aw_env: uiautomator2 would suppress it and it can crash on screen
        rec = self.run_envoy(make_payload(goal, int(self._max_steps or 10), run_id, self.config))
        retries = 0
        # A network outage is not the agent's doing. On Oct 28 one turned 98 episodes in a row into instant errors. If
        # Envoy couldn't reach the model before it touched the phone, the phone is as AndroidWorld set it up, so the
        # episode starts again once the API answers. If it never does, the stage stops and a resume reruns this task.
        while api_unreachable(rec) and not rec.get("steps_device"):
            retries += 1
            if retries > 3 or not wait_for_api():
                print("STOP: the model API is unreachable; resume the stage to rerun this task", flush=True)
                os._exit(3)
            run_id = f"aw-{self.stage}-{dt.datetime.now().strftime('%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
            rec = self.run_envoy(make_payload(goal, int(self._max_steps or 10), run_id, self.config))
        rec["harness"] = {"crash_dialog_after_episode": aw_env.crash_dialog() or None}
        if retries:
            rec["harness"]["api_outage_retries"] = retries
        if api_unreachable(rec):  # lost mid-episode: recorded as it happened, flagged, and the next task waits
            rec["harness"]["api_lost_mid_episode"] = True
            if not wait_for_api():
                print("STOP: the model API is unreachable; resume the stage to rerun the next task", flush=True)
                os._exit(3)
        try:
            rec["harness"]["forwarder_restore_s"] = round(aw_env.restore_forwarder(self.env), 1)
        except RuntimeError as e:  # AndroidWorld's scoring then reads the screen with its own retries; recorded either way
            rec["harness"]["forwarder_restore_error"] = str(e)
        if rec.get("answer"):
            self.env.execute_action(json_action.JSONAction(action_type=json_action.ANSWER, text=rec["answer"]))
        self.last = rec
        return base_agent.AgentInteractionResult(bool(rec.get("done")), {"envoy_run_id": run_id, "envoy_status": rec.get("status")})


def build_suite(tasks: list[str] | None, seed: int, instances: list[int]) -> suite_utils.Suite:
    reg = registry.TaskRegistry().get_registry(family=registry.TaskRegistry.ANDROID_WORLD_FAMILY)
    suite = suite_utils.create_suite(reg, n_task_combinations=max(instances) + 1, seed=seed, tasks=tasks)
    out = suite_utils.Suite({name: [insts[i] for i in instances] for name, insts in suite.items()})
    out.suite_family = registry.TaskRegistry.ANDROID_WORLD_FAMILY
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--agent", choices=["envoy", "noop", "hand"], default="envoy")
    ap.add_argument("--tasks", default="", help="comma-separated task names (default: all, or the --split half)")
    ap.add_argument("--split", choices=["dev", "held_out"])
    ap.add_argument("--seed", type=int, default=30, help="AndroidWorld's task_random_seed (standard: 30)")
    ap.add_argument("--instances", default="0", help="instance indices per task (0 = the standard instance)")
    ap.add_argument("--config", default="{}", help="Envoy RunConfig overrides as JSON (stages after the baseline)")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    split = json.loads((RESULTS / "split.json").read_text())
    tasks = [t for t in args.tasks.split(",") if t] or (split[args.split] if args.split else None)
    instances = [int(i) for i in args.instances.split(",")]
    out = RESULTS / args.stage
    (out / "episodes").mkdir(parents=True, exist_ok=True)
    (out / "traces").mkdir(parents=True, exist_ok=True)
    ckpt = WORK / args.stage / "checkpoint"
    ckpt.mkdir(parents=True, exist_ok=True)

    env = aw_env.connect()
    reset_by_setup = aw_env.ensure_setup(env)  # Android deletes AndroidWorld's app snapshots on every boot (aw_env)
    suite = build_suite(tasks, args.seed, instances)
    config = json.loads(args.config)
    agent = {"noop": lambda: NoopAgent(env), "hand": lambda: HandAgent(env, args.stage),
             "envoy": lambda: EnvoyAgent(env, args.stage, config)}[args.agent]()
    agent.transition_pause = None

    run_meta_path = out / "run.json"
    meta = json.loads(run_meta_path.read_text()) if run_meta_path.exists() else {"sessions": []}
    meta.update({"stage": args.stage, "agent": args.agent, "seed": args.seed, "instances": instances, "split": args.split,
                 "tasks": sorted(suite), "androidworld_commit": aw_env.aw_commit(),
                 "emulator": "AndroidWorldAvd: Pixel 6 1080x2400 420 dpi, API 33 google_apis arm64-v8a r17, 4 GB",
                 "envoy_config": config, "tier": config.get("tier", "contributor") if args.agent == "envoy" else None})
    meta["sessions"].append({"started": dt.datetime.now().isoformat(timespec="seconds"),
                             "envoy_commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                             "note": args.note, "androidworld_setup_rerun": reset_by_setup,
                             "app_snapshots": aw_env.snapshot_count()})
    run_meta_path.write_text(json.dumps(meta, indent=1))

    def record(episode: dict[str, Any]) -> bool:
        name, seed = episode[EC.TASK_TEMPLATE], episode[EC.SEED]
        rec = getattr(agent, "last", None) or {}
        key = f"{name}__s{seed}"
        dig = WORK / args.stage / "episodes" / f"{rec.get('run_id', '')}.jsonl.gz"
        if rec.get("run_id") and dig.exists():
            shutil.copy(dig, out / "traces" / f"{key}.jsonl.gz")
            rec["trace_digest"] = str((out / "traces" / f"{key}.jsonl.gz").relative_to(REPO))
        joined = {"task": name, "seed": seed, "goal": episode[EC.GOAL], "score": float(episode[EC.IS_SUCCESSFUL]),
                  "aw_run_time_s": round(episode[EC.RUN_TIME], 1), "aw_episode_length": episode[EC.EPISODE_LENGTH],
                  "agent": args.agent, "finished": str(episode[EC.FINISH_DTIME]), "envoy": rec}
        (out / "episodes" / f"{key}.json").write_text(json.dumps(joined, indent=1, ensure_ascii=False, default=str))
        print(f"### {name} s{seed}: score {joined['score']} · envoy {rec.get('status', '-')} · {rec.get('iterations', '-')} steps"
              f" · ${rec.get('cost_usd', 0):.4f} billed (${rec.get('cost_at_standard_usd', 0):.4f} std) · {joined['aw_run_time_s']} s", flush=True)
        return True

    results = suite_utils.run(suite, agent, checkpointer=checkpointer_lib.IncrementalCheckpointer(str(ckpt)),
                              check_episode_fn=record)
    seeds = {name: [inst.params[EC.SEED] for inst in insts] for name, insts in suite.items()}
    for ep in results:  # harness exceptions (init, scoring, teardown) are recorded too, never silently dropped
        if ep.get(EC.EXCEPTION_INFO):
            seed = seeds[ep[EC.TASK_TEMPLATE]][int(ep.get(EC.INSTANCE_ID) or 0)]
            key = f"{ep[EC.TASK_TEMPLATE]}__s{seed}"
            path = out / "episodes" / f"{key}.json"
            if not path.exists():
                path.write_text(json.dumps({"task": ep[EC.TASK_TEMPLATE], "seed": seed, "goal": ep.get(EC.GOAL),
                                            "score": 0.0, "harness_exception": str(ep[EC.EXCEPTION_INFO])[-3000:],
                                            "agent": args.agent}, indent=1, default=str))
    n = len(results)
    ok = sum(float(ep.get(EC.IS_SUCCESSFUL) or 0) for ep in results if not ep.get(EC.EXCEPTION_INFO))
    print(f"\n{args.stage}: {ok:g}/{n} (exceptions: {sum(1 for ep in results if ep.get(EC.EXCEPTION_INFO))})")
    env.close()


if __name__ == "__main__":
    main()
