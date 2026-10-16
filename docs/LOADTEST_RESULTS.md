# Load test results

Written by `python -m test.loadtest --find-max`. Newest at the bottom.

## 2026-10-15 07:50
Machine: Darwin 25.5.0 arm64, 8 cores, Python 3.13.5
Target: 20 ticks/s (50 ms budget); sustained = typical p95 tick <= 80% of the budget, <= 1% overruns, no behind resets, no bot dropped.
World 160x160 tiles, seed 5; measured 8 s after a 5 s warm-up. far_stride default, active_chunks default, sleep_ticks default, rates default.

| What | Maximum sustained | First failure | At the maximum: tick p95 / pixels / out | Trials |
|---|---|---|---|---|
| players, each with 3 pixels, spread over the map | 134 | 143 | 38.3 ms / 402 / 264 KB/s | 8 |
| pixels in a dense 12x12-tile cluster that fights, watched by 1 player | 469 | 501 | 36.6 ms / 472 / 6 KB/s | 5 |
| shots added per tick, with 8 players watching | 256 | not reached (limit 256) | 14.2 ms / 24 / 408 KB/s | 4 |

- measured on Darwin 25.5.0 arm64, 8 cores, Python 3.13.5
- Shots: 256 per tick is the cap of the event log, and it was sustained: the log, not the server, limits a burst.
- Players are bots that place 3 pixels, pan their camera and order their pixels about about once a second.
- Re-run on the machine that will host the server; these numbers are not portable.

## 2026-10-15 08:21
Machine: Darwin 25.5.0 arm64, 8 cores, Python 3.13.5
Target: 20 ticks/s (50 ms budget); sustained = typical p95 tick <= 80% of the budget, <= 1% overruns, no behind resets, no bot dropped.
World 160x160 tiles, seed 5; measured 8 s after a 5 s warm-up. far_stride default, active_chunks default, sleep_ticks default, rates default.

| What | Maximum sustained | First failure | At the maximum: tick p95 / pixels / out | Trials |
|---|---|---|---|---|
| players, each with 3 pixels, spread over the map | 125 | 134 | 37.4 ms / 375 / 243 KB/s | 8 |
| pixels in a dense 12x12-tile cluster that fights, watched by 1 player | 532 | 563 | 36.8 ms / 535 / 6 KB/s | 7 |
| shots added per tick, with 8 players watching | 256 | not reached (limit 256) | 12.2 ms / 24 / 423 KB/s | 4 |

- measured on Darwin 25.5.0 arm64, 8 cores, Python 3.13.5
- Shots: 256 per tick is the cap of the event log, and it was sustained: the log, not the server, limits a burst.
- Players are bots that place 3 pixels, pan their camera and order their pixels about about once a second.
- Re-run on the machine that will host the server; these numbers are not portable.

