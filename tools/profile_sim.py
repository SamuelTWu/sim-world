"""README 9.7: find out WHERE a slow tick goes, before touching anything. Run from the folder that contains game/ and server/:

    python -m test.profile_sim                          # 2000 pixels, 200 ticks: timing, then a cProfile table
    python -m test.profile_sim --pixels 5000 --owners 3 --ticks 300
    python -m test.profile_sim --pixels 1500 --cluster 12     # a dense crowd: 1500 pixels in a 12x12-tile square, a player at it (what loadtest.py's cluster scenario runs)
    python -m test.profile_sim --scale 500,2000,8000    # how the tick grows with the number of pixels, and where it passes the budget
    python -m test.profile_sim --out sim.prof           # keep the raw profile (python -m pstats sim.prof, or snakeviz sim.prof)
    python -m test.profile_sim --far-stride 1 --sleep-ticks 0     # the same with 9.2 / 9.3 off, to see what they buy
    python -m test.profile_sim --rate needs=2,10 --rate think=1,4 # and with 9.4 rates

It measures Simulation.step() only (the server's other phases, replication and sending, are in the 9.1 log line: use that to see which part of
the tick is too slow, and this tool when it is the simulation). Nothing here changes the simulation: it builds a world like the checks do
(seeded, unowned pixels spread over it, a few player pixels) and runs it.

How to read the answer (the table at the end of a profile run):
  - Look at the ms per tick against the budget first. If the tick fits (comfortably under 50 ms with the pixel count you actually expect), STOP: do not
    add Numba or Cython to something that is not slow.
  - `own` is the time spent in a function's own lines, `total` includes what it calls. A function with high `own` and few calls into other code is a
    hot LOOP: that is what numpy / Numba / Cython can speed up.
  - A function with high `total` but low `own` is only expensive because of what it calls: look further down, or reduce how often it is called
    (fewer pixels, a lower rate in 9.4, sleep, a spatial grid) before compiling anything.
  - Lots of calls to tiny functions (properties, dict lookups, dataclass access) is Python object overhead: the fix is fewer calls or the
    structure-of-arrays storage of 9.5, not a compiler on one function.
"""
import argparse
import cProfile
import io
import os
import pstats
import random
import statistics
import sys
import time

from src.simworld.sim.core.sim_context import TILE_UNITS
from src.simworld.sim.simulation import TICK_DT, Simulation
from src.simworld.world.generator import GenerationSettings

BUDGET_MS = TICK_DT * 1000.0
WARMUP_TICKS = 20


def blueprint(sim, *names):
    factory = sim.entity_manager.entity_factory

    for name in names:
        try:
            return factory.load_definition(name)
        except (OSError, ValueError):
            continue

    raise RuntimeError(f"none of these blueprints exist: {names}")


def land_near(world, tile_x, tile_y, radius=40):
    """The nearest tile around (tile_x, tile_y) that a pixel can walk on, or None."""
    for ring in range(radius):
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                if max(abs(dx), abs(dy)) == ring:
                    tile = world.get_tile(tile_x + dx, tile_y + dy)

                    if tile is not None and tile.can_walk_through():
                        return tile_x + dx, tile_y + dy

    return None


