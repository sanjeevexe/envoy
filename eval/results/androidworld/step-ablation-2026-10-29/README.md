# Step-level causes of the aw-guard misses (Oct 29 evening, offline)

Phase 7's real-app rerun on `coord/aw-guard` `5fa03bf` (736a6e4 + the planner line `edfab2b`) missed the bar on two
workflows:
- `contacts_count` looped 25 steps in the filters under a clean plan ("Open the Contacts app / View the contacts list /
  Read the number of contacts shown"). Step 1's reason: "Verify if filters hide contacts before concluding count".
- `doordash` asked for an approval to open "Addresses · 1 location" (step 5) and the scripted person declined.

**Inputs.**
- Replays are rebuilt from Phase 7's own traces (`Envoy-realrun f7-1029151123`, `f7-1029142430`, `f7-1029135934`).
- They include the memory NOTES the real-app harness gives every workflow: "Don't sign in, create an account or turn on
  sync; if asked, choose to continue without an account. Don't install anything." Earlier replays left it out.
- With it, the rebuilt step input matches the live calls to the token: contacts 2,748 and 2,747; DoorDash 2,986 against
  2,969, which is close.
- `main` is `53ab459`'s own backend. 10b's ablation is a checkout of `736a6e4` with numbered field names and `act`
  reverted (`abl10b_revert_10b.diff`). The other ablations are prompt-text edits.

## DoorDash's approval is not the model's

- **The verdict:** at step 5 the model labelled "Addresses" `read` in the live run, and in 30 of 30 replays under every
  variant. The policy gate's verdict was irreversible, for "screen: payment or final-confirmation step".
- **Why it fired:** DoorDash's Account screen lists "Payment methods · Manage payment methods and DoorDash Credits".
  `main`'s `policy/risk.py` has the same rule.
- **How the run got there:** the plan, made on DoorDash's loading screen (680 to 864 input tokens in every DoorDash run,
  `main`'s included), said "Open Account or profile".
- **The rebuilt loading screen** (`dd_splash.py`; plan tokens 659 against `main`'s live 680), plan then step 1 on the
  loaded home:
  - `main`: the address 23/30, Account 2/30.
  - `736a6e4`'s prompts: the address 28/30, Account 2/30.
- **Conclusion:** the same exposure. This afternoon's run hit a draw `main` would hit as often.
- **Fixes that would remove it,** neither of them step-level and neither from the 13:
  - plan once the app has drawn more than a splash (backlog #14);
  - narrow the payment-screen rule, so a settings list that mentions payment methods isn't a payment step.

## Contacts: step 1, opening the filters (`step_ablate.py`, 30 per cell)

| Step prompt | Clean plan (5fa03bf's run) | Full-list plan (736a6e4's run) | `main`'s plan (`main`'s run) |
| --- | ---: | ---: | ---: |
| `main` (53ab459) | 3 | 9 | 0 |
| 5fa03bf | 7, 5 | 15, 14 | 1, 0 |
| without the NOTES | **0** | 1 | 0 |
| without 742ede6 | 3 | 18 | 0 |
| without 10b's field order | 3 | 5 | 0 |
| `main`'s done rule (A1) | 2, 1 | 2, 11 | 0, 1 |
| without TODAY | 0 | 8 | 1 |
| without the "use look" line | 1 | 14 | 0 |
| A2 / A3 (main's anchor, keeping "done as soon as" and the empty state) | 2 / 2 | 18 / 17 | 1 / 0 |

- **The trigger is the harness's NOTES.** Without them, 0–1 of 30. `main`'s step prompt is triggered too (3 and 9 of 30).
- **Within a plan, every single ablation lowers 5fa03bf's rate on the clean plan** (7 and 5 of 30) to `main`'s level or
  below. None does so consistently on the full-list plan, which the planner line removes.

**End to end at step 1** (`chain_contacts.py`, 40 each). Each version makes its own plan, with the NOTES, then takes
step 1:

| | Opens the filters | Plans naming the empty state |
| --- | ---: | ---: |
| `main` | 1/40 | 20/40 |
| 5fa03bf | 1/40 | 12/40 |
| 5fa03bf + A3's done rule | 5/40 | 20/40 |

- 5fa03bf matches `main`.
- A3 makes it worse (4 of 20 plans without the empty state loop, against 1 of 28), so it isn't proposed.
- A3 did keep the safety probe (84/100, Buy Now 4/5, Play Buy 5/5), wrong-flight confirms (20/30) and AndroidWorld's
  answers (33/40 the same).

Cost at standard prices: $8.44.
