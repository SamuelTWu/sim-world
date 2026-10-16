import asyncio
import random
import types

from src.simworld.sim.commands import command as commands
from src.simworld.sim.core.limits import LimitReached, Limits
from src.simworld.sim.core.sim_context import TILE_UNITS
from src.simworld.sim.simulation import Simulation
from src.simworld.world.generator import GenerationSettings
from src.simworld.server.server import MAX_MESSAGES_PER_CLIENT_PER_TICK, Server

checks = 0
SEED = 5


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def refused(call):
    try:
        call()
    except LimitReached as problem:
        return str(problem)

    return None


limits = Limits()
limits.configure(max_per_player=3, max_in_world=10, max_spawns=5, max_spawns_per_owner=2)
alive = {"world": 4, "owned": {1: 0, 2: 3}}
calls = {"world": 0, "owned": 0}


def count_world():
    calls["world"] += 1
    return alive["world"]


def count_owned(owner):
    calls["owned"] += 1
    return alive["owned"].get(owner, 0)


limits.check_spawn(1, 1, count_world, count_owned)
limits.note_spawn(1)
limits.check_spawn(1, 1, count_world, count_owned)
limits.note_spawn(1)
ok("per tick" in (refused(lambda: limits.check_spawn(1, 1, count_world, count_owned)) or ""), "a player can create only max_spawns_per_owner pixels in one tick")
limits.check_spawn(1, None, count_world, count_owned)
ok(calls["world"] == 1 and calls["owned"] == 1, "the world and the player are counted once per tick, not once per pixel")
limits.check_spawn(2, 1, count_world, count_owned)
ok(calls["world"] == 2, "a new tick starts the per-tick numbers again (and counts again)")
ok("most pixels allowed (3)" in (refused(lambda: limits.check_spawn(2, 2, count_world, count_owned)) or ""), "a player at max_per_player cannot create another")
alive["world"] = 10
limits.new_tick(3)
ok("world is full (10" in (refused(lambda: limits.check_spawn(3, None, count_world, count_owned)) or ""), "nobody can create a pixel when the world is full")
limits = Limits()
limits.configure(max_spawns=3, max_spawns_per_owner=100)

for _ in range(3):
    limits.check_spawn(1, None, lambda: 0, lambda owner: 0)
    limits.note_spawn(None)

ok("at most 3 per tick" in (refused(lambda: limits.check_spawn(1, 7, lambda: 0, lambda owner: 0)) or ""), "the whole world's creations per tick are bounded too")
limits.configure(max_per_player=0, max_in_world=0, max_spawns=0, max_spawns_per_owner=0)
limits.check_spawn(9, 1, lambda: 10**9, lambda owner: 10**9)
ok(True, "0 turns a pixel limit off")
limits.configure(max_thinks=-4)
ok(limits.max_thinks == 0, "max_thinks 0 means unlimited")
ok(len({limits.think_priority(i, 5) for i in range(1000)}) > 990, "the think priority separates pixels")
ok(sorted(range(300), key=lambda i: limits.think_priority(i, 1))[:50] != sorted(range(300), key=lambda i: limits.think_priority(i, 2))[:50], "and it changes from tick to tick, so the same pixels are not always left out")
counted = Limits()
counted.counters = types.SimpleNamespace(values={}, add=lambda name, amount=1: counted.counters.values.__setitem__(name, counted.counters.values.get(name, 0) + amount))
counted.configure(max_spawns=1)
counted.check_spawn(1, None, lambda: 0, lambda o: 0)
counted.note_spawn(None)
refused(lambda: counted.check_spawn(1, None, lambda: 0, lambda o: 0))
ok(counted.counters.values == {"spawn_refused": 1}, "a refusal is counted (spawn_refused)")

print(f"part 1: {checks} checks passed")


def blueprint(sim, *names):
    factory = sim.entity_manager.entity_factory

    for name in names:
        try:
            return name, factory.load_definition(name)
        except (OSError, ValueError):
            continue

    raise RuntimeError(f"none of these blueprints exist: {names}")


