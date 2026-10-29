"""Three candidate fixes for the template-like first `back`, on bags_boston's warm first step (notes on)."""
import concurrent.futures as cf, sys
sys.path.insert(0, "/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/00162ac0-c405-47a1-87b7-50b0092e9381/scratchpad")
import replay_first_step as R
from pydantic import Field
from models.schemas import AgentActionListed, _Strict
from typing import Literal

class ActionFirst(_Strict):
    action: AgentActionListed
    reason: str = Field(description="One short sentence: why this action")
    expected_result: str = Field(description="What the screen should show after the action, checkable by code")
    risk: Literal["read", "reversible", "irreversible"]

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
plan, screen = R.first_step("bags_boston")
goal = R.GOALS["bags_boston"]
adapter = R.ModelAdapter()

def call(text, effort="low", schema=R.StepOutputListed, tid="x"):
    res = adapter.call("step", [{"type": "input_text", "text": text}], instructions=R.STEP_INSTRUCTIONS, data_scope="test_app",
                       contributor=False, task_id=f"probe-fix-{tid}", effort=effort, schema=schema)
    return res.parsed, res.cost_at_standard_usd

def text(feedback=""):
    return R.step_input(goal, screen, plan=plan, history="", memory="", feedback=feedback, visited="Good morning, Maya ×1", app_notes=R.NOTES)

def medium(i):
    d, c = call(text(), effort="medium", tid=f"medium-{i}"); return d.action.type == "back", c, d.reason
def action_first(i):
    d, c = call(text(), schema=ActionFirst, tid=f"actfirst-{i}"); return d.action.type == "back", c, d.reason
def reask(i):
    d, c = call(text(), tid=f"reask-{i}")
    if d.action.type != "back":
        return False, c, "first try fine"
    fb = (f"Your last reply chose `back`, but its reason was: \"{d.reason}\". Back would leave the app this goal needs. "
          "Return the action you meant, for an element on this SCREEN.")
    d2, c2 = call(text(fb), tid=f"reask2-{i}")
    return d2.action.type == "back", c + c2, f"re-asked after: {d.reason[:50]} -> {d2.action.type}"

total = 0.0
for name, fn in (("medium effort", medium), ("action before reason", action_first), ("re-ask once on a contradicting back", reask)):
    with cf.ThreadPoolExecutor(8) as ex:
        rs = list(ex.map(fn, range(N)))
    total += sum(r[1] for r in rs)
    print(f"{name}: back left {sum(r[0] for r in rs)}/{N}")
    for r in rs:
        if r[0] or "re-asked" in r[2]:
            print("    ", r[2][:110])
print(f"cost ${total:.3f}")
