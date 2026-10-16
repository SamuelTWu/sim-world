"""README 9.1: the server measures itself and logs it every few seconds.

Part 1 feeds server/metrics.py known numbers and checks the window it reports (percentiles, overruns, rates, per-client bytes, log lines).
Part 2 checks the work counters (entity/system/counters.py) in step_toward with stand-in objects.
Part 3 runs a real server and clients: the numbers it measures must match what really happened (bytes counted = bytes the client received,
pixels counted = pixels that exist) and the log must be printed. Run from the folder that contains game/ and server/.
"""
import asyncio
import threading
import time
import types

from src.simworld.sim.navigation import movement
from src.simworld.sim.core.counters import Counters, count
from src.simworld.sim.simulation import TICK_DT, Simulation
from src.simworld.world.generator import GenerationSettings
from src.simworld.shared import protocol as proto
from src.simworld.client.net.connection import Client
from src.simworld.server.metrics import MAX_CLIENT_LINES, Metrics, format_lines
from src.simworld.server.server import Server

PORT = 8798
URL = f"ws://127.0.0.1:{PORT}"
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def near(a, b, tolerance=1e-6):
    return abs(a - b) <= tolerance


# ---- part 1: the Metrics window
m = Metrics(budget=0.05)
durations = [0.010] * 90 + [0.040] * 8 + [0.060, 0.200]
for value in durations:
    m.tick(value, {"inbox": 0.001, "step": value * 0.5, "grid": 0.0, "notices": 0.0, "replicate": value * 0.25})

m.behind()
m.sent(1, "alice", "tick_update", 1000, backlog=2)
m.sent(1, "alice", "tick_update", 3000, backlog=7)
m.sent(1, "alice", "world_delta", 500)
m.sent(2, "bob", "tick_update", 200)
snap = m.snapshot(m.window_start + 5.0, pixels=42, projectiles=3, counters={"tile_checks": 500, "attacks": 10}, players=2, tick=777)

ok(snap["ticks"] == 100 and snap["tick"] == 777 and snap["players"] == 2, "tick, players and the number of ticks")
ok(near(snap["tick_ms"]["avg"], sum(durations) / 100 * 1000) and near(snap["tick_ms"]["max"], 200.0) and near(snap["tick_ms"]["budget"], 50.0), "average, max and budget in ms")
ok(near(snap["tick_ms"]["p95"], 40.0), f"95th percentile is the 95th of 100 sorted ticks: {snap['tick_ms']['p95']}")
ok(snap["overruns"] == 2 and snap["totals"]["overruns"] == 2 and snap["totals"]["ticks"] == 100, "overruns count the ticks over the budget (60 ms and 200 ms)")
ok(snap["behind_resets"] == 1 and snap["totals"]["behind_resets"] == 1, "behind resets")
ok(near(snap["phase_ms"]["inbox"], 1.0) and snap["phase_ms"]["grid"] == 0.0 and near(snap["phase_ms"]["step"], sum(durations) * 0.5 / 100 * 1000), "average ms per tick of each phase")
ok(snap["pixels"] == 42 and snap["projectiles"] == 3, "active pixels and projectiles are passed through")
ok(near(snap["counters_per_s"]["tile_checks"], 100.0) and near(snap["counters_per_s"]["attacks"], 2.0), "counters become per second rates")
ok(near(snap["bytes_per_s"], 4700 / 5.0), "total bytes per second")
ok(near(snap["by_type_per_s"]["tick_update"]["bytes"], 4200 / 5.0) and near(snap["by_type_per_s"]["world_delta"]["messages"], 0.2), "bytes and messages per type")
alice = next(c for c in snap["clients"] if c["id"] == 1)
bob = next(c for c in snap["clients"] if c["id"] == 2)
ok(near(alice["bytes_per_s"], 900.0) and near(alice["messages_per_s"], 0.6) and alice["backlog"] == 7 and alice["biggest"] == 3000 and alice["name"] == "alice", "per client: bytes, messages, worst backlog, biggest message")
ok(near(bob["bytes_per_s"], 40.0), "per client: bob")
ok(m.last is snap, "the snapshot is kept as metrics.last")

