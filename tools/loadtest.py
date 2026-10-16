"""README 9.8: load tests, and the maximum counts the server sustains at its tick rate. Run from the folder that contains game/ and server/:

    python -m test.loadtest                          # the three scenarios below once each, at a moderate size, with a verdict
    python -m test.loadtest --scenario clients --bots 60
    python -m test.loadtest --scenario cluster --crowd 3000 --crowd-tiles 10
    python -m test.loadtest --scenario burst --bots 8 --burst 256
    python -m test.loadtest --find-max               # search for the largest player / pixel / burst counts that are still sustained, and RECORD them
    python -m test.loadtest --find-max players,pixels --quick     # shorter trials
    python -m test.loadtest --far-stride 1 --sleep-ticks 0        # the same with 9.2 / 9.3 off (also --active-chunks, --rate KEY=NEAR[,FAR])

What it does. Every trial starts a REAL server in its own process (a fresh seeded world, optionally filled with a crowd of pixels), then connects
real websocket bots from this process and runs for a while. The bots are not the game's Client (no world generation, no drawing) but they speak the
real protocol: join, view, `place`, `move` orders, and they read every message, so the server really builds, encodes and sends everything.
  clients  MANY CLIENTS: N bots, each in its own place on the map (spread out, so every one asks for different terrain and pixels), each places a few
           pixels, keeps panning its view and ordering its pixels around. Shows what players cost: replication, terrain, bytes, the outbox.
  cluster  DENSE ENTITY CLUSTER: a crowd of neutral pixels packed into a few tiles (they pick fights: attack scans, collisions, hits, tiered rates
           and sleeping all in play) watched by one bot.
  burst    PROJECTILE BURSTS: bots as in `clients`, while every tick the server adds `--burst` shots (transient events, the way ranged attacks show
           up on the wire) around them, up to the cap the event log allows per tick (TransientEventLog.MAX_PER_TICK). A projectile system
           does not exist yet; if it does later, the same numbers apply to it: it hooks in through `LoadServer.inject_burst`.

A trial is SUSTAINED when, after a warm-up, over the measured seconds:
  - the typical (median) 95th percentile tick takes at most MAX_P95_FRACTION of the tick budget (50 ms at 20 Hz), so there is room for a slow tick;
  - at most MAX_OVERRUN_FRACTION of the ticks ran over the budget, and the loop never had to give up catching up ("behind resets");
  - every bot joined and none was dropped by the server (too slow, too many messages).
Everything it measures comes from the server's own 9.1 metrics (one window per second) and from what the bots received.
--find-max grows a count until a trial fails, then bisects, and appends the result (with this machine) to LOADTEST_RESULTS.md. The numbers belong to THE
MACHINE THEY WERE MEASURED ON: run it on the machine that will host the server (a cheap VPS is a lot slower than a laptop).
Load generators share the computer with the server here, so on a small machine the bots can be the limit; the report says how busy the bot side was.
"""
import argparse
import asyncio
import datetime
import json
import multiprocessing
import os
import platform
import random
import socket
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field

from src.simworld.shared import protocol as proto

TICK_RATE = 20
BUDGET_MS = 1000.0 / TICK_RATE
MAX_P95_FRACTION = 0.8
MAX_OVERRUN_FRACTION = 0.01
TILE_UNITS = 32
RESULTS_FILE = "LOADTEST_RESULTS.md"
VIEW_TILES = (40, 24)  # a bot's camera, in tiles
BURST_CAP = 256  # TransientEventLog.MAX_PER_TICK


