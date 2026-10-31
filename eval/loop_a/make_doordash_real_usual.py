"""doordash_order_meal v6 (data only): the user's real usual from Chick-fil-A, a Spicy Chicken Sandwich on its own, on
DoorDash (relayed by the coordinator, Oct 30 21:25), compiled from loop A's cleanest first run (task-1030-212646-1800-r1:
search, store, Entrées, the sandwich, Add to order, cart, Continue, the payment sheet) and fixed by hand like v4/v5:

  - the choices are fixed, not inputs (Chick-fil-A, Spicy Chicken Sandwich), so the matcher refuses it for any other order;
  - the menu row is exact (text "Spicy Chicken Sandwich", not "Spicy Deluxe Sandwich" or the Meal), and opening it checks
    the item page's title;
  - the compiled options scroll and the cart outputs are dropped (the footer's Add to order is always on screen; outputs
    read after Continue would sit under the payment sheet);
  - after Continue, a 3 s wait for checkout to load, then place_order: tap Place Order, irreversible, so it always asks
    (and it is money: decide() asks even with a standing never-ask). Optional: on an account with no payment method
    (envoy-real's test account) Continue opens "Select Payment Method", Place Order never comes and the routine ends there.
    Check on the Pixel before a take that Place Order appears and asks.

  uv run --project backend python eval/loop_a/make_doordash_real_usual.py
"""
import json
from pathlib import Path

from routines.model import Check, Locator, Step, StepAction, load_yaml
from routines.store import RoutineStore

HERE = Path(__file__).resolve().parent
ITEM, PLACE = "Spicy Chicken Sandwich", "Chick-fil-A"

r = load_yaml((HERE / "doordash_real_usual.compiled.yaml").read_text())
text = json.dumps(r.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
text = text.replace("{{item_name}}", ITEM).replace("{{restaurant_name}}", PLACE)
r = type(r).model_validate(json.loads(text))
r.inputs = {}
r.outputs = []
r.routine = "doordash_order_meal"
r.intent = f"Order my usual from {PLACE} on DoorDash: a {PLACE} {ITEM} on its own"
r.description = (f"Searches DoorDash for {PLACE}, opens Entrées, adds the {ITEM} on its own (no meal) to the cart, continues from the "
                 "cart to checkout and taps Place Order, which always waits for your OK. Only this order: another item or a meal "
                 "is a different request.")
r.patterns = [f"Order my usual from {PLACE} on DoorDash", f"Order me my usual from {PLACE}", f"Order a {PLACE} {ITEM} on its own"]

steps = [s for s in r.steps if s.id != "scroll_item_options"]
by_id = {s.id: s for s in steps}
row = Locator(resource_id="container_card_view", text=ITEM, text_has=ITEM, kind="Button", cls="CardView", in_list=True)
by_id["find_open_menu_item"].action.target = row.model_copy()
by_id["find_open_menu_item"].post = [Check(kind="element_present", locator=row.model_copy())]
by_id["open_menu_item"].action.target = row.model_copy()
by_id["open_menu_item"].post = [Check(kind="screen_changed"),
                                Check(kind="element_present", locator=Locator(resource_id="collapsingToolbar_navBar", text=ITEM, text_has=ITEM, kind="Text"))]
cont = by_id["continue_to_checkout"]
cont.extract = None
wait = Step(id="wait_for_checkout", intent="Wait for checkout to load", action=StepAction(kind="wait", seconds=3.0), risk="read",
            note="loop A: so place_order sees the checkout, not a loading screen")
place = Step(id="place_order", intent="Place the order (the payment step: it waits for your OK)", optional=True,
             pre=[Check(kind="app_foreground", package="com.dd.doordash"),
                  Check(kind="element_present", locator=Locator(text="Place Order", kind="Button"))],
             action=StepAction(kind="tap", target=Locator(text="Place Order", kind="Button", in_list=False)),
             post=[Check(kind="screen_changed")], risk="irreversible",
             note="doordash-usual's template; optional: no payment method on the account means no Place Order")
steps += [wait, place]
r.steps = steps
r.changes = [f"the user's real usual: a {ITEM} on its own (was the placeholder Deluxe Meal), compiled from task-1030-212646-1800-r1; "
             "fixed choices, the exact menu row and the item page's title; a 3 s wait and an optional, irreversible place_order "
             "after Continue (loop A, Oct 30)"]
out = RoutineStore().add(r, verification={"by": "loop-a", "how": "replays in eval/results/real-apps/loop-a/runs.jsonl (task doordash_real)"})
print(out.routine, out.version, out.status, [s.id for s in out.steps])