lines = format_lines(snap)
text = "\n".join(lines)
ok("active pixels 42" in text and "active projectiles 3" in text and "overruns 2/100" in text and "behind resets 1" in text, "the log shows pixels, projectiles, overruns, behind resets")
ok("tile_checks 100" in text and "tick_update" in text and "client 1 'alice'" in text and "client 2 'bob'" in text, "the log shows counters, message types and clients")
ok(lines[0].startswith("tick 777") and all(not line.startswith("[server]") for line in lines), "format_lines returns bare lines (the server adds the prefix)")

n = Metrics(0.05)
n.tick(0.01)
text = "\n".join(format_lines(n.snapshot(n.window_start + 5.0, pixels=42, pixels_total=420)))
ok("active pixels 42 of 420 (far 378)" in text, "when only some pixels get the full simulation the log says how many exist and how many are far (9.2)")
n = Metrics(0.05)
n.tick(0.01)
ok("active pixels 7 |" in "\n".join(format_lines(n.snapshot(n.window_start + 5.0, pixels=7, pixels_total=7))), "with no far pixels the log stays as it was")
n = Metrics(0.05)
n.tick(0.01)
text = "\n".join(format_lines(n.snapshot(n.window_start + 5.0, pixels=30, pixels_total=100, pixels_asleep=50)))
ok("active pixels 30 of 100 (far 20, asleep 50)" in text, "the log also says how many pixels are asleep (9.3)")
n = Metrics(0.05)
n.tick(0.01)
ok(n.snapshot(n.window_start + 1.0, pixels=3)["pixels_total"] == 3, "pixels_total defaults to the active count")

# the next window starts clean
snap2 = m.snapshot(m.window_start + 5.0)
ok(snap2["ticks"] == 0 and snap2["overruns"] == 0 and snap2["clients"] == [] and snap2["bytes_per_s"] == 0.0 and snap2["tick_ms"]["avg"] == 0.0, "an empty window reports zeros and does not divide by zero")
ok(snap2["totals"]["ticks"] == 100, "totals keep growing across windows")

# many clients: only the busiest are listed
m = Metrics(0.05)
for player in range(1, MAX_CLIENT_LINES + 4):
    m.sent(player, f"p{player}", "tick_update", player * 100)
text = "\n".join(format_lines(m.snapshot(m.window_start + 1.0)))
ok(f"p{MAX_CLIENT_LINES + 3}'" in text and "p1'" not in text and "3 more clients" in text, "with many clients only the busiest are listed, the rest are summarized")

# ---- part 2: counters
counters = Counters()
counters.add("a")
counters.add("a", 4)
ok(counters.take() == {"a": 5} and counters.take() == {}, "counters add up and take() resets them")
count(types.SimpleNamespace(), "x")   # a context without counters: nothing happens
count(types.SimpleNamespace(counters=counters), "b", 2)
ok(counters.values == {"b": 2}, "count() adds to the context's counters and ignores a context without any")


class Tile:
    def __init__(self, walkable):
        self.walkable = walkable

    def can_walk_through(self):
        return self.walkable


class Entity:
    def __init__(self):
        self.position = types.SimpleNamespace(x=100.0, y=100.0)
        self.components = {}

    def has_prop(self, name):
        return True

    def effective(self, name):
        return 2.0


world = types.SimpleNamespace(width=50, height=50)
context = types.SimpleNamespace(world=world, counters=Counters(), tile_at=lambda x, y: Tile(x < 300))
mover = Entity()
for _ in range(3):
    movement.step_toward(mover, context, 200.0, 100.0, 0.05)
ok(context.counters.values == {"tile_checks": 3}, f"each step tests the terrain once: {context.counters.values}")
mover.position.x = 290.0
movement.step_toward(mover, context, 600.0, 100.0, 0.5)
ok(context.counters.values == {"tile_checks": 4, "blocked_moves": 1}, f"a step into an unwalkable tile is counted as blocked: {context.counters.values}")
movement.step_toward(mover, context, mover.position.x, mover.position.y, 0.05)   # already there: no terrain test
ok(context.counters.values["tile_checks"] == 4, "arriving costs no terrain test")