@dataclass
class Config:
    bots: int = 0
    pixels_per_bot: int = 3
    crowd: int = 0  # neutral pixels packed into the cluster
    crowd_tiles: int = 12  # the cluster is a square this many tiles wide
    together: bool = False  # bots stand at the cluster instead of spread over the map
    burst: int = 0  # shots added per tick (transient events)
    size: int = 160  # world width and height in tiles
    seed: int = 5
    warmup: float = 3.0  # seconds, after every bot has joined
    measure: float = 8.0
    join_spread: float = 0.03  # seconds between bots connecting
    far_stride: int | None = None
    active_chunks: int | None = None
    sleep_ticks: int | None = None
    rates: list = field(default_factory=list)
    max_p95_fraction: float = MAX_P95_FRACTION

    def ramp(self):
        return self.bots * self.join_spread + (1.0 if self.bots else 0.0)

    def total_warmup(self):
        return self.ramp() + self.warmup


# ---- judging a trial (no network: these are what check_loadtest.py tests)

def percentile(values, fraction):
    ordered = sorted(values)

    if not ordered:
        return 0.0

    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def summarize(config, snapshots, bots):
    """One dict of facts and a verdict from the server's metric windows (after the warm-up) and the bots' own counters."""
    skip, windows = config.total_warmup(), []
    elapsed = 0.0

    for snap in snapshots:
        elapsed += snap["seconds"]

        if elapsed > skip + 0.5:
            windows.append(snap)

    ticks = sum(w["ticks"] for w in windows)
    seconds = sum(w["seconds"] for w in windows)
    p95s = [w["tick_ms"]["p95"] for w in windows]
    result = {
        "windows": len(windows),
        "seconds": seconds,
        "ticks": ticks,
        "tick_avg_ms": (sum(w["tick_ms"]["avg"] * w["ticks"] for w in windows) / ticks) if ticks else 0.0,
        "tick_p95_ms": statistics.median(p95s) if p95s else 0.0,
        "tick_p95_worst_ms": max(p95s) if p95s else 0.0,
        "tick_max_ms": max((w["tick_ms"]["max"] for w in windows), default=0.0),
        "overruns": sum(w["overruns"] for w in windows),
        "behind_resets": sum(w["behind_resets"] for w in windows),
        "tick_rate": ticks / seconds if seconds else 0.0,
        "players": max((w["players"] for w in windows), default=0),
        "pixels_total": max((w["pixels_total"] for w in windows), default=0),
        "pixels_active": max((w["pixels"] for w in windows), default=0),
        "pixels_asleep": max((w["pixels_asleep"] for w in windows), default=0),
        "bytes_per_s": max((w["bytes_per_s"] for w in windows), default=0.0),
        "backlog_max": max((c["backlog"] for w in windows for c in w["clients"]), default=0),
        "phase_ms": {},
        "burst_injected": sum(w.get("burst_injected", 0) for w in windows),
        "burst_kept": sum(w.get("burst_kept", 0) for w in windows),
    }

    for name in ("inbox", "step", "grid", "notices", "replicate"):
        result["phase_ms"][name] = (sum(w["phase_ms"].get(name, 0.0) * w["ticks"] for w in windows) / ticks) if ticks else 0.0

    joined = [b for b in bots if b.get("joined")]
    dropped = [b for b in bots if b.get("dropped")]
    commands = [ms for b in bots for ms in b.get("command_ms", ())]
    result.update({
        "bots": len(bots),
        "bots_joined": len(joined),
        "bots_dropped": len(dropped),
        "drop_reasons": sorted({b["dropped"] for b in dropped}),
        "join_p95_ms": percentile([b["join_ms"] for b in joined], 0.95),
        "command_p50_ms": percentile(commands, 0.5),
        "command_p95_ms": percentile(commands, 0.95),
        "bot_errors": sorted({b["error"] for b in bots if b.get("error")}),
        "bot_events": sum(b.get("events", 0) for b in bots),
        "bot_bytes": sum(b.get("bytes", 0) for b in bots),
    })
    result["verdict"], result["reasons"] = judge(config, result)
    return result


