# The Instagram scene, rehearsed on hybrid (Oct 30, overnight)

Session `insta-rehearsal` (owner name `creator-workflow` on `pixel5`), branch `claude/insta-rehearsal-ee37b3` from main
`501c463` (rehearsed there), rebased onto `1566a36`. API copy on :8746 with its own data dir, token and outbox (scratchpad); never :8700 or `data/api`. The Pixel 5
(Android 13, Instagram 453, test account envoy3955) over USB. **Nothing was posted**: every rehearsal declined at Share.
No likes, follows, comments or messages. Test clips were 4-second ffmpeg test patterns made in the scratchpad.

## What changed (on this branch)

- **"Envoy's phone"** (`api/devices.py` `phone_ref`, Settings › Phones): a real phone can be given a name, kept in the
  `phone_names` setting and set with `POST /api/settings/phones/name` or the name field under the phone in Settings ›
  Phones. Every line that said "your Pixel 5" now says the name word for word when there is one: the offer's title
  (`handoff.where`), "Before I start" (`preflight._device`, `_where`), the task's notes and the phone ask
  (`runner._choose_phone`, `_ask_for_phone`, the bus event and its push), and Muse's `send_to_phone` / `phone_updates`
  text ("was posted from Envoy's phone"; "their Pixel 5" / "the Pixel 5" when unnamed). Unnamed phones read as before.
  Nothing names the demo or the Pixel.
- **A routine can be switched off** (`RoutineStore.switch`): no version active, versions and runs kept; on brings the
  same version back. An offer whose template names a routine that is off (or missing) now runs the agent with a note
  ("routine instagram_post_reel isn't active: the agent does it instead") instead of failing with a KeyError. Take 1 needs
  this: Instagram's template always names `instagram_post_reel`.
- **`scripts/instagram_take.py`**: a take's starting state in one command (docs/demo-creator-workflow.md, "Setting up a
  take").
- **`scripts/record_phone.sh`**: a full-resolution recording of the phone during a take ("Recording Envoy's phone").
- **`eval/run_creator.py`**: the rehearsal's cleanup leaves the composer with Start over instead of Save draft; only an
  approval that reached the user counts as "asked before Share" (one the request covered doesn't).
- Tests: `backend/tests/test_phone_name.py` (8). Rebased onto main `1566a36`: 654 passed on the default (hybrid) and the spark profile (646 + 8), and `npm run build` passes.

## Results

Every run: a 4 s test clip and its sidecar into the copy's outbox → the offer → this copy's yes → the clip pushed to the
phone → the post runs → **Share asked, declined here**. Times are from the yes to the Share ask (the offer came 4–7 s
after the clip every time). Calls and dollars are the task's, from `logs/model_costs.jsonl` (app notes after the run
not included: ~$0.006 each). All rows are in `eval/results/creator/runs/runs.md` with their JSON.

| Run (Oct 30) | As | Yes → Share | Calls | Cost | Notes |
| --- | --- | --- | --- | --- | --- |
| 03:20 | agent, cold | 105.0 s | 10 (plan 1, step 9) | $0.132 | 54 s of it before the plan: the first agent run in this checkout read every app's name (below) |
| 03:53 | agent, warm | 46.4 s | 9 (plan 1, step 8) | $0.122 | |
| 03:55 | agent, warm | 49.6 s | 9 | $0.115 | |
| 03:27 | routine v2 | 47.5 s | 2 (repair) | $0.033 | |
| 03:35 | routine v2 | – | 2 (repair) | $0.027 | the repair's thumbnail tap **asked the user** (Muse Wonder labelled it irreversible); the script declined it, so no Share |
| 03:37 | routine v2, recorded | 53.5 s | 2 | $0.027 | |
| 03:39 | routine v2 | 48.4 s | 2 | $0.030 | the repair's "Gallery" tap was labelled irreversible too, but the request covered it (no ask) |
| 03:41 | routine v2 | 51.4 s | 2 | $0.032 | |
| 03:43 | routine v3 candidate | 18.2 s | 0 | $0 | |
| 03:44 | routine v3 candidate, recorded | 25.2 s | 0 | $0 | |
| 03:46 | routine v3 candidate | 20.2 s | 0 | $0 | |
| 03:47 | routine v3 candidate | 19.1 s | 0 | $0 | |
| 04:04 | routine v3 candidate, recorded | 23.2 s | 0 | $0 | the setup before it read the app names from a cold cache (51.9 s) |
| 04:05 | routine v3 candidate, recorded | 24.2 s | 0 | $0 | |
| 04:07 | routine v3 candidate | 20.2 s | 0 | $0 | |
| 04:08 | routine v3 candidate, recorded at 30 fps | 22.2 s | 0 | $0 | |
| 04:10 | routine v3 candidate, recorded at 30 fps | 22.2 s | 0 | $0 | |

