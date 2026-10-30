"""starbucks_drink_calories v4 from v1 (data only): Starbucks' location prompt ("No, thanks" / "Share location") comes after Order on
some launches, after Skip on others, and not at all on some. v1 asked for it in tap_order's after-checks, so a launch
without it (or with it late) failed tap_order or tap_skip_cafe_selection and the repairs, then the agent, took over: on
b1f3c9a 2 of 4 replays fell back to the agent (103-113 s, ~$0.10). Now:
  - tap_order only checks that the screen changed;
  - dismiss_location_prompt checks that the prompt is gone (not "No cafés found", which depends on the area);
  - tap_skip_cafe_selection only checks that the screen changed (the café dialog or the prompt may come next);
  - dismiss_location_prompt_after_skip, the same optional step again after Skip.

  uv run --project backend python eval/loop_a/starbucks_v2.py
"""
from routines.model import Check, Locator
from routines.store import RoutineStore

lib = RoutineStore()
r = lib.get("starbucks_drink_calories", 1).model_copy(deep=True)  # v1, not the self-repair's v3 (Choose a café inserted)
steps = {s.id: s for s in r.steps}
prompt_gone = Check(kind="element_absent", locator=Locator(resource_id="button2", text="No, thanks", kind="Button"))
steps["tap_order"].post = [Check(kind="screen_changed")]
steps["dismiss_location_prompt"].post = [Check(kind="screen_changed"), prompt_gone]
steps["tap_skip_cafe_selection"].post = [Check(kind="screen_changed")]
again = steps["dismiss_location_prompt"].model_copy(deep=True)
again.id, again.note = "dismiss_location_prompt_after_skip", "loop A: the prompt can come after Skip instead; optional"
r.steps.insert([s.id for s in r.steps].index("tap_skip_cafe_selection") + 1, again)
r.changes = ["the location prompt is optional wherever it comes: tap_order and tap_skip_cafe_selection no longer require it (or the "
             "café dialog) in their after-checks, dismiss_location_prompt checks it is gone, and an optional copy follows Skip "
             "(loop A, Oct 30: on b1f3c9a 2 of 4 replays fell back to the agent at tap_order)"]
out = lib.add(r, verification={"by": "loop-a", "how": "hand fix; replays in eval/results/real-apps/loop-a/runs.jsonl"})
print(out.routine, out.version, [s.id for s in out.steps])