def judge(config, result):
    """("SUSTAINED" or "FAILED", the reasons it failed)."""
    reasons = []
    limit = config.max_p95_fraction * BUDGET_MS

    if result["ticks"] == 0:
        reasons.append("no ticks were measured")
    else:
        if result["tick_p95_ms"] > limit:
            reasons.append(f"typical p95 tick {result['tick_p95_ms']:.1f} ms is over {limit:.0f} ms ({config.max_p95_fraction:.0%} of the {BUDGET_MS:.0f} ms budget)")

        if result["overruns"] > MAX_OVERRUN_FRACTION * result["ticks"]:
            reasons.append(f"{result['overruns']} of {result['ticks']} ticks ran over the budget")

        if result["behind_resets"] > 0:
            reasons.append(f"the loop fell too far behind {result['behind_resets']} times")

    if result["bots_joined"] < result["bots"]:
        reasons.append(f"only {result['bots_joined']} of {result['bots']} bots joined")

    if result["bots_dropped"]:
        reasons.append(f"{result['bots_dropped']} bots were dropped by the server ({', '.join(result['drop_reasons'])})")

    return ("FAILED" if reasons else "SUSTAINED"), reasons


def search(trial, start, limit, factor=2.0, tolerance=0.1):
    """The largest n in [0, limit] for which trial(n) is True, assuming it is True up to some point and False after.

    Doubles from `start` until a trial fails (or `limit` is sustained), then bisects until the gap is within `tolerance` of the answer.
    Returns (best sustained n, the smallest n known to fail or None, how many trials it took).
    """
    runs, best, failed, n = 0, 0, None, max(1, start)

    while True:
        n = min(n, limit)
        runs += 1

        if trial(n):
            best = n

            if n >= limit:
                return best, None, runs

            n = int(n * factor) + 1
        else:
            failed = n
            break

    low, high = best, failed

    while high - low > max(1, tolerance * low):
        middle = (low + high) // 2
        runs += 1

        if trial(middle):
            low = middle
        else:
            high = middle

    return low, high, runs


def describe(config):
    parts = []

    if config.bots:
        parts.append(f"{config.bots} bots x {config.pixels_per_bot} pixels" + (" together" if config.together else ", spread over the map"))

    if config.crowd:
        parts.append(f"crowd of {config.crowd} neutral pixels in {config.crowd_tiles}x{config.crowd_tiles} tiles")

    if config.burst:
        parts.append(f"{config.burst} shots per tick")

    return ", ".join(parts) or "empty world"


def report_lines(config, result):
    lines = [
        f"  {result['verdict']}: {describe(config)} ({config.size}x{config.size} tiles)",
        f"    tick ms: avg {result['tick_avg_ms']:.1f}, typical p95 {result['tick_p95_ms']:.1f}, worst-window p95 {result['tick_p95_worst_ms']:.1f}, max {result['tick_max_ms']:.1f} (budget {BUDGET_MS:.0f}) | overruns {result['overruns']}/{result['ticks']} | behind resets {result['behind_resets']} | {result['tick_rate']:.1f} ticks/s",
        "    phases ms/tick: " + " ".join(f"{name} {value:.2f}" for name, value in result["phase_ms"].items()),
        f"    world: {result['players']} players, {result['pixels_total']} pixels ({result['pixels_active']} active, {result['pixels_asleep']} asleep) | out {result['bytes_per_s'] / 1024:.0f} KB/s | outbox backlog max {result['backlog_max']}",
    ]

    if result["bots"]:
        lines.append(f"    bots: {result['bots_joined']}/{result['bots']} joined (join p95 {result['join_p95_ms']:.0f} ms), command round trip p50 {result['command_p50_ms']:.1f} ms / p95 {result['command_p95_ms']:.1f} ms, {result['bot_events']} shots received")

    if config.burst:
        lines.append(f"    shots: {result['burst_injected']} added, {result['burst_kept']} kept by the event log (the cap is {BURST_CAP} per tick)")

    for reason in result["reasons"]:
        lines.append(f"    ! {reason}")

    for error in result["bot_errors"][:3]:
        lines.append(f"    ! bot error: {error}")

    return lines