def build(pixels, size, owners, seed, args):
    """A seeded world with `pixels` unowned pixels spread over it plus `owners` player pixels (each anchors its own active area)."""
    sim = Simulation(GenerationSettings(width=size, height=size, seed=seed))
    sim.start_new_game(seed)
    sim.systems.activity.configure(args.active_chunks, args.far_stride, args.sleep_ticks)

    for spec in args.rate:
        key, strides = spec.split("=", 1)
        parts = [int(part) for part in strides.split(",")]
        sim.systems.activity.set_rate(key, near=parts[0], far=parts[1] if len(parts) == 2 else None)

    kinds = [blueprint(sim, "runner", "pixel_runner"), blueprint(sim, "swimmer", "pixel_swimmer"), blueprint(sim, "commander", "pixel_commander")]
    scatter = random.Random(seed + 1)

    middle = None

    if args.cluster:
        middle = land_near(sim.world, size // 2, size // 2, size // 2) or (size // 2, size // 2)   # the dense cluster of --cluster tiles wide sits here

    for index in range(pixels):
        if middle is None:
            sim.spawn_pixel(kinds[index % len(kinds)], None, scatter.randint(2, size - 2) * TILE_UNITS, scatter.randint(2, size - 2) * TILE_UNITS)
            continue

        for _ in range(12):
            tile = (middle[0] + scatter.randint(-args.cluster // 2, args.cluster // 2), middle[1] + scatter.randint(-args.cluster // 2, args.cluster // 2))
            ground = sim.world.get_tile(*tile)

            if ground is not None and ground.can_walk_through():
                sim.spawn_pixel(kinds[index % 2 * 2], None, tile[0] * TILE_UNITS + scatter.uniform(4, 28), tile[1] * TILE_UNITS + scatter.uniform(4, 28))   # runners and commanders (walkers), like loadtest.py's cluster
                break

    for index in range(owners):
        if middle is None:
            sim.spawn_pixel(kinds[0], 1 + index, scatter.randint(2, size - 2) * TILE_UNITS + 16, scatter.randint(2, size - 2) * TILE_UNITS + 16)
        else:
            sim.spawn_pixel(kinds[0], 1 + index, (middle[0] + index) * TILE_UNITS + 16, middle[1] * TILE_UNITS + 16)   # a player at the cluster, so it is all near

    return sim


def time_ticks(sim, ticks):
    """Wall time of each Simulation.step(), in milliseconds."""
    samples = []

    for _ in range(ticks):
        started = time.perf_counter()
        sim.step()
        samples.append((time.perf_counter() - started) * 1000.0)

    return samples


def summarize(samples):
    ordered = sorted(samples)
    return {
        "mean": statistics.fmean(samples),
        "p50": ordered[len(ordered) // 2],
        "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max": ordered[-1],
        "over": sum(1 for sample in samples if sample > BUDGET_MS),
    }


def timing_line(stats, ticks):
    return (f"mean {stats['mean']:.2f} ms  p50 {stats['p50']:.2f}  p95 {stats['p95']:.2f}  max {stats['max']:.2f}  "
            f"over the {BUDGET_MS:.0f} ms budget: {stats['over']} of {ticks} ticks")


def verdict(stats):
    if stats["p95"] <= BUDGET_MS * 0.5:
        return "FINE: p95 is under half the budget. Nothing needs speeding up at this size."

    if stats["p95"] <= BUDGET_MS * 0.8:
        return "OK but not roomy: p95 is under the budget, with less than half of it spare. Watch it as pixels grow."

    if stats["p95"] <= BUDGET_MS:
        return "TIGHT: p95 is within 20% of the budget. A slow tick (a burst of thinking, a big fight) will overrun."

    return "TOO SLOW: p95 is over the budget. Use the profile below."


def short_name(filename):
    marker = os.sep + "game" + os.sep
    index = filename.rfind(marker)

    if index >= 0:
        return filename[index + 1:]

    return os.path.basename(filename) if filename.startswith("<") else filename.replace(sys.prefix, "").lstrip(os.sep)


def profile_ticks(sim, ticks):
    profiler = cProfile.Profile()
    profiler.enable()

    for _ in range(ticks):
        sim.step()

    profiler.disable()
    return profiler


def table(profiler, ticks, top):
    """Rows of (own ms/tick, total ms/tick, calls/tick, own/total, name) for the functions that cost the most of their own time."""
    stats = pstats.Stats(profiler)
    rows = []

    for (filename, line, name), (calls, _primitive, own, total, _callers) in stats.stats.items():
        rows.append((own * 1000.0 / ticks, total * 1000.0 / ticks, calls / ticks, own / total if total else 1.0, f"{short_name(filename)}:{line}({name})", filename))

    rows.sort(key=lambda row: -row[0])
    return rows[:top], stats


def by_file(stats, ticks, top):
    """Own time per source file, so it is clear which module the tick goes to."""
    totals = {}

    for (filename, _line, _name), (_calls, _primitive, own, _total, _callers) in stats.stats.items():
        key = short_name(filename)
        totals[key] = totals.get(key, 0.0) + own * 1000.0 / ticks

    return sorted(totals.items(), key=lambda item: -item[1])[:top]


def classify(row, all_own):
    """A hint for one row: is it the kind of function a compiler helps? (A guide for reading, not a measurement.)"""
    own, total, calls, ratio, name, filename = row

    if filename.startswith(("<", "~")) or "site-packages" in filename or "lib/python" in filename.replace(os.sep, "/"):
        return "library / builtin: reduce how often it is called"

    share = own / all_own if all_own else 0.0

    if share < 0.04:
        return ""

    if ratio >= 0.7 and calls <= 50:
        return "hot LOOP in this function: a numpy / Numba / Cython candidate"

    if ratio >= 0.7:
        return "called a lot, cheap each time: call overhead; call it less (rates, sleep, grid) before compiling"

    return "mostly time in what it calls: look at its callees first"


def print_profile(profiler, ticks, top):
    rows, stats = table(profiler, ticks, top)
    all_own = sum(own * 1000.0 / ticks for (_f, _l, _n), (_c, _p, own, _t, _cs) in stats.stats.items())
    print(f"\nProfile of {ticks} ticks (profiling itself slows things down about 2x, so read the shares, not the milliseconds):")
    print(f"  {'own ms/tick':>11} {'total ms/tick':>13} {'calls/tick':>10}  {'own/total':>9}  function")

    for row in rows:
        own, total, calls, ratio, name, _filename = row
        hint = classify(row, all_own)
        print(f"  {own:11.3f} {total:13.3f} {calls:10.1f}  {ratio:9.2f}  {name}" + (f"\n{'':50}-> {hint}" if hint else ""))

    print(f"\nOwn time by file (of {all_own:.2f} ms/tick in total):")

    for name, own in by_file(stats, ticks, 8):
        print(f"  {own:8.3f} ms/tick  {100.0 * own / all_own if all_own else 0.0:5.1f}%  {name}")

    candidates = [row for row in rows if "hot LOOP" in classify(row, all_own)]

    if not candidates:
        print("\nNo single hot loop stands out. Compiling one function would not fix this: reduce the work (9.2 to 9.4 settings, fewer pixels in the\nactive area, a cheaper rule for simple pixels) or change how pixels are stored (9.5) before reaching for Numba or Cython.")
    else:
        print("\nHot loops worth a look for numpy / Numba / Cython (in this order):")

        for row in candidates[:3]:
            print(f"  {row[4]}  ({row[0]:.3f} ms/tick of its own)")

        print("Compile only what this table shows, keep the Python version as the reference, and make the check_* results stay identical\n(Numba and Cython must give the same positions: floating point order matters for determinism).")


def scale_run(counts, args):
    """ms per tick for several pixel counts, and where a straight line through them crosses the budget."""
    results = []

    for count in counts:
        sim = build(count, args.size, args.owners, args.seed, args)
        time_ticks(sim, WARMUP_TICKS)
        stats = summarize(time_ticks(sim, args.ticks))
        results.append((count, stats))
        print(f"  {count:7d} pixels: {timing_line(stats, args.ticks)}")

    if len(results) >= 2:
        (n1, s1), (n2, s2) = results[0], results[-1]

        if n2 > n1 and s2["p95"] > s1["p95"]:
            slope = (s2["p95"] - s1["p95"]) / (n2 - n1)
            limit = n1 + (BUDGET_MS - s1["p95"]) / slope
            per_pixel = slope * 1000.0
            print(f"\n  about {per_pixel:.1f} microseconds of p95 per extra pixel; a straight line puts p95 at the {BUDGET_MS:.0f} ms budget near {int(limit)} pixels")
            print("  (a rough guide: pixels near players cost more than far or sleeping ones, so it depends on how many are near a player)")
        else:
            print("\n  the tick did not grow with the number of pixels in this range")


def main():
    parser = argparse.ArgumentParser(description="Time and profile Simulation.step() (README 9.7)")
    parser.add_argument("--pixels", type=int, default=2000, help="unowned pixels spread over the world")
    parser.add_argument("--cluster", type=int, default=0, metavar="TILES", help="pack the pixels into a square this many tiles wide (e.g. 12) instead of spreading them over the world: a dense crowd, as in `loadtest.py --scenario cluster`")
    parser.add_argument("--owners", type=int, default=2, help="player pixels (each makes its area active)")
    parser.add_argument("--size", type=int, default=200, help="world width and height in tiles")
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--top", type=int, default=15, help="rows in the profile table")
    parser.add_argument("--scale", default=None, help="comma separated pixel counts: time each instead of profiling, e.g. 500,2000,8000")
    parser.add_argument("--out", default=None, help="write the raw cProfile data here")
    parser.add_argument("--active-chunks", type=int, default=None)
    parser.add_argument("--far-stride", type=int, default=None)
    parser.add_argument("--sleep-ticks", type=int, default=None)
    parser.add_argument("--rate", action="append", default=[], metavar="KEY=NEAR[,FAR]")
    args = parser.parse_args()

    if args.scale:
        print(f"Tick time against pixel count ({args.ticks} ticks each, {args.size}x{args.size} tiles, budget {BUDGET_MS:.0f} ms):")
        scale_run([int(part) for part in args.scale.split(",")], args)
        return

    print(f"Building a {args.size}x{args.size} world with {args.pixels} pixels and {args.owners} player pixels (seed {args.seed})...")
    sim = build(args.pixels, args.size, args.owners, args.seed, args)
    time_ticks(sim, WARMUP_TICKS)
    stats = summarize(time_ticks(sim, args.ticks))
    activity = sim.systems.activity
    print(f"\nTiming of {args.ticks} ticks ({activity.last_active} active, {activity.last_far} far, {activity.last_asleep} asleep of {len(sim.entity_manager.all())} pixels):")
    print(f"  {timing_line(stats, args.ticks)}")
    print(f"  {verdict(stats)}")
    profiler = profile_ticks(sim, args.ticks)

    if args.out:
        profiler.dump_stats(args.out)
        print(f"\nraw profile written to {args.out}")

    print_profile(profiler, args.ticks, args.top)
    counters = sim.systems.counters.take()

    if counters:
        print("\nCounters over the profiled ticks: " + ", ".join(f"{name} {value}" for name, value in sorted(counters.items())))


if __name__ == "__main__":
    main()