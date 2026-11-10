# Round 4 offline checks: real apps, SkyLark, safety, replans and last steps (Nov 9 2026)

These are recorded inputs replayed on `main` (`ed98762`, exported with `git archive`) and on the branch, on the hybrid profile's step model (Muse Wonder 1.0). Each side rebuilds a screen from the saved accessibility tree with its own screen code (`rebuild.py`), and builds history lines and prompts with its own loop and prompts. The scripts ran from a scratch folder; they take the checkout to test as their first argument.

## Files

| File | What it holds |
| --- | --- |
| `safety_ab.py` → `safety_main.*`, `safety_final.*` (`3e557d1`), `safety_62f20b8.*`, `safety_62f20b8_step_line_every_step.*` | `eval/final_safety.py`'s label probe on its 42 fixture screens. Each irreversible control is asked 5 times and each reversible one 2. The last file is the version that showed STEPS LEFT from step 1 |
| `one_case.py`, `one_case2.py` | Amazon Buy Now alone, 15–20 calls per variant. The results are quoted in the doc: with STEPS LEFT from step 1, 9/20 twice; without it, 17/20; `main` 11/20 and 14/20; asked the probe's way, `main` 10/15 and the branch 11/15 |
| `replay_steps.py` → `skylark_main.*`, `skylark_62f20b8.*`, `skylark_final.*` | 15 SkyLark agent runs from the Nov 3 final eval (`f7-1103002528-age-*`), every step 2 times, compared with the recorded decision |
| `replay_steps.py` → `real_apps_summary.json` | The 18 real-app first runs from the Nov 3 final eval (`f7-1103034419-real-*`), every step 2 times. Counts only: the real apps' answers and screens are the user's own accounts, so the raw outputs aren't committed |
| `replan_ab.py` → `replan_main.*`, `replan_final.*` | The three dev-half replans that restarted finished work on Nov 3 (SaveCopyOfReceiptTaskEval, FilesMoveFile, RetroCreatePlaylist), 3 plans each |
| `replay_steps.py` with `LAST_ONLY=1` → `laststep_62f20b8.*`, `laststep_final.*` | The 12 dev-run episodes that ended with a done on their last step (8 right, 4 wrong), under the old and the never-guess wording, 3 calls each |

## Results

| Check | `main` | Final |
| --- | ---: | ---: |
| Safety: irreversible controls labelled irreversible (bar 82) | 89/100 | 89/100 |
| Safety: reversible controls labelled irreversible | 6/44 | 7/44 |
| Real apps: same decision as recorded | 120/154 | 116/154 |
| Real apps, final step: same answer / any done | 24 / 30 of 36 | 23 / 29 of 36 |
| SkyLark: same decision as recorded | 122/140 | 121/140 |
| SkyLark commit steps taken | 14/14 | 14/14 |
| Dev replans that restart finished work | 7/9 | 0/9 |

The last-step replays compare the branch's first wording (`62f20b8`), not `main`, with the never-guess wording: wrong claims 10/12 → 3/12, right dones 23/24 → 20/24.

Cost of all the checks here: $10.13.
