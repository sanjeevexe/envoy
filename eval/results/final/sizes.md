# sizes

Run 1028023040 on `5504260` with uncommitted changes, 2026-10-28 06:30 UTC, 6 min, standard tier. 0 model calls, $0.000 at standard prices ($0.000 billed).

| Device | Screen | dp | Runs | Passed | No model call | Agent fallbacks | Median s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| envoy-test | 1080×2400 at 420 dpi | 411×914 | 30 | **30** | 30 | 0 | 2.8 |
| envoy-small | 720×1280 at 320 dpi | 360×640 | 30 | **30** | 30 | 0 | 4.1 |
| envoy-large | 1440×3120 at 480 dpi | 480×1040 | 30 | **29** | 29 | 0 | 4.7 |

Not clean (failed, or needed a model call):

- envoy-large · add_ktn: failed rung 2, 0 calls · done-check failed: '71253619' not visible
