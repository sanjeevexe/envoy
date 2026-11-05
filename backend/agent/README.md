# agent

The agent loop: plan, then observe → decide → check policy → act → verify → record, one model call per step (Muse Wonder on the default `hybrid` profile).

| File | What |
| --- | --- |
| `loop.py` | `AgentRunner.run(goal)`: the loop, limits, stuck recovery and `done` verification. Returns a `RunResult` with status, result, steps, model calls, tokens, cost, approvals and a trace path. |
| `checks.py` | Success checks evaluated in code on the final screen. `info` checks require the answer to be visible on screen, so answers can't be made up. |
| `popups.py` | Shared pop-up handler (permission, rating and notification prompts, "app not responding"), answered with the declining option and no model call. |
| `vision.py` | Finding a described target on a screenshot when the screen has no tree: SAM 3.1 proposes regions and the model picks one, with Muse Spark's visual grounding as the fallback (52 of 52 in Phase 6). |
| `trace.py` | Run traces in `data/runs/<task_id>/`: `steps.jsonl`, gzipped before and after trees, downscaled screenshots. The input for the routine compiler. |

## One step

1. **Observe:** wait until the screen settles, then read the compact screen (`devices/screen.py`).
2. **Sign-in?** A password field, a secure window with a text field, or a sign-in form means stop with status `handoff` (`policy/signin.py`). The agent never types passwords.
3. **Pop-up?** A known interruption is dismissed in code.
4. **Stuck?** If the same screen comes back three times with no effect: first tell the model, then press back, then fail.
5. **Decide:** the step model (Muse Wonder on `hybrid`; Muse Spark 1.3 at `low` on `spark`), with structured output (`models/schemas.py` StepOutput). The model sees:
   - the cached instructions
   - the goal and plan
   - the last 5 actions and their outcomes
   - notes
   - the screen
   - a 540-px screenshot, only when the tree is sparse, the last action did nothing, or the model asked with `look`. Never on secure screens.
6. **Policy:** the element number is validated, then `policy/risk.py` classifies the action. Rules, screen context and the model's label each vote, and any "irreversible" vote asks the approver (terminal, or scripted in eval). A declined action is reported back to the model.
7. **Act, verify, record:** act through the device, settle, compare screens. "No visible change" is reported, and the next step gets a screenshot.
8. **Done:** the planner's success check runs in code. If it fails, `done` is rejected (up to 2 times) and the model is told what's missing.

## Run it

```bash
uv run --project backend python scripts/run_task.py "Check me in for my flight to Chicago" --skylark --approve-all
uv run --project backend python eval/run_skylark.py                  # the SkyLark task set
python3 scripts/show_trace.py <task_id>                              # what happened, step by step
```
