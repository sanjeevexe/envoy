"""doordash_order_meal v7 from v6 (data only): wait for checkout until it shows Place Order or Select Payment Method (up to
~13 s), instead of v6's fixed 3 s, so a slow checkout can't make the optional place_order skip its ask (the coordinator,
Oct 30). Routine checks have no "either", so the wait is built from steps the executor already runs:

  1. checkout_opened: wait 0.5 s, after-check: the cart page ("Your cart from") is gone, retried like any after-check;
  2. wait_while_checkout_loads, x3, optional: wait 4 s, but only while neither "Place Order" nor "Select Payment Method" is
     on screen (two text_absent before-checks); once either shows, each is skipped (~1 s);
  3. place_order, unchanged: optional, irreversible and money, so it always asks when Place Order shows.

On envoy-real's test account (no payment method) the sheet comes at once: about 4 s of skips, then the routine ends there.

  uv run --project backend python eval/loop_a/make_doordash_v7.py
"""
from routines.model import Check, Step, StepAction
from routines.store import RoutineStore

lib = RoutineStore()
r = lib.get("doordash_order_meal", 6).model_copy(deep=True)
steps = [s for s in r.steps if s.id != "wait_for_checkout"]
at = [s.id for s in steps].index("place_order")
opened = Step(id="checkout_opened", intent="Wait for the cart to give way to checkout", action=StepAction(kind="wait", seconds=0.5),
              post=[Check(kind="text_absent", text="Your cart from")], risk="read", note="loop A v7")
loading = [Step(id=f"wait_while_checkout_loads_{k}", intent="Wait while checkout is still loading (neither Place Order nor the "
                "payment sheet yet)", optional=True, action=StepAction(kind="wait", seconds=4.0),
                pre=[Check(kind="text_absent", text="Place Order"), Check(kind="text_absent", text="Select Payment Method")],
                risk="read", note="loop A v7: wait-until built from steps; skipped once either shows") for k in (1, 2, 3)]
r.steps = steps[:at] + [opened, *loading] + steps[at:]
r.changes = ["after Continue, wait until checkout shows Place Order or Select Payment Method (up to ~13 s: the cart gone, then up to "
             "three 4 s waits while neither shows) instead of a fixed 3 s, so a slow checkout can't skip place_order's ask "
             "(loop A, Oct 30)"]
out = lib.add(r, verification={"by": "loop-a", "how": "replays in eval/results/real-apps/loop-a/runs.jsonl (task doordash_real)"})
print(out.routine, out.version, out.status, [s.id for s in out.steps][-7:])
