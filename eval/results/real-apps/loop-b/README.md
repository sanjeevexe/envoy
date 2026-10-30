# Loop B: new real apps on envoy-real (Oct 30 to the Nov 1 22:00 ET cut)

Brief: `prompts/loop-new-apps.md`. Rows go to `../table.md`; every run's record is in `runs.json` here, written by
`eval/run_new_apps.py` (a task on the API copy :8751, hybrid, envoy-real by name; every approval declined; a sign-in or
bot check stops the run). Before each first run the app is force-stopped and Envoy's notes about it are retired, so
each first run is cold. Routines saved from a successful first run are in `data/routines/<name>/`.

## Apps checked

| app | package | signed in | outcome |
| --- | --- | --- | --- |
| Uber | com.ubercab | user (real account), on the Pixel 5 | not installable on envoy-real ("available only for your other devices"); installed on the Pixel 5 Oct 30 14:59 at the user's request, signed in by the user; runs are numbers only (`--private`) |
| Lyft | me.lyft.android | user (real account) | installed Oct 30 13:40; opens to "Get started", no emulator block; location ask answered "Don't allow" |
| Spotify | com.spotify.music | — | **skipped**: sign-in fails on the emulator (Google sign-in errored; the emailed code was rejected), Oct 30 ~15:30 |
| CapCut | com.lemon.lvoverseas | user | installed Oct 30 13:41; terms accepted and signed in by the user |
| Clock | com.google.android.deskclock | no | preinstalled; routine `clock_set_alarm` v5 (hand-fixed) 5/5 |
| Google Maps | com.google.android.apps.maps | no (phone's Google account) | preinstalled; `maps_get_driving_time` v6 awaiting replays (not in this branch yet) |
| Google Calendar | com.google.android.calendar | phone's Google account | preinstalled; first runs only, no readable output for a routine |
| Google app | com.google.android.googlequicksearchbox | phone's Google account | launching it leaves "android" in front; routine paused (not in this branch) |
| Chrome / Google Flights | com.android.chrome | no | every typed step asks approval (Chrome's "Show saved payment methods" bar trips the checkout rule); skipped |

## What the routines needed by hand (Oct 30)

- **Clock**: the compiler templated an ID with the input (`material_clock_period_{{alarm_period}}_button`, but the app writes
  `..._am_button`) and read the first alarm row, so a wrong alarm still read as done. A bad patch (AM/PM step removed)
  then passed its trial with a wrong answer, because a trial only asks "done with no model call".
- **Maps**: the first runs left their places in Maps' history; the compiled run (run 3) tapped remembered suggestions,
  so no new place could be reached without repair. Typed suggestions are ambiguous (Mountain View · CA, · AR, · MO …);
  type + Enter takes Maps' best match.
- **Google app**: compiled with app `android` and a launcher detour; launching the app by package leaves "android" in front.