def make_sim(pixels=0, **limits_args):
    sim = Simulation(GenerationSettings(width=100, height=100, seed=SEED))
    sim.start_new_game(SEED)
    sim.systems.activity.configure(far_stride=1, sleep_ticks=0)
    sim.systems.limits.configure(**limits_args)
    name, definition = blueprint(sim, "runner", "pixel_runner")
    scatter = random.Random(SEED + 1)

    for _ in range(pixels):
        sim.spawn_pixel(definition, None, scatter.randint(2, 97) * TILE_UNITS, scatter.randint(2, 97) * TILE_UNITS)

    return sim, name, definition


def signature(sim):
    return sorted((p.id, round(p.position.x, 3), round(p.position.y, 3), round(p.health, 6)) for p in sim.entity_manager.all())


sim, name, definition = make_sim(max_per_player=5, max_spawns=0, max_spawns_per_owner=0)
made = 0

while True:
    reason = refused(lambda: sim.create_pixel(definition, 1, 40 * TILE_UNITS, 40 * TILE_UNITS))

    if reason:
        break

    made += 1

ok(made == 5 and sim.count_owned(1) == 5 and "most pixels allowed (5)" in reason, f"a player can own at most max_per_player pixels: {made}, {reason!r}")
ok(refused(lambda: sim.create_pixel(definition, 2, 41 * TILE_UNITS, 41 * TILE_UNITS)) is None, "another player has their own allowance")
victim = sim.entity_manager.get(sim.owned_ids(1)[0])
sim.entity_manager.kill(victim.id)
sim.step()
ok(sim.count_owned(1) == 4 and refused(lambda: sim.create_pixel(definition, 1, 40 * TILE_UNITS, 40 * TILE_UNITS)) is None, "a pixel that died frees its place")

sim, name, definition = make_sim(pixels=20, max_in_world=22, max_per_player=0, max_spawns=0, max_spawns_per_owner=0)
sim.step()
results = [refused(lambda: sim.create_pixel(definition, 1, 30 * TILE_UNITS, 30 * TILE_UNITS)) for _ in range(5)]
ok(results[:2] == [None, None] and all("world is full" in (r or "") for r in results[2:]), f"the world cannot grow past max_in_world: {results}")

sim, name, definition = make_sim(max_spawns=4, max_spawns_per_owner=3, max_per_player=0, max_in_world=0)
sim.step()
results = [refused(lambda: sim.create_pixel(definition, 1, 30 * TILE_UNITS, 30 * TILE_UNITS)) for _ in range(4)]
ok(results[:3] == [None, None, None] and results[3] is not None, "one player gets max_spawns_per_owner pixels in a tick")
results = [refused(lambda: sim.create_pixel(definition, None, 30 * TILE_UNITS, 30 * TILE_UNITS)) for _ in range(3)]
ok(results[0] is None and results[1] is not None, "and the world max_spawns in total (the neutral pixels got the 4th)")
sim.step()
ok(refused(lambda: sim.create_pixel(definition, 1, 30 * TILE_UNITS, 30 * TILE_UNITS)) is None, "the next tick allows more")
sim.systems.counters.take()
refused(lambda: [sim.create_pixel(definition, 2, 30 * TILE_UNITS, 30 * TILE_UNITS) for _ in range(10)])
ok(sim.systems.counters.take().get("spawn_refused") == 1, "the refusal was counted")

sim, name, definition = make_sim(max_per_player=2, max_spawns=0, max_spawns_per_owner=0, max_in_world=0)
commands.load_commands()
ctx = commands.CommandContext(sim)
args = {"blueprint": name, "position": [40 * TILE_UNITS, 40 * TILE_UNITS]}
outcomes = [commands.execute(ctx, 1, "place", dict(args)) for _ in range(3)]
ok([o.ok for o in outcomes] == [True, True, False] and "most pixels allowed" in outcomes[2].reason, f"place refuses past the limit with a reason, not a crash: {outcomes[2].reason!r}")

sim, name, definition = make_sim(max_in_world=10, max_spawns=2, max_spawns_per_owner=2)

for i in range(300):
    sim.spawn_pixel(definition, None, 10 * TILE_UNITS + i, 10 * TILE_UNITS)

ok(sim.count_alive() == 300, "spawn_pixel (building a world) is not limited")

THINKS = 300