def machine():
    return f"{platform.system()} {platform.release()} {platform.machine()}, {os.cpu_count()} cores, Python {platform.python_version()}"


def markdown_section(config, found, notes, stamp=None):
    """The block appended to LOADTEST_RESULTS.md: what was found on which machine, and how."""
    stamp = stamp or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"## {stamp}",
        f"Machine: {machine()}",
        f"Target: {TICK_RATE} ticks/s ({BUDGET_MS:.0f} ms budget); sustained = typical p95 tick <= {config.max_p95_fraction:.0%} of the budget, <= {MAX_OVERRUN_FRACTION:.0%} overruns, no behind resets, no bot dropped.",
        f"World {config.size}x{config.size} tiles, seed {config.seed}; measured {config.measure:.0f} s after a {config.total_warmup():.0f} s warm-up. "
        f"far_stride {config.far_stride if config.far_stride is not None else 'default'}, active_chunks {config.active_chunks if config.active_chunks is not None else 'default'}, sleep_ticks {config.sleep_ticks if config.sleep_ticks is not None else 'default'}, rates {config.rates or 'default'}.",
        "",
        "| What | Maximum sustained | First failure | At the maximum: tick p95 / pixels / out | Trials |",
        "|---|---|---|---|---|",
    ]

    for row in found:
        best = row["best_result"]
        at_best = f"{best['tick_p95_ms']:.1f} ms / {best['pixels_total']} / {best['bytes_per_s'] / 1024:.0f} KB/s" if best else "-"
        failure = f"{row['failed']}" if row["failed"] is not None else f"not reached (limit {row['limit']})"
        lines.append(f"| {row['what']} | {row['best']} | {failure} | {at_best} | {row['runs']} |")

    lines.append("")

    for note in notes:
        lines.append(f"- {note}")

    return "\n".join(lines) + "\n\n"


# ---- the server side of a trial (runs in its own process)

def land_near(world, tile_x, tile_y, radius=40):
    """The nearest tile around (tile_x, tile_y) that a pixel can walk on, or None."""
    for ring in range(radius):
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                if max(abs(dx), abs(dy)) != ring:
                    continue

                tile = world.get_tile(tile_x + dx, tile_y + dy)

                if tile is not None and tile.can_walk_through():
                    return tile_x + dx, tile_y + dy

    return None


def blueprint(sim, *names):
    factory = sim.entity_manager.entity_factory

    for name in names:
        try:
            return factory.load_definition(name)
        except (OSError, ValueError):
            continue

    raise RuntimeError(f"none of these blueprints exist: {names}")


