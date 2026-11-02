# policy

Every action passes through here before it runs, including actions that routines replay and actions an agent's task takes. No agent can approve: Envoy has no approve tool.

| File | What |
| --- | --- |
| `risk.py` | Labels each action read, reversible or irreversible. Three independent signals vote: rule patterns on the target's text and ID (pay, place order, confirm, submit, send, delete, cancel trip…, in several languages; plain "Cancel" is safe), the screen context (card ending, will be charged, order total, "this can't be undone"), and the model's own label. Any one saying irreversible pauses the run. |
| `approvals.py` | Only a person approves. `TerminalApprover` asks y/N, and no answer means no. `ScriptedApprover` is for eval on our own test apps and logs every request. The web and iPhone approval flow is `api/approvals.py` (Phase 4–5). |
| `approval_rules.py` | When Envoy may take an irreversible step without asking. Three modes, for everything, per app or per routine: `always`; `unless_requested` (the default: the step the person asked for, in their own words, in Envoy's app); `never` (a routine's standing approval). Money always asks, and so does a request from a trigger, an email, Siri or an agent (MCP), unless a standing approval covers the routine. Rules, not model judgments. |
| `signin.py` | Sign-in detection: a password field, a secure window with a text field, or a sign-in form (an email, phone or code field plus a sign-in button plus a sign-in title). Phase 0 showed the secure flag alone misses most native sign-ins. |
| `botcheck.py` | Bot-check detection: a known blocking activity (Target's `HSBlockActivity`), or a short screen that is mostly a challenge's words ("press and hold", "not a robot", CAPTCHA). Envoy hands these to you, never gets past them; on an emulator the runner also sets the app to your phone. |

Tests: `backend/tests/test_policy_and_screens.py`, run offline on real SkyLark screens.
