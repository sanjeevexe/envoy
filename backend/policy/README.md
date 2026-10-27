# policy

Every action passes through here before it runs, including actions that routines replay.

| File | What |
| --- | --- |
| `risk.py` | Labels each action read, reversible or irreversible. Three independent signals vote: rule patterns on the target's text and ID (pay, place order, confirm, submit, send, delete, cancel trip…, in several languages; plain "Cancel" is safe), the screen context (card ending, will be charged, order total, "this can't be undone"), and the model's own label. Any one saying irreversible pauses the run. |
| `approvals.py` | Only a person approves. `TerminalApprover` asks y/N, and no answer means no. `ScriptedApprover` is for eval on our own test apps and logs every request. The web and iPhone approval flow arrives in Phase 4. |
| `signin.py` | Sign-in detection: a password field, a secure window with a text field, or a sign-in form (an email, phone or code field plus a sign-in button plus a sign-in title). Phase 0 showed the secure flag alone misses most native sign-ins. |

Tests: `backend/tests/test_policy_and_screens.py`, run offline on real SkyLark screens.
