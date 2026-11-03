# The showcase site in five sections (WS-F, Nov 2)

Branch `claude/site-five-sections`, rebased onto main `557f150`. Only `site/**`, `scripts/build_site_data.py` and this report
(with its screenshots in `prompts/site-five-sections-report/`) changed. Not pushed, not merged. No devices, no model calls,
$0.

## The structure

Sixteen sections and about 9,700 words became five sections, about 3,600 words, plus an evidence appendix whose groups stay
closed until clicked. The story follows the video plan (V1): the idea and one live run, learns, acts, watches, results.

| # | Section | What's in it |
| --- | --- | --- |
| 1 | **The idea** | The tagline. One plain line: Envoy gives an AI agent its own Android phone, approvals on your iPhone, a learned task becomes a tool. What Muse is. The diagram (Asks → Envoy on a Mac → Envoy's phone; your iPhone approves). "One post, start to finish": the Reel's two iPhone yeses, with the four posts and which went live. Three numbers: Learns 6 → 0 model calls (medians, real apps), 4 app-only posts live, 1.57 s (one comment) |
| 2 | **Learns** | The Starbucks first-run stepper (`?step=` works). Then: first run vs routine on real apps as medians with ranges, a new input and its pass-by-pass trajectory, repairs (real apps first: 7 proposed, 3 kept, among them the Reel's and Short's checks after their live posts; SkyLark 50/50 as the stress test), a routine shared as a tool (the Spark agent's tool list and its first call by name), and Meta's models by job with "SAM then grounding 52 of 52; grounding alone 49" |
| 3 | **Acts** | The four posting routines, 2×2: how each was made (Instagram's two "learned from one agent run, no hand edits"; TikTok and YouTube "compiled from one agent run" with their hand edits stated exactly), rehearsals with Envoy's calls "in Envoy's replay", the live post, the automatic repair. The flaws callout. The Spark agent's one-request dry run (timeline behind a click). Muse's dry run, five rows in plain words with the two Story failures. "Only a person approves": no approve tool, per-agent keys, 20/20 and 0 of 20 |
| 4 | **Watches** | The live comment table, "and it's waiting for your agent" (Muse about every 10 min), six trigger kinds, Muse's scheduled task |
| 5 | **Results** | Real apps first: one pass per row (Oct 28, Oct 29 ×2, Oct 31 rehearsal, then the final), first run vs routine (calls, time, cost; medians with ranges), the posting routines' 13 of 13 rehearsals. SkyLark second, as its own table. AndroidWorld framed by cost (55/69 at 1 call and $0.002 vs the agent's 63/69 at 6 and $0.012; 67/69 with fallback; held-out 31/58 vs 12). Limits, each weak number with its trajectory |
| – | **Evidence** | Every run cited (when, where, commit, profile, task ids); the Starbucks routine with every model call; all 50 SkyLark repairs; real apps workflow by workflow; the design's targets and four charts; the share switch (agent-door's before/after); SAM; safety; keys; Claude Code; teach mode; memory; how it's built |

Kept: the `?only=<id>` and `?step=N` parameters, light by default with the dark toggle, `file://`, the static page with no
third-party calls, and the deterministic build.

New: `?open=1` opens every evidence group, and `#ev-<group>` opens one.

## Rules from the handoff, as applied

- **Numbers true at face value.** Every number states its scope and its pass:
  - The real-app medians come from `eval/results/final/real.json`. They're labeled as "one pass of the evaluation's real-app suite (Oct 28, all-Spark profile)" until the eval makes them the final pass.
  - Starbucks's 45.6 s → 14.8 s is gone from the headline. The page says plainly that its replays used fewer calls but took longer (median 4 vs 12 calls, 67 s vs 44 s).
  - The one replay shown in the evidence is labeled "the quickest of the loop, not the typical one".
- **No mixing of passes in a row.** The real-app table has one pass per row.
- **"Learned from one run"** is used only for Instagram's Reel and Story. The Reel also says its checks were repaired automatically after its live post. TikTok and YouTube are "compiled from one agent run", with their hand edits.
  - The build checks its hand-edit wording (`HAND_EDITS`) against each version's own changes, so a new version stops the build instead of leaving the page wrong.
- **"0 model calls" appears only as "in Envoy's replay".** The calling agent's cost is stated: 11 calls, $0.043.
- **"Compiler checks aren't outcome checks"** is said in the flaws callout.
- **Watches.** "1.57 s" is labeled as one comment, to the iPhone. Agents hear it at their next check.
- **The dry runs are labeled.** "4 posts, 1 request" is no longer a headline. The live posts and the dry runs are separate, and Limits says the live posts were started from the Spark agent, while Muse's run was a dry run whose Story failed twice.
- **Internal wording removed.** "loop A", "rung", backlog numbers, "the coordinator", "the other chat's branch", commit hashes and task ids are gone from the five sections.
  - Text the page quotes from the repo's own records goes through a small cleaner. This covers the routine version notes and the suite names.
  - The commits, task ids and configuration are in the evidence.
  - A scan of the rendered page with every group open finds none of those terms. The only "the user" left is inside Claude Code's quoted reply.
- **Banned wording.** None of the banned phrases appear: "deterministic", "cryptographic", "hardware-enforced", "instantly", "virtual", or "your phone" for the Pixel. The only "your phone" left is the Spark agent's own words about the iPhone, in its collapsed call log.

## Checked

- **Browser.** Served from Bash on 127.0.0.1:8781. Checked at 1440 px with headless Chrome, section by section, and at 375 px in the browser pane.
  - No horizontal overflow at 375 px. Only teach mode's film strip scrolls sideways, inside its own frame.
  - Light and dark both checked.
  - No console errors.
- **Links and files.**
  - All 63 linked repo paths are tracked files.
  - All 33 images on the page exist, and nothing in `site/data/img/` is unused.
  - The build is byte-identical twice.
- **The post-eval path, simulated.** I edited `report.md` to 10 of 10 suites on `eval-final` and set `real.json` to `is_eval_final`, then rebuilt.
  - The banner read "Final numbers", all 10 pending markers cleared, and the real-app table gained a "Final evaluation" row.
  - The real-app numbers switched to "From the final evaluation".
  - Restored afterwards; `site/data/` came back byte-identical.
- **Privacy.** No new images were added.
  - Removed: the eight real-app grid frames and their `app-frames.json`, and the hand-driven Story-poll frame.
  - Every image left was checked at full size in the earlier rework.
  - The screenshots in this report's folder are of the site itself.

## The fact check's site rows, applied (Nov 2, evening)

The baseline (`docs/claims.md` on `claude/keen-wu-000a7e`) checked the old site at 726965e. Rows my rework had already
removed (the real-app cards, the voice line, "the expensive one works once per task", the Starbucks bars) are gone. For
the rest, on this branch, rebased onto main 46a3dd4:
- **W6, W73, W44, W47 (Starbucks):** no best replay as typical, no "every replay is 2 Spark calls", no "on a replay:
  none". The first run says it took two hand fixes and one kept self-repair before its replays ran cleanly; the one replay
  in the evidence is "among the quickest, not the typical one", with the loop's median.
- **W5:** no "4 posts, 1 request"; the dry runs and the live posts are separate cards.
- **W10, W65, W80, W82:** the Pixel tile, the memory tiles and the design targets carry "our test app".
- **Profiles:** every timing and cost names its profile and tier: the Spark profile for `report.md`'s suites (read from
  each suite's JSON) and AndroidWorld; hybrid for the Starbucks runs (read from the run's own model calls), the posting
  rehearsals (each run file records it) and the Oct 31 rehearsal. "all-Spark" is gone: that profile compiles with Wonder.
