"""The dev / held-out split of AndroidWorld's 116 tasks, fixed before any results are seen.

  eval/androidworld/aw.sh split.py        # writes eval/results/androidworld/split.json

Stratified by app and difficulty: tasks are grouped by (app, difficulty), each group is shuffled with a fixed seed, and
its tasks alternate between the halves, with the starting half alternating from group to group, so each half gets
about half of every app and every difficulty. "App" is the task's first AndroidWorld app (multi-app tasks are grouped
under "multi-app"); difficulty is AndroidWorld's own label (task_metadata.json). This metadata is for splitting and
reporting only: the agent never sees it.

Also records each task's step budget for seed 30 (AndroidWorld's int(10 * complexity)).
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from android_world import registry, suite_utils

import aw_env

SPLIT_SEED = 20261027
TASK_SEED = 30  # AndroidWorld's standard seed (run.py --task_random_seed default)
OUT = Path(__file__).resolve().parents[2] / "eval" / "results" / "androidworld" / "split.json"


def app_of(task) -> str:
    apps = [a for a in task.app_names if a]
    if len(set(apps)) > 1:
        return "multi-app"
    return apps[0] if apps else "none"


def main() -> None:
    reg = registry.TaskRegistry().get_registry(family=registry.TaskRegistry.ANDROID_WORLD_FAMILY)
    suite = suite_utils.create_suite(reg, n_task_combinations=1, seed=TASK_SEED)
    meta = {m["task_name"]: m for m in json.loads((aw_env.AW_DIR / "android_world" / "task_metadata.json").read_text())}
    tasks = {}
    for name, (inst,) in suite.items():
        tasks[name] = {"app": app_of(inst), "difficulty": meta[name]["difficulty"], "complexity": inst.complexity,
                       "step_budget": int(10 * inst.complexity), "tags": meta[name]["tags"]}
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for name, t in sorted(tasks.items()):
        groups[(t["app"], t["difficulty"])].append(name)
    rng = random.Random(SPLIT_SEED)
    halves: dict[str, list[str]] = {"dev": [], "held_out": []}
    start = 0
    for key in sorted(groups):
        names = groups[key]
        rng.shuffle(names)
        for i, name in enumerate(names):
            halves["dev" if (i + start) % 2 == 0 else "held_out"].append(name)
        start += len(names) % 2  # an odd group's extra task goes to the other half next time
    for h in halves.values():
        h.sort()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"split_seed": SPLIT_SEED, "task_seed": TASK_SEED, "androidworld_commit": aw_env.aw_commit(),
                               "dev": halves["dev"], "held_out": halves["held_out"], "tasks": tasks}, indent=1))
    for h, names in halves.items():
        by_d = defaultdict(int)
        for n in names:
            by_d[tasks[n]["difficulty"]] += 1
        print(f"{h}: {len(names)} tasks, {dict(by_d)}, {len({tasks[n]['app'] for n in names})} apps")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
