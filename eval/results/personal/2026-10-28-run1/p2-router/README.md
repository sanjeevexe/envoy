# Run 1's P2: chat's router said "no routine for that" (replayed Oct 29)

**What:** in run 1, "Add a checked bag to my Chicago trip." got a reply instead of a task: "Sorry, I can't add a checked
bag to your Chicago trip — I don't have a routine for that in the SkyLark app." The router (`api/chat.py`, one Spark call)
sees the request and a list headed "APPS (learned routines)". SkyLark has six routines there and none adds a bag, and
nothing in `CHAT_INSTRUCTIONS` says a task needs no routine. In run 2 the same request was routed as a task.

**Replayed** (`replay_router.py`: the router's own input with run 1's routine list, `apps.txt`; Spark, `low`, standard
tier; the router is unchanged on main at fb3d926; two batches, 10 then 30 per condition; $0.58 in all;
`replay-output.txt`):

| Request | Right route | As is | With one more instruction line |
| --- | --- | --- | --- |
| Add a checked bag to my Chicago trip. (no routine) | task | **6/40 replied "can't"** | **0/40** |
| Which seat am I in on my Denver flight? | memory or task | 0/20 wrong | 0/20 wrong |
| Turn on Wi-Fi. (no routine either) | task | 0/20 wrong | 0/20 wrong |
| What can you do? | reply | 0/20 wrong | 0/20 wrong |

So about 1 in 7 times, a request to do something in an app that has routines, but none for this, is refused. A request
in an app with a routine list that doesn't cover it (Settings: Bluetooth and the Android version, not Wi-Fi) wasn't, in
20 tries. The line tested:

> A task needs no learned routine: APPS lists only what Envoy has already learned, and it can do anything else in a
> phone app too, so a request to do something in an app is a task even when APPS has nothing for it.

**The fix (not made here):** add that line to `CHAT_INSTRUCTIONS` in `backend/models/prompts.py`.