- **W30, W31, W52:** rebuilt on 46a3dd4: the Reel and Short at v3, self-repair 7 proposed / 3 kept.
- **W83:** the builder's median now averages an even list's two middle values: the Pixel's 30 runs give 6.6 s, not 7.1.
- **"0 model calls":** "in Envoy's replay" (or "Envoy's own calls") wherever a calling agent could be read as free.
- **W84, W87:** AndroidWorld says the 13 changes are now in main; `numbers.json` gives its full headline and "merged into
  main Oct 29 (105d04e)".
- **W9, W12, W15, W61, W62, W69, W76, W79:** "every section links to the files its numbers came from"; each new-input
  number with its pass and profile; banking apps "expected to (not tested)"; teach mode's "one scripted demonstration and
  one replay"; "both events were deleted" dropped (no record); "on 42 captured screens from 8 apps"; SAM's 52 targets
  scoped (16 drawn seats in our test app); the safety suites use captured real-app screens.

## The fact check's second pass, applied (Nov 2, late evening)

On `3790eae` the second pass (`docs/claims.md`, WB rows) verified the baseline fixes and found these, now fixed on this
branch, rebased onto main 557f150:
- **WB41 (false):** the Oct 28 row's first run read 13/18 from the rehearsal README, which copied real.json's count. Each
  pass's row now comes from its own published stage table (real.md): 14/18. The Nov 2 hybrid pass on 192cd29 (new input
  8/11) is now a row; the Nov 2 check pass isn't, since its totals mix runs.