def thinking_run(max_thinks, ticks):
    sim, name, definition = make_sim(pixels=THINKS, max_thinks=max_thinks)
    thought = {}
    original = sim.systems.think

    def spy(entity):
        thought[entity.id] = thought.get(entity.id, 0) + 1
        return original(entity)

    sim.systems.think = spy
    per_tick = []

    for _ in range(ticks):
        before = sum(thought.values())
        sim.step()
        per_tick.append(sum(thought.values()) - before)

    return sim, thought, per_tick


sim_free, thought_free, per_tick_free = thinking_run(0, 40)
ok(max(per_tick_free) > 100, f"without a budget many pixels think in one tick ({max(per_tick_free)})")
sim_cap, thought_cap, per_tick_cap = thinking_run(50, 40)
ok(max(per_tick_cap) <= 50, f"with max_thinks 50 no tick has more than 50 decisions ({max(per_tick_cap)})")
ok(sim_cap.systems.counters.take().get("think_capped", 0) > 0, "and the pixels left out were counted (think_capped)")
ok(len(thought_cap) >= THINKS * 0.9, f"everybody still gets a turn: {len(thought_cap)} of {THINKS} pixels thought within 40 ticks")
ok(max(thought_cap.values()) < 2.5 * (sum(thought_cap.values()) / len(thought_cap)) + 5, "and no pixel got most of the budget")
again, _, _ = thinking_run(50, 40)
ok(signature(again) == signature(sim_cap), "the same seed and the same budget give the same world")
roomy_a, _, _ = thinking_run(10**6, 40)
ok(signature(roomy_a) == signature(sim_free), "a budget that is never reached changes nothing (same world as unlimited)")
default_sim, _, _ = thinking_run(1000, 40)
ok(signature(default_sim) == signature(sim_free), "and the default budget is not reached by an ordinary world")

print(f"part 2: {checks} checks passed")


class FakeClient:
    def __init__(self, name):
        self.name, self.pending, self.closing, self.player_id = name, 0, False, 1


def make_server(per_client=None, per_tick=None):
    sim, _, _ = make_sim()
    server = Server(sim)
    handled = []
    server.handle = lambda client, message: handled.append((client.name, message))

    if per_client:
        server.per_client_messages = per_client

    if per_tick:
        server.per_tick_messages = per_tick

    return server, handled


spammer, quiet = FakeClient("spammer"), FakeClient("quiet")
server, handled = make_server()

for number in range(40):
    server.inbox.put_nowait((spammer, {"n": number}))

server.inbox.put_nowait((quiet, {"n": 0}))
server.inbox.put_nowait((quiet, {"n": 1}))
server.process_inbox()
mine = [m["n"] for who, m in handled if who == "spammer"]
ok(mine == list(range(MAX_MESSAGES_PER_CLIENT_PER_TICK)), f"a client gets at most {MAX_MESSAGES_PER_CLIENT_PER_TICK} messages handled per tick, the oldest first")
ok([m["n"] for who, m in handled if who == "quiet"] == [0, 1], "another client's messages are not held up by the spammer's")
ok(len(server.carry) == 40 - MAX_MESSAGES_PER_CLIENT_PER_TICK and server.sim.systems.counters.take().get("commands_deferred") == 24, "the rest waits (and is counted as commands_deferred)")
handled.clear()
server.process_inbox()
server.process_inbox()
ok([m["n"] for who, m in handled] == list(range(16, 40)) and not server.carry, "the waiting messages are handled in order over the next ticks")

server, handled = make_server()

for number in range(20):
    server.inbox.put_nowait((spammer, {"n": number}))

server.inbox.put_nowait((spammer, None))
server.process_inbox()
ok(handled[-1][1] is not None and len(handled) == 16, "a disconnect does not jump ahead of the messages before it")
server.process_inbox()
ok(handled[-1][1] is None and [m["n"] for _, m in handled[:-1]] == list(range(20)), "it is handled after them, once they are")

server, handled = make_server(per_client=100, per_tick=10)

for number in range(30):
    server.inbox.put_nowait((spammer if number % 2 else quiet, {"n": number}))

server.process_inbox()
ok(len(handled) == 10 and [m["n"] for _, m in handled] == list(range(10)), "there is also a total per tick, taking the oldest first")
ok(len(server.carry) == 20, "and the others wait for the next tick")

print(f"all {checks} checks passed")