def populate(sim, config):
    """Fill the world: the crowd, and where the bots will stand. Returns {"homes": [(x, y)], "center": (x, y), "crowd": how many were placed, "blueprint": a blueprint id the bots can place}."""
    rng = random.Random(config.seed + 99)  # its own generator: the simulation's seeded one is never touched
    size = config.size
    middle = land_near(sim.world, size // 2, size // 2, size // 2) or (size // 2, size // 2)
    kinds = [blueprint(sim, "runner", "pixel_runner"), blueprint(sim, "commander", "pixel_commander")]
    placed, half = 0, config.crowd_tiles // 2

    for index in range(config.crowd):
        for _ in range(12):
            tile = (middle[0] + rng.randint(-half, half), middle[1] + rng.randint(-half, half))
            ground = sim.world.get_tile(*tile)

            if ground is not None and ground.can_walk_through():
                sim.spawn_pixel(kinds[index % len(kinds)], None, tile[0] * TILE_UNITS + rng.uniform(4, 28), tile[1] * TILE_UNITS + rng.uniform(4, 28))
                placed += 1
                break

    homes = []

    for _ in range(config.bots):
        if config.together:
            spot = (middle[0] + rng.randint(-half, half), middle[1] + rng.randint(-half, half))
        else:
            spot = land_near(sim.world, rng.randint(10, size - 10), rng.randint(10, size - 10)) or middle

        homes.append((spot[0] * TILE_UNITS + 16, spot[1] * TILE_UNITS + 16))

    name = next(name for name in ("runner", "commander", "swimmer", "pixel_runner") if sim.systems.context.load_blueprint(name) is not None)
    return {"homes": homes, "center": (middle[0] * TILE_UNITS + 16, middle[1] * TILE_UNITS + 16), "crowd": placed, "blueprint": name}


def server_main(config, port, ready, stop, results, info):
    """The process that runs the real server for one trial. Metric windows go back through `results` (plain dicts)."""
    sys.stdout = open(os.devnull, "w")  # the server prints a line per player joining
    from src.simworld.sim.simulation import Simulation
    from src.simworld.world.generator import GenerationSettings
    from src.simworld.server.server import Server

    class LoadServer(Server):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.burst_rng = random.Random(config.seed + 7)
            self.started = None
            self.burst_centers = []
            self.burst_injected = 0
            self.burst_kept = 0

        async def tick_loop(self):
            self.started = time.monotonic()
            ready.set()
            await super().tick_loop()

        def process_inbox(self):
            super().process_inbox()
            self.inject_burst()

        def inject_burst(self):
            """Add `config.burst` shots this tick around the bots (or the cluster): what ranged attacks put on the wire. The log keeps at most MAX_PER_TICK."""
            if config.burst <= 0 or self.started is None or time.monotonic() - self.started < config.total_warmup():
                return

            log = self.sim.systems.transient_events
            before = len(log.items)

            for _ in range(config.burst):
                cx, cy = self.burst_rng.choice(self.burst_centers)
                x, y = cx + self.burst_rng.uniform(-9, 9) * TILE_UNITS, cy + self.burst_rng.uniform(-5, 5) * TILE_UNITS
                log.add("fired", "arrow", point=(x, y), to_point=(x + self.burst_rng.uniform(-3, 3) * TILE_UNITS, y + self.burst_rng.uniform(-3, 3) * TILE_UNITS))

            self.burst_injected += config.burst
            self.burst_kept += len(log.items) - before

        def log_stats(self, now):
            saved, self.log = self.log, (lambda line: None)
            super().log_stats(now)
            self.log = saved
            snap = dict(self.metrics.last)
            snap["burst_injected"], snap["burst_kept"] = self.burst_injected, self.burst_kept
            self.burst_injected = self.burst_kept = 0
            results.put(snap)

    sim = Simulation(GenerationSettings(width=config.size, height=config.size, seed=config.seed))
    sim.start_new_game(config.seed)
    sim.systems.activity.configure(config.active_chunks, config.far_stride, config.sleep_ticks)

    for spec in config.rates:
        key, strides = spec.split("=", 1)
        parts = [int(part) for part in strides.split(",")]
        sim.systems.activity.set_rate(key, near=parts[0], far=parts[1] if len(parts) == 2 else None)

    placed = populate(sim, config)
    info.put(placed)
    server = LoadServer(sim, "127.0.0.1", port, max_players=config.bots + 4, stats_interval=1.0)
    server.burst_centers = placed["homes"] or [placed["center"]]

    async def main():
        task = asyncio.create_task(server.run())

        while not stop.is_set():
            await asyncio.sleep(0.1)

        task.cancel()

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


# ---- the bots (this process)

async def bot(index, url, home, config, end_at, out, blueprint_id):
    """One player: join, set the camera, place a few pixels, then keep ordering them around and panning, reading everything the server sends."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    stats = out
    stats.update({"name": f"bot{index}", "joined": False, "join_ms": 0.0, "command_ms": [], "bytes": 0, "messages": 0, "events": 0, "tick_updates": 0, "dropped": None, "error": None})
    rng = random.Random(config.seed + 1000 + index)
    finishing = False

    try:
        async with connect(url, max_size=proto.MAX_MESSAGE_BYTES, compression=None, open_timeout=30) as ws:
            started = time.monotonic()
            await ws.send(proto.encode(proto.join(stats["name"])))
            first = proto.decode(await asyncio.wait_for(ws.recv(), 30), accept=proto.SERVER_TYPES)

            if first["type"] != proto.WELCOME:
                stats["error"] = f"expected welcome, got {first['type']} {first.get('code', '')}"
                return

            stats["joined"], stats["join_ms"] = True, (time.monotonic() - started) * 1000
            sent_at, mine, seq = {}, [], [0]
            half_w, half_h = VIEW_TILES[0] * TILE_UNITS / 2, VIEW_TILES[1] * TILE_UNITS / 2

            async def send_command(name, args):
                seq[0] += 1
                sent_at[seq[0]] = time.monotonic()
                await ws.send(proto.encode(proto.command(seq[0], name, args)))

            async def look(x, y):
                await ws.send(proto.encode(proto.view([x - half_w, y - half_h, x + half_w, y + half_h])))

            async def reader():
                async for raw in ws:
                    message = proto.decode(raw, accept=proto.SERVER_TYPES)
                    stats["bytes"] += len(raw)
                    stats["messages"] += 1

                    if message["type"] == proto.TICK_UPDATE:
                        stats["tick_updates"] += 1
                        stats["events"] += len(message.get("events", ()))
                    elif message["type"] in (proto.COMMAND_RESULT, proto.ERROR) and message.get("seq") in sent_at:
                        stats["command_ms"].append((time.monotonic() - sent_at.pop(message["seq"])) * 1000)
                        mine.extend(message.get("applied", ()))

            read_task = asyncio.create_task(reader())
            hx, hy = home
            await look(hx, hy)

            for _ in range(config.pixels_per_bot):
                await send_command("place", {"blueprint": blueprint_id, "position": [hx + rng.uniform(-3, 3) * TILE_UNITS, hy + rng.uniform(-3, 3) * TILE_UNITS]})

            while time.monotonic() < end_at and not read_task.done():
                await asyncio.sleep(0.8 + rng.random() * 0.4)

                if time.monotonic() >= end_at:
                    break

                px, py = hx + rng.uniform(-6, 6) * TILE_UNITS, hy + rng.uniform(-4, 4) * TILE_UNITS
                await look(px, py)

                if mine:
                    await send_command("move", {"ids": list(mine), "target": [hx + rng.uniform(-8, 8) * TILE_UNITS, hy + rng.uniform(-8, 8) * TILE_UNITS]})

            if read_task.done() and not read_task.cancelled():
                stats["dropped"] = f"closed {getattr(ws, 'close_code', '?')} {getattr(ws, 'close_reason', '')}".strip()
                problem = read_task.exception()

                if problem is not None and not isinstance(problem, ConnectionClosed):
                    stats["error"] = f"{type(problem).__name__}: {problem}"
            else:
                finishing = True
                read_task.cancel()
    except ConnectionClosed as closed:
        if not finishing:
            code = closed.rcvd.code if closed.rcvd else "?"
            stats["dropped"] = f"closed {code} {closed.rcvd.reason if closed.rcvd else ''}".strip()
    except (OSError, asyncio.TimeoutError) as problem:
        stats["error"] = f"{type(problem).__name__}: {problem}"
    except Exception as problem:  # a bot problem must show in the report, not stop the others
        stats["error"] = f"{type(problem).__name__}: {problem}"


async def run_bots(url, homes, config, duration, blueprint_id):
    end_at = time.monotonic() + duration
    outs = [{} for _ in homes]
    tasks = []

    for index, home in enumerate(homes):
        tasks.append(asyncio.create_task(bot(index, url, home, config, end_at, outs[index], blueprint_id)))
        await asyncio.sleep(config.join_spread)

    await asyncio.gather(*tasks)
    return outs


# ---- one trial

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_trial(config):
    """Start a server process, run the bots against it for warmup + measure seconds, and return summarize()'s dict."""
    context = multiprocessing.get_context("spawn")
    port = free_port()
    ready, stop = context.Event(), context.Event()
    results, info = context.Queue(), context.Queue()
    process = context.Process(target=server_main, args=(config, port, ready, stop, results, info), daemon=True)
    process.start()
    try:
        deadline = time.monotonic() + 180
        placed = None

        while not ready.is_set():
            if not process.is_alive():
                raise RuntimeError("the server process stopped before it was ready (run `python -m server.server` to see why)")

            if time.monotonic() > deadline:
                raise RuntimeError("the server was not ready after 180 s")

            time.sleep(0.1)

        placed = info.get(timeout=10)
        started = time.monotonic()
        bots = []

        if config.bots:
            bots = asyncio.run(run_bots(f"ws://127.0.0.1:{port}", placed["homes"], config, config.total_warmup() + config.measure + 1.0, placed["blueprint"]))
        else:
            time.sleep(config.total_warmup() + config.measure + 1.0)

        elapsed = time.monotonic() - started
        stop.set()
        snapshots = []

        while True:
            try:
                snapshots.append(results.get(timeout=0.5))
            except Exception:
                break
    finally:
        stop.set()
        process.join(5)

        if process.is_alive():
            process.terminate()

    result = summarize(config, snapshots, bots)
    result["crowd_placed"] = placed["crowd"] if placed else 0
    result["elapsed"] = elapsed
    return result


# ---- scenarios and the search

def scenario_config(name, args, **override):
    base = dict(size=args.size, seed=args.seed, warmup=args.warmup, measure=args.measure, far_stride=args.far_stride, active_chunks=args.active_chunks,
                sleep_ticks=args.sleep_ticks, rates=list(args.rate), max_p95_fraction=args.max_p95_fraction, pixels_per_bot=args.pixels_per_bot)

    if name == "clients":
        base.update(bots=args.bots or 40)
    elif name == "cluster":
        base.update(bots=1, crowd=args.crowd or 1500, crowd_tiles=args.crowd_tiles, together=True)
    elif name == "burst":
        base.update(bots=args.bots or 8, burst=args.burst or BURST_CAP)

    base.update(override)
    return Config(**base)


def find_max(args, names):
    found, notes = [], []
    machine_note = f"measured on {machine()}"
    notes.append(machine_note)

    for name in names:
        print(f"\nSearching for the largest sustained {name} count...")
        best_result = {"value": None}

        if name == "players":
            make, start, limit = (lambda n: scenario_config("clients", args, bots=n)), 8, args.max_bots
            label = f"players, each with {args.pixels_per_bot} pixels, spread over the map"
        elif name == "pixels":
            make, start, limit = (lambda n: scenario_config("cluster", args, crowd=n)), 250, args.max_pixels
            label = f"pixels in a dense {args.crowd_tiles}x{args.crowd_tiles}-tile cluster that fights, watched by 1 player"
        else:
            make, start, limit = (lambda n: scenario_config("burst", args, burst=n)), 32, BURST_CAP
            label = f"shots added per tick, with {args.bots or 8} players watching"

        best_seen = {}

        def trial(n, make=make, best_seen=best_seen):
            config = make(n)
            result = run_trial(config)
            ok = result["verdict"] == "SUSTAINED"
            print(f"  {n:6d}: {result['verdict']}  p95 {result['tick_p95_ms']:.1f} ms, overruns {result['overruns']}/{result['ticks']}" + ("" if ok else f"  ({'; '.join(result['reasons'][:2])})"))

            if ok:
                best_seen[n] = result

            return ok

        best, failed, runs = search(trial, start, limit)
        found.append({"what": label, "best": best, "failed": failed, "limit": limit, "runs": runs, "best_result": best_seen.get(best)})
        print(f"  -> {name}: maximum sustained {best}" + (f", fails at {failed}" if failed is not None else f" (limit {limit} reached)"))

        if name == "burst" and failed is None:
            notes.append(f"Shots: {BURST_CAP} per tick is the cap of the event log, and it was sustained: the log, not the server, limits a burst.")

    config = scenario_config("clients", args)
    notes.append(f"Players are bots that place {args.pixels_per_bot} pixels, pan their camera and order their pixels about about once a second.")
    notes.append("Re-run on the machine that will host the server; these numbers are not portable.")
    section = markdown_section(config, found, notes)

    with open(args.results, "a", encoding="utf-8") as handle:
        if handle.tell() == 0:
            handle.write("# Load test results\n\nWritten by `python -m test.loadtest --find-max`. Newest at the bottom.\n\n")

        handle.write(section)

    print(f"\nRecorded in {args.results}")
    return found


def parse():
    parser = argparse.ArgumentParser(description="Sim World load tests (README 9.8)")
    parser.add_argument("--scenario", choices=["clients", "cluster", "burst", "all"], default="all")
    parser.add_argument("--find-max", nargs="?", const="players,pixels,burst", default=None, metavar="WHICH", help="search for the largest sustained counts (players, pixels, burst: any of them, comma separated) and record them")
    parser.add_argument("--bots", type=int, default=0, help="players (default 40 for clients, 8 for burst)")
    parser.add_argument("--pixels-per-bot", type=int, default=3)
    parser.add_argument("--crowd", type=int, default=0, help="neutral pixels in the cluster (default 1500)")
    parser.add_argument("--crowd-tiles", type=int, default=12, help="the cluster is this many tiles wide: smaller is denser")
    parser.add_argument("--burst", type=int, default=0, help="shots added per tick (default %d, the cap)" % BURST_CAP)
    parser.add_argument("--size", type=int, default=160, help="world width and height in tiles")
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--warmup", type=float, default=3.0)
    parser.add_argument("--measure", type=float, default=8.0)
    parser.add_argument("--quick", action="store_true", help="shorter trials (1 s warm-up, 4 s measured)")
    parser.add_argument("--max-bots", type=int, default=400, help="the search never goes beyond this many players")
    parser.add_argument("--max-pixels", type=int, default=20000, help="the search never goes beyond this many cluster pixels")
    parser.add_argument("--max-p95-fraction", type=float, default=MAX_P95_FRACTION, help="typical p95 tick must be at most this part of the budget")
    parser.add_argument("--results", default=RESULTS_FILE)
    parser.add_argument("--far-stride", type=int, default=None)
    parser.add_argument("--active-chunks", type=int, default=None)
    parser.add_argument("--sleep-ticks", type=int, default=None)
    parser.add_argument("--rate", action="append", default=[], metavar="KEY=NEAR[,FAR]")
    args = parser.parse_args()

    if args.quick:
        args.warmup, args.measure = 1.0, 4.0

    return args


def main():
    args = parse()

    if args.find_max:
        names = [part.strip() for part in args.find_max.split(",") if part.strip()]
        unknown = [name for name in names if name not in ("players", "pixels", "burst")]

        if unknown:
            raise SystemExit(f"--find-max wants players, pixels and/or burst, not {unknown}")

        find_max(args, names)
        return

    names = ["clients", "cluster", "burst"] if args.scenario == "all" else [args.scenario]
    print(f"Load tests on {machine()}\nSustained = typical p95 tick <= {args.max_p95_fraction:.0%} of {BUDGET_MS:.0f} ms, <= {MAX_OVERRUN_FRACTION:.0%} overruns, no behind resets, no bot dropped.")

    for name in names:
        config = scenario_config(name, args)
        print(f"\n[{name}] starting a server and {config.bots} bots...")
        result = run_trial(config)
        print("\n".join(report_lines(config, result)))


if __name__ == "__main__":
    main()