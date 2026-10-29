# Routines on three screen sizes and the real phone

Run 1029194756 on ``, 2026-10-29 19:47 UTC, 5 min, standard tier. 0 model calls, $0.000 at standard prices ($0.000 billed).

| Device | Screen | dp | Runs | Passed | No model call | Agent fallbacks | Median s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| envoy-test | 1080×2400 at 420 dpi | 411×914 | 30 | **30** | 30 | 0 | 5.4 |
| envoy-small | 720×1280 at 320 dpi | 360×640 | 30 | **30** | 30 | 0 | 4.1 |
| envoy-large | 1440×3120 at 480 dpi | 480×1040 | 30 | **29** | 29 | 0 | 4.7 |
| phone (real phone: Pixel 5, Android 13) | 1080×2340 at 440 dpi | 393×851 | 30 | **30** | 30 | 0 | 6.6 |

Not clean (failed, or needed a model call):

- envoy-large · add_ktn: failed rung 2, 0 calls · done-check failed: '71253619' not visible
