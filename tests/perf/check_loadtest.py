"""README 9.8: the load test tool itself (loadtest.py) does what it says.

Part 1 (no network): the verdict rules, the search for the largest sustained count, the report and the results file text.
Part 2 (real): a tiny trial of everything at once: a real server process, a few real websocket bots, a small crowd and a shot burst, a few seconds
long. It checks the tool works (bots join and are not dropped, the server's metrics come back, the shots reach the bots, the file records what was
found); it does NOT check that the server is fast enough: that is what `python -m test.loadtest` is for.
Run from the folder that contains game/ and server/:  python -m test.check_loadtest
"""
import os
import tempfile

from tools import loadtest as lt

checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def window(p95=10.0, ticks=20, overruns=0, behind=0, players=3, backlog=0, seconds=1.0):
    return {"tick": 1, "seconds": seconds, "players": players, "pixels": 50, "pixels_total": 80, "pixels_asleep": 10, "projectiles": 0, "ticks": ticks,
            "tick_ms": {"avg": p95 / 2, "p95": p95, "max": p95 * 1.5, "budget": 50.0}, "overruns": overruns, "behind_resets": behind,
            "phase_ms": {"inbox": 0.1, "step": p95 / 2, "grid": 0.2, "notices": 0.0, "replicate": 1.0}, "counters_per_s": {}, "bytes_per_s": 2048.0, "by_type_per_s": {},
            "clients": [{"id": 1, "name": "a", "bytes_per_s": 1.0, "messages_per_s": 1.0, "backlog": backlog, "biggest": 10}], "totals": {}}


def bot_stats(joined=True, dropped=None, events=5):
    return {"name": "b", "joined": joined, "join_ms": 12.0, "command_ms": [3.0, 5.0, 9.0], "bytes": 1000, "messages": 10, "events": events, "dropped": dropped, "error": None}


