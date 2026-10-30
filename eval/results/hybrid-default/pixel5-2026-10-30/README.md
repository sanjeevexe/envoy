# Hybrid vs spark on the Pixel 5 (Oct 30, 01:19–01:23 ET)

Envoy's agent and routine executor ran directly on the loaned Pixel 5 (09031FDD4000C6, Android 13, USB), on
`coord/hybrid-default` (7cf64ec). The app was SkyLark, our own test app: DoorDash isn't installed on the Pixel, and the
coordinator chose SkyLark over an Instagram replay. Everything was read-only with every approval declined. Before each run
the shade was collapsed, SkyLark was force-stopped and the phone went home. The runs were interleaved: first run hybrid,
spark; replay hybrid, spark; then all four again.

- **First run:** the agent, with no routine: "What gate does my Chicago flight leave from?". Every run answered Gate B12.
- **Replay:** the routine `skylark_get_flight_gate` v3 (copied from the benchmark's scratch library; `data/routines`
  untouched), with trip_city = Chicago, launched fresh.

| Run | Profile | Status | Steps | Calls | Cost | Wall | Per step: model | observe | act+settle | total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent | hybrid | done | 5 | 6 | $0.055 | 94 s | 1.7 s | 5.4 s | 0.2 s | 7.3 s |
| agent | hybrid | done | 3 | 4 | $0.025 | 16 s | 1.5 s | 0.8 s | 0.9 s | 3.3 s |
| agent | spark | done | 3 | 4 | $0.007 | 13 s | 1.0 s | 0.8 s | 0.9 s | 2.5 s |
| agent | spark | done | 3 | 4 | $0.006 | 12 s | 1.1 s | 0.8 s | 0.9 s | 2.6 s |
| routine | hybrid | done | 3 | 0 | $0.000 | 22 s | 0.0 s | 0.0 s | 7.2 s | 14.4 s |
| routine | hybrid | done | 3 | 0 | $0.000 | 22 s | 0.0 s | 0.0 s | 6.9 s | 13.8 s |
| routine | spark | done | 3 | 0 | $0.000 | 22 s | 0.0 s | 0.0 s | 7.1 s | 14.2 s |
| routine | spark | done | 3 | 0 | $0.000 | 23 s | 0.0 s | 0.0 s | 6.9 s | 13.8 s |

The per-step columns are medians over that run's steps, from the trace's `timings_ms`: model, observe, act + settle.

**Reading it**

- **First run on an awake phone: hybrid 16 s, spark 12–13 s, so about +3.5 s for a 3-step task.**
  - Wonder's plan call took 4.3–4.5 s, against Spark's 2.1–3.0 s.
  - Wonder's steps took about 1.5 s each, against about 1.0 s on Spark.
  - Screen reads and taps are the same under both.
  - Cost: hybrid $0.025 against $0.006–0.007.
- **The 94 s hybrid run was the phone, not the model.**
  - The Pixel had locked itself before the first run. Startup took about 45 s before the plan call, against about 4 s on the
    other runs.
  - Then two extra steps unlocked the screen; reading the lock screen took 5.4 s each.
  - It made 6 model calls in all, against 4 for the clean runs. Its model latency per step (1.7 s) matches the clean runs.
- **Replays: identical (22 s, no model call under either profile).** A replay only calls Wonder when it needs a repair.
- **Spend:** $0.09 (from the cost log, `pixel-*` task ids).

`runs/` holds each run's record. The step logs aren't kept here, because the lock-screen steps read the phone's lock
screen. The script is `pixel_timing.py`.