# ---- part 3: a real server
sim = Simulation(GenerationSettings(width=120, height=120, seed=5))
sim.start_new_game(5)
factory = sim.entity_manager.entity_factory
placeable = [path.stem for path in sorted(factory.definitions_path.glob("*.json")) if factory.load_definition(path.stem).get("placeable", True) is not False and path.stem != "resource_pile"]
BLUEPRINT = next((name for name in ("runner", "commander", "swimmer") if name in placeable), placeable[0] if placeable else None)
ok(BLUEPRINT is not None, "there is a placeable blueprint to test with")
server = Server(sim, "127.0.0.1", PORT, max_players=4, stats_interval=0.6)
lines = []                      # what the server logs
server.log = lines.append
loop = asyncio.new_event_loop()
snaps = []                      # every window the server closes
close_window = server.metrics.snapshot


def keep_window(*args, **kwargs):
    snaps.append(close_window(*args, **kwargs))
    return snaps[-1]


server.metrics.snapshot = keep_window


threading.Thread(target=lambda: loop.run_until_complete(server.run()), daemon=True).start()


def join(name):
    for _ in range(50):
        client = Client(URL, name, timeout=5)
        client.start()

        if client.wait(15) or not (client.error or "").startswith("could not connect"):
            return client

        time.sleep(0.1)

    raise RuntimeError("server did not start")


def pump(client, seconds):
    deadline = time.monotonic() + seconds
    messages = []

    while time.monotonic() < deadline:
        messages.extend(client.poll())
        time.sleep(0.02)

    return messages


alice = join("alice")
seq = alice.command("place", {"blueprint": BLUEPRINT, "position": [60 * 32 + 16, 60 * 32 + 16]})
ok(seq is not None, "alice sent a place command")
pump(alice, 2.5)

deadline = time.monotonic() + 5
while time.monotonic() < deadline and server.metrics.last is None:
    time.sleep(0.05)

snap = server.metrics.last
ok(snap is not None, "the server closed at least one metrics window")
ok(snap["ticks"] >= 5 and snap["seconds"] >= 0.5, f"it measured real ticks: {snap['ticks']} in {snap['seconds']:.2f} s")
ok(snap["tick_ms"]["avg"] > 0 and snap["tick_ms"]["max"] >= snap["tick_ms"]["avg"] and snap["tick_ms"]["p95"] >= 0, "tick times were measured")
ok(set(snap["phase_ms"]) == {"inbox", "step", "grid", "notices", "replicate"} and near(sum(snap["phase_ms"].values()), snap["tick_ms"]["avg"], 0.01), "all five phases are timed and add up to the average tick")
alive = sum(1 for entity in sim.entity_manager.all() if entity.alive)
ok(snap["pixels"] + snap["pixels_asleep"] >= 1 and snap["pixels"] <= alive + 5, f"active pixels counted from the world: {snap['pixels']} (now {alive})")
ok(snap["projectiles"] == 0, "no projectile system yet: 0 active projectiles")
ok(snap["players"] == 1, "one player is connected")
ok(any(c["name"] == "alice" and c["bytes_per_s"] > 0 and c["biggest"] > 0 for window in snaps for c in window["clients"]), "alice's bytes were counted (at least the welcome and her terrain)")
kinds = {kind for window in snaps for kind in window["by_type_per_s"]}
ok({"welcome", "tick_update"} <= kinds, f"bytes are counted by message type (welcome and tick_update at least): {sorted(kinds)}")
time.sleep(0.2)
pump(alice, 0.3)
text = "\n".join(lines)
ok("[server] tick " in text and "active pixels" in text and "tick ms: avg" in text and "phases ms/tick:" in text and "network:" in text and "client 1 'alice'" in text, "the log has the tick, phase, network and client lines")
ok("overruns" in text and "behind resets" in text, "the log shows overruns and behind resets")
ok(server.metrics.totals["ticks"] >= 10, "totals count ticks")
ok(isinstance(snap["counters_per_s"], dict), "work counters are reported (what they hold depends on what pixels did)")

# switching it off
quiet = Server(sim, "127.0.0.1", PORT + 1, stats_interval=0)
ok(quiet.stats_interval == 0, "stats_interval=0 turns the log off")

alice.close()
print(f"all {checks} checks passed")