def main():
    # ---- part 1
    config = lt.Config(bots=2, warmup=1.0, measure=3.0, join_spread=0.0)
    ok(config.total_warmup() == 1.0 + 1.0, "the warm-up includes the time the bots take to join")
    snaps = [window(p95=10.0) for _ in range(8)]
    result = lt.summarize(config, snaps, [bot_stats(), bot_stats()])
    ok(result["verdict"] == "SUSTAINED" and not result["reasons"], f"a calm run is sustained: {result['reasons']}")
    ok(result["windows"] == 6 and result["ticks"] == 120, "the warm-up windows are left out of the measurement")
    ok(result["bots_joined"] == 2 and result["command_p50_ms"] == 5.0 and result["bot_events"] == 10, "the bots' numbers are added up")
    ok(lt.summarize(config, [window(p95=45.0) for _ in range(8)], [bot_stats()])["verdict"] == "FAILED", "a p95 near the budget fails (it must leave room for a slow tick)")
    ok(lt.summarize(config, [window(p95=39.0) for _ in range(8)], [bot_stats()])["verdict"] == "SUSTAINED", "a p95 just under the limit passes")
    spiky = [window(p95=10.0) for _ in range(7)] + [window(p95=90.0)]
    res = lt.summarize(config, spiky, [bot_stats()])
    ok(res["verdict"] == "SUSTAINED" and res["tick_p95_worst_ms"] == 90.0, "one bad window does not fail a run (typical p95 is the median) but the worst is reported")
    ok(lt.summarize(config, [window(overruns=2) for _ in range(8)], [bot_stats()])["verdict"] == "FAILED", "more than 1% of the ticks over the budget fails")
    ok(lt.summarize(config, [window(behind=1)] + [window() for _ in range(7)], [bot_stats()])["verdict"] == "SUSTAINED", "a behind reset during the warm-up does not count")
    ok(lt.summarize(config, [window() for _ in range(3)] + [window(behind=1)] + [window() for _ in range(4)], [bot_stats()])["verdict"] == "FAILED", "but one while measuring does")
    ok(lt.summarize(config, snaps, [bot_stats(), bot_stats(dropped="closed 1013 too slow")])["verdict"] == "FAILED", "a bot dropped by the server fails the run")
    res = lt.summarize(config, snaps, [bot_stats(), bot_stats(joined=False)])
    ok(res["verdict"] == "FAILED" and any("joined" in reason for reason in res["reasons"]), "a bot that never joined fails the run")
    ok(lt.summarize(config, [], [])["verdict"] == "FAILED", "no measured ticks is not a pass")
    ok(lt.summarize(lt.Config(), snaps, [])["verdict"] == "SUSTAINED", "a run with no bots at all can be judged too")
    ok(lt.summarize(lt.Config(max_p95_fraction=0.1), snaps[:], [])["verdict"] == "FAILED", "the p95 limit can be changed")

    # the search
    for truth in (0, 1, 7, 100, 333, 1000):
        calls = []
        best, failed, runs = lt.search(lambda n: (calls.append(n), n <= truth)[1], start=8, limit=5000)
        ok(best <= truth and (failed is None or failed > truth), f"search finds a sustained count that is really sustained (truth {truth}: best {best}, failed {failed})")
        ok(truth - best <= max(1, 0.1 * truth) + 1 or truth < 8 and best <= truth, f"within about 10% of the real limit (truth {truth}, best {best})")
        ok(runs == len(calls) and runs < 25, f"in a modest number of trials ({runs})")

    best, failed, runs = lt.search(lambda n: True, start=32, limit=256)
    ok(best == 256 and failed is None, "when the limit itself is sustained it says so (failed is None)")
    ok(lt.search(lambda n: False, start=8, limit=100)[0] == 0, "when even the smallest count fails the maximum is 0")

    # the text
    lines = lt.report_lines(config, result)
    ok(lines[0].startswith("  SUSTAINED") and any("bots:" in line for line in lines) and any("tick ms" in line for line in lines), "the report has a verdict, the tick times and the bots")
    failed_lines = lt.report_lines(config, lt.summarize(config, [window(p95=45.0) for _ in range(8)], [bot_stats()]))
    ok(any(line.strip().startswith("!") for line in failed_lines), "a failed run lists why")
    ok("crowd of 100" in lt.describe(lt.Config(crowd=100)) and "shots" in lt.describe(lt.Config(burst=5)), "describe names the crowd and the shots")
    section = lt.markdown_section(config, [{"what": "players", "best": 120, "failed": 130, "limit": 400, "runs": 7, "best_result": result}, {"what": "shots", "best": 256, "failed": None, "limit": 256, "runs": 2, "best_result": None}], ["a note"], stamp="2026-01-01 00:00")
    ok("## 2026-01-01 00:00" in section and "| players | 120 | 130 |" in section and "not reached (limit 256)" in section and "- a note" in section and "Machine:" in section, "the results file section has the machine, the table and the notes")

    print(f"part 1: {checks} checks passed")

    # ---- part 2: a tiny real trial
    tiny = lt.Config(bots=3, pixels_per_bot=2, crowd=40, crowd_tiles=6, together=False, burst=20, size=96, warmup=1.0, measure=3.0, join_spread=0.05)
    trial = lt.run_trial(tiny)
    print("\n".join(lt.report_lines(tiny, trial)))
    ok(trial["bots_joined"] == 3 and trial["bots_dropped"] == 0 and not trial["bot_errors"], f"3 real bots joined and were not dropped: {trial['bot_errors']} {trial['drop_reasons']}")
    ok(trial["ticks"] > 0 and trial["windows"] >= 2, "the server's metric windows came back from the other process")
    ok(trial["players"] == 3 and trial["pixels_total"] >= 3 * 2, f"the bots' pixels exist in the world: {trial['pixels_total']} pixels")
    ok(trial["crowd_placed"] > 0, f"the crowd was placed: {trial['crowd_placed']}")
    ok(trial["command_p50_ms"] > 0 and trial["join_p95_ms"] > 0, "the bots measured their command round trips and join time")
    ok(trial["burst_injected"] >= 20 * 10 and trial["burst_kept"] >= trial["burst_injected"] * 0.9, f"the shot burst was added and kept ({trial['burst_injected']} / {trial['burst_kept']})")
    ok(trial["bot_events"] > 0, f"the shots reached the bots over the wire ({trial['bot_events']})")
    ok(trial["bytes_per_s"] > 0 and trial["bot_bytes"] > 0, "the server sent bytes and the bots received them")
    ok(trial["verdict"] in ("SUSTAINED", "FAILED") and trial["tick_rate"] > 10, f"it has a verdict and the server kept ticking ({trial['tick_rate']:.1f} ticks/s)")

    # a burst over the event log's cap is cut at the cap (the tool reports it, the server stays alive)
    over = lt.Config(bots=1, burst=lt.BURST_CAP * 2, size=96, warmup=1.0, measure=2.0, join_spread=0.0)
    res = lt.run_trial(over)
    ok(res["burst_kept"] <= res["burst_injected"] / 2 + lt.BURST_CAP and res["ticks"] > 0, f"a burst bigger than the cap is cut by the event log: {res['burst_injected']} added, {res['burst_kept']} kept")

    # the search wired to a real trial writes the file
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "results.md")

        class Args:
            pixels_per_bot, crowd_tiles, bots, crowd, burst, size, seed, warmup, measure = 1, 6, 2, 0, 0, 96, 5, 0.5, 1.5
            far_stride = active_chunks = sleep_ticks = None
            rate, max_p95_fraction, results = [], 10.0, path   # a limit no run can fail, so the search stops at the limit at once
            max_bots, max_pixels = 2, 20

        found = lt.find_max(Args, ["players"])
        ok(os.path.exists(path) and "players" in open(path, encoding="utf-8").read(), "find_max appended its findings to the results file")
        ok(found[0]["best"] == 2 and found[0]["failed"] is None, "and, with a limit nothing fails, reports the limit as sustained")

    print(f"all {checks} checks passed")


if __name__ == "__main__":   # the server process is started by 'spawn', which imports this file again: it must not run the checks a second time
    main()