"""A routine loop A compiled as loop_<task> becomes <app_task> (the coordinator's naming), same steps, version 1 under the
new name; the loop_ one is removed from the library.

  uv run --project backend python eval/loop_a/rename.py loop_amazon amazon_search_price
"""
import shutil
import sys

from routines.store import RoutineStore

old, new = sys.argv[1], sys.argv[2]
lib = RoutineStore()
r = lib.get(old).model_copy(deep=True)
was = r.version
r.routine = new
r.changes = [f"named {new} (was {old} v{was} in loop A's copy; same steps)", *(r.changes or [])]
out = lib.add(r, verification={"by": "loop-a", "renamed_from": f"{old} v{was}"})
shutil.rmtree(lib.root / old)
print(out.routine, out.version, out.status, list(out.inputs), len(out.steps))
