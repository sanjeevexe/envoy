"""Loop A's hand fixes to two routines compiled from first runs (data only), each the next version of the library's:

  loop_starbucks v2: drink_name says it is the menu name without the size. The matcher filled "Grande Caffè Latte" from
    "how many calories are in a Grande Caffè Latte?", which no search result row has ("Caffè Latte"), so
    find_tap_drink_result failed and the agent took over in 6 of 6 replays (Oct 30, 70-149 s, ~$0.09 each).
  loop_chipotle v2: the pickup location and the menu category the first run chose are fixed values, not inputs. The
    request names only the item, so with three inputs the runner said "needs location_search, menu_category" and the
    agent ran instead in 6 of 6 replays.

  uv run --project backend python eval/loop_a/make_v2.py starbucks|chipotle
"""
import json
import sys

from routines.store import RoutineStore


def fix(r, name: str, value: str) -> None:
    """Every {{name}} in the routine's steps becomes the fixed value; the input goes."""
    text = json.dumps([s.model_dump(mode="json", exclude_none=True) for s in r.steps], ensure_ascii=False)
    r.steps = [type(r.steps[0]).model_validate(s) for s in json.loads(text.replace("{{" + name + "}}", value))]
    r.inputs.pop(name)
    for attr in ("intent", "description"):
        setattr(r, attr, (getattr(r, attr) or "").replace("{{" + name + "}}", value))


lib = RoutineStore()
which = sys.argv[1]
if which == "starbucks":
    r = lib.get("loop_starbucks", 1).model_copy(deep=True)
    r.inputs["drink_name"].description = ("The drink's name as the Starbucks menu lists it, without its size (Tall, Grande, Venti) "
                                          "or milk, e.g. Caffè Latte for 'a Grande Caffè Latte'")
    r.changes = ["drink_name is the menu name without the size: the matcher filled 'Grande Caffè Latte', which no search result row "
                 "has, so find_tap_drink_result failed and the agent took over in 6 of 6 replays (loop A, Oct 30)"]
elif which == "chipotle":
    r = lib.get("loop_chipotle", 1).model_copy(deep=True)
    fix(r, "location_search", r.inputs["location_search"].example)
    fix(r, "menu_category", r.inputs["menu_category"].example)
    r.changes = ["the pickup location and menu category are the first run's values, not inputs: the request names only the item, so "
                 "the runner sent every replay to the agent (needs location_search, menu_category; loop A, Oct 30)"]
else:
    sys.exit(__doc__)
out = lib.add(r, verification={"by": "loop-a", "how": "hand fix after live replays (eval/results/real-apps/loop-a/runs.jsonl)"})
print(out.routine, out.version, out.status, list(out.inputs), len(out.steps))