- **WB67 (false):** the share-switch evidence now picks the run's call to a learned routine:
  `skylark_check_flight_status(flight_number: "SL 1190")`, not `memory_search`.
- **WB73 (false), WB74:** the README says task ids and commits stay out of the prose (profiles are in it), and gives the
  rebuild check (`git diff --exit-code site/data`).
- **WB22, WB6:** "among 42 controls on 30 captured screens from 8 apps (15 of the screens from SkyLark)"; the planted-text
  runs are labeled SkyLark. Both counts are read from safety.json.
- **WB11, WB12, WB53:** the posting cards say "Rehearsals of v2" where v3 is an automatic repair, and how many the agent
  finished (read from each run file's model jobs). The results line gives 13 of 13 since each last compile and 41 of 49
  across all versions.
- **WB13:** after the last hand fix, 9 of the next 10 Starbucks replays ran clean, one fell back to the agent (from
  runs.jsonl, times compared in one zone).
- **Approval wording (WB35, WB36):** "anything an agent asks for that can't be undone waits for your yes"; a request from
  an agent, a trigger or an email waits unless that routine is set to run without asking; money always asks; a request the
  person types counts as their OK.
- **"Learns":** the lede, the section 2 heading and the meta description now say a verified run can be compiled into a
  checked routine; section 2 and the limits say agent runs are compiled by a script or the evaluation today, and teach
  mode compiles in the running Envoy.
- **After the eval:** `eval/results/final/real.md` becomes the final pass, so the Oct 28 row leaves the table (its numbers
  live only in that file's history) and the "Final evaluation" row takes its place. Simulated and restored.
- **Scope rows:** WB38 (Muse: three declined, the Story failed), WB40 (the Oct 28 pass is 4 runs; the runs table lists
  them), WB42, WB47, WB49 ("against a probe MCP server"), WB51 (TikTok's three hand edits), WB62 (the 22 of 59 routines),
  WB64 (three test comments), WB66, WB70, WB72.

## Still open

1. **The live posts' raw rows: done.** The coordinator's five task rows are now
   `eval/results/showcase/live-2026-11-02/task-rows.json`. Sections 1 and 3 and the evidence read them: what each post
   carried, Envoy's model calls, and the songless TikTok in plain words. The build no longer reads
   `prompts/showcase-report.md`. The Muse rows were replaced with the coordinator's cleaned copy (only its source line and
   notes changed; the site uses its own wording for the two Story notes).
2. **Section 1's capture:** planned. The coordinator will send a still or frames from tonight's take once the user is happy
   to publish it. Until then, section 1 shows the live rows plus the dry-run timeline, labeled.
3. **The C5 cold start** is now an Uber fare quote on the Pixel, filmed Tue 14:00–16:15. Its evidence comes Tue afternoon
   at the earliest, with card digits removed. Section 2 keeps the Oct 30 Starbucks run until then.
4. **The watch timings** still cite `prompts/phone-watch-report.md`. There's no raw file in `eval/results/` for them.
5. **Rebuild** after WS-E merges and again after the eval's report (Nov 3, about 22:00). Both are a plain build plus a commit of `site/data/`.

## For WS-E (docs)

The build now parses these lines in `docs/`. A reworded line stops the build:
- `docs/androidworld-results.md`: "**Headline.**", "**Held-out half:**", and the "**Routines.**" bullets ("they did N of N instances, against the full agent's N, at N model call against N, $X against $Y" and "with the agent run where a routine failed, N of N");
- `docs/phase-6-results.md`: "SAM then grounding N of N; grounding alone N of N";
- `docs/diagrams/*.png`.

It no longer reads `docs/phase-5-results.md`.

The page links to `docs/cloud.md`, `muse-link.md`, `demo-showcase.md`, `phase-6-results.md`, `androidworld-results.md` and
`agents.md`. A rename needs a matching change in `site/`.