One more v2 run (03:34) is not in the table: my mistake stopped it (finding 7).

**Against Spark (Oct 29, `docs/demo-creator-workflow.md`):**

| | Spark (Oct 29) | Hybrid (Oct 30) |
| --- | --- | --- |
| Agent alone, Yes → Share | 49.4 s, 12 calls, $0.059 (post 2); 121.8 s, 14 calls, $0.060 (rehearsal with a detour) | 46.4–49.6 s warm, 9 calls, $0.115–0.122 (105 s cold) |
| Routine v2, Yes → Share | 38.3–43.9 s, 2 repair calls, $0.016–0.018 a task | 47.5–53.5 s, 2 repair calls (Wonder: 4–7.5 s each), $0.027–0.033 |
| Routine v3 candidate | – | 18.2–20.2 s (23–25 s recorded at 60 fps, 22 s at 30 fps), 0 calls, $0 |

So on hybrid the agent's first run takes the same time as Spark's best run, with fewer calls at about twice the cost;
v2's two repairs are ~10 s slower on Wonder, and on hybrid they sometimes interrupt with an approval nobody expects.

Spend tonight: **$0.57**, 46 model calls in all (app notes after each run included), against a guide of $3.

## Findings

1. **Why v2 always repairs (and the v3 candidate).** Instagram labels every gallery thumbnail "Unselected Video thumbnail
   created on October 30, 2026 3:27 AM". v2's locator for "Select the newest video" is `text: Video thumbnail` on
   `gallery_grid_item_thumbnail`, which now fits every thumbnail about equally (0.86 vs 0.81, under the 0.08 margin), so
   the executor finds nothing, scrolls the grid to look (`_reveal`: down, then up), and the upward scroll at the top
   pulls Instagram's gallery sheet down into the **front camera**. The repair then taps Gallery and the newest
   thumbnail: 2 Wonder calls, ~13 s, every run (Oct 29's "2 calls" were this too). Envoy's own patch after a successful
   take 2 wouldn't fix it: `locators.updated` would record this run's dated label, which fits every thumbnail the next
   day just as badly. The **v3 candidate** (`eval/results/creator/routine/instagram_post_reel.v3-candidate.yaml`)
   changes only that locator to the grid's first video slot (id, in the list, nearest the recorded position, no text);
   offline it picks the newest clip on all 7 gallery screens recorded tonight, and live it ran 9/9 with 0 calls. It is a
   **hand edit, not something Envoy learned**, so it is not in the library: whether take 2 uses it (and whether the
   video says "learned") is the user's call. A general fix (the compiler or the patcher treating dated labels as data,
   like booking rows) is agent code, past what should change before the cut.
2. **Approvals nobody expects on hybrid.** Muse Wonder, repairing, labelled harmless taps irreversible in 2 of 5 v2 runs
   ("Gallery", then the thumbnail). One was covered by the request (no ask), one asked the user. In a take, approve it
   and Share still asks; v3 has no repair there.
3. **The first agent run per checkout reads the phone's app names** (`devices/apps.py`: pulls each launchable APK, runs
   aapt2, caches `data/apps/labels.json`): 54 s before the plan in this fresh checkout, 10 s once cached. The main
   checkout has no `data/apps/` yet, so take 1 on the live API would pay it. `scripts/instagram_take.py` now reads them
   first: 51.9 s for the Pixel's 24 apps on a cold cache (the file came out byte-identical to the agent's), ~1 s after.
4. **"Keep editing your draft?" comes back after every restart** once a reel was started, even after "Start over"
   (which only resets the editor); every run restarts Instagram (fresh launch), so a rehearsal's leftover always met the
   next run. "Start new video" is the only answer that clears it, and it keeps the half-made reel as a private draft.
   The setup script does that and then checks Create → gallery after two restarts; each rehearsal therefore leaves one
   private draft (Drafts went 6 → 23 tonight). Deleting drafts was refused by the permission classifier for me, so
   they're the user's to delete (Create › Drafts › ⋯ › Delete). Oct 29's cleanup saved a draft every rehearsal too.
5. **The camera repair sees the room.** When the gallery fell into the front camera, the repair's screenshot (sent to
   Muse Wonder) showed whatever the front camera faced. I didn't look at those images; worth knowing before a take on
   v2, and v3 never opens the camera.
6. **The recording** (`scripts/record_phone.sh`): full 1080×2340 H.264 at up to 60 fps (variable: ~25–28 fps average),
   ~9 Mbit/s in practice (49 MB for 45 s). A second scrcpy beside Envoy's caused no errors. Timing effect: it does slow Envoy a
   little, because the Pixel encodes the screen twice. v3 runs took 23.2–25.2 s Yes → Share recorded at 60 fps (3 runs)
   and 22.2 s at 30 fps (2) vs 18.2–20.2 s unrecorded (4); the routine's own steps 19.2–20.7 s vs 16.5–17.5 s. Fine for
   a time-lapsed take; `-f 30` halves the cost.
   Two gotchas fixed in the script: the Pixel tags its video YCgCo (rewritten to BT.601, lossless), and a background
   recorder ignores SIGINT (the script turns Ctrl-C or SIGTERM into scrcpy's clean stop). Envoy's banner
   ("Envoy is using this phone · Pause") is in the footage over Instagram's title bar while Envoy works.
7. **Mistake of mine, for the record:** at 03:34 I opened the copy's `envoy.db` with `TaskStore()` from another process
   to read `phone_updates`; its start-up sweep marked the running rehearsal stopped. I stopped the scripts, restarted the
   copy and removed that run's row. Nothing was posted (the Share gate never opened). Read a live API's store over HTTP.

## Left for the morning (the user)

- **Take 2 on v2 or the v3 candidate.** v2 is what Envoy learned and repairs twice a run (~50 s, sometimes an extra
  approval); v3 is one locator I edited (~19 s, 0 calls). To use v3, the coordinator adds it to the library (a demo-scene
  routine may merge after the cut): `uv run --project backend python eval/run_creator.py add-routine
  eval/results/creator/routine/instagram_post_reel.v3-candidate.yaml` from the checkout that films (it refuses unless
  Share stays irreversible and the caption is an input). Its `changes` line says it was a hand edit.
- **Instagram drafts**: "Drafts · 23" on the gallery screen (rehearsals, private). Delete them by hand before filming
  if they shouldn't show (Create › Drafts › ⋯ › Delete › Delete); the classifier refused that action for me.
- **Muse "Posted"**: the 5-minute check in `docs/demo-creator-workflow.md` ("Muse reports back").
- **Name the phone** on the API that films: Settings › Phones › "Envoy's phone" (after the coordinator merges this
  branch and restarts :8700), or `scripts/instagram_take.py --api-dir <its data dir>`.
- **Warm the app names** on that checkout before take 1: `scripts/instagram_take.py` does it (one minute the first time).
- **Keep-awake**: the app's classifier refused my request to keep the Mac awake overnight; the work finished anyway.
