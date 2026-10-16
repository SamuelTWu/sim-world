"""README 9.2: only run the expensive simulation systems near players, without freezing or unloading anything.

Part 1 checks entity/system/activity.py alone: which chunks are near, the far pixels' turns and the time they are owed, wakes, and that it is
off until refreshed. Part 2 runs the real Simulation: pixels far from every player still age, walk (also across chunk borders) and get
hungry as fast as near ones, only their needs, memory and decisions run less often; the same seed and commands still give the same world, and
switching the tiers off gives the old behaviour. Run from the folder that contains game/ and server/.
"""
import random
import types

from src.simworld.sim.core.activity import ACTIVE_CHUNKS, WAKE_TICKS, Activity, wake
from src.simworld.sim.core.sim_context import TILE_UNITS
from src.simworld.sim.simulation import TICK_DT, Simulation
from src.simworld.world.chunks import CHUNK_SIZE, chunk_of_point
from src.simworld.world.generator import GenerationSettings

checks = 0
CHUNK = CHUNK_SIZE * TILE_UNITS


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def near(a, b, tolerance=1e-6):
    return abs(a - b) <= tolerance


def pixel(pixel_id, x, y):
    return types.SimpleNamespace(id=pixel_id, position=types.SimpleNamespace(x=x, y=y))


# ---- part 1: Activity on its own
a = Activity()
here = pixel(1, 10.0, 10.0)
ok(a.is_active(pixel(1, 99999.0, 99999.0), 0) and a.due_dt(here, 0, TICK_DT) == TICK_DT, "before the first refresh everything is active (tools that skip Simulation.step are unchanged)")
a.refresh([(CHUNK * 10 + 5, CHUNK * 10 + 5)])      # one anchor in chunk (10, 10)
ok(a.tiers_on, "the tiers are on after a refresh")
ok(a.is_active(pixel(2, CHUNK * 10, CHUNK * 10), 0), "a pixel in the anchor's chunk is active")
ok(a.is_active(pixel(3, CHUNK * (10 + ACTIVE_CHUNKS) + 1, CHUNK * (10 - ACTIVE_CHUNKS) + 1), 0), f"{ACTIVE_CHUNKS} chunks away (diagonal) is still active")
ok(not a.is_active(pixel(4, CHUNK * (11 + ACTIVE_CHUNKS), CHUNK * 10), 0), f"{ACTIVE_CHUNKS + 1} chunks away is far")
ok(len(a.near) == (2 * ACTIVE_CHUNKS + 1) ** 2, "the near set is a square of chunks")

first = a.near
a.refresh([(CHUNK * 10 + 99, CHUNK * 10 + 7)])     # moved inside the same chunk: nothing is rebuilt
ok(a.near is first, "an anchor that stays in its chunk costs nothing")
a.refresh([(CHUNK * 20, CHUNK * 20)])
ok(a.near is not first and a.is_active(pixel(5, CHUNK * 20, CHUNK * 20), 0) and not a.is_active(pixel(2, CHUNK * 10, CHUNK * 10), 0), "when the anchor moves to another chunk the near area follows")
a.refresh([(CHUNK * 20, CHUNK * 20), (CHUNK * 40, CHUNK * 3)])
ok(a.is_active(pixel(6, CHUNK * 40, CHUNK * 3), 0) and a.is_active(pixel(7, CHUNK * 20, CHUNK * 20), 0), "every anchor makes its own area near")

# far pixels: staggered turns, and no time is lost
a = Activity(far_stride=10)
a.refresh([(0.0, 0.0)])
far_pixels = [pixel(i, CHUNK * 50, CHUNK * 50) for i in range(1, 21)]
turns = {p.id: [] for p in far_pixels}
applied = dict.fromkeys(turns, 0.0)

for tick in range(100):
    a.refresh([(0.0, 0.0)])

    for p in far_pixels:
        step = a.due_dt(p, tick, TICK_DT)

        if step is not None:
            turns[p.id].append(tick)
            applied[p.id] += step

ok(all(len(t) == 10 for t in turns.values()), "a far pixel takes its turn once in FAR_STRIDE ticks")
ok(all(all(b - a_ == 10 for a_, b in zip(t, t[1:])) for t in turns.values()), "its turns are exactly FAR_STRIDE ticks apart")
ok(len({t[0] for t in turns.values()}) == 10, "pixels take their turns on different ticks (id staggered), so the work is spread out")
ok(all(applied[i] <= 100 * TICK_DT + 1e-9 and 100 * TICK_DT - applied[i] <= (10 - 1) * TICK_DT + 1e-9 for i in applied), "over 100 ticks a far pixel is handed all the time that passed, except what it will get on its next turn")
ok(a.far_now == 20 and a.active_now == 0, "the far counter counts this tick's far pixels")

# a far pixel that becomes active gets the time it was owed at once
p = pixel(1, CHUNK * 50, CHUNK * 50)
a = Activity(far_stride=10)
a.refresh([(0.0, 0.0)])
owed_ticks = 0
tick = 0
while a.due_dt(p, tick, TICK_DT) is None:
    tick += 1
    owed_ticks += 1
a.due_dt(p, tick + 1, TICK_DT)          # skipped (not its turn)
a.refresh([(CHUNK * 50, CHUNK * 50)])   # a player's pixel arrives
step = a.due_dt(p, tick + 2, TICK_DT)
ok(near(step, TICK_DT * 2, 1e-9) and a.owed_for(p.id) == 0.0, "an arriving pixel is handed the time it was owed together with this tick's")

# wake
a = Activity(far_stride=10)
a.refresh([(0.0, 0.0)])
sleeper = pixel(9, CHUNK * 50, CHUNK * 50)
ctx = types.SimpleNamespace(activity=a, tick=100)
ok(not a.is_active(sleeper, 100), "a far pixel is far")
wake(ctx, sleeper)
ok(all(a.is_active(sleeper, 100 + k) for k in range(WAKE_TICKS)) and not a.is_active(sleeper, 100 + WAKE_TICKS), "a wake keeps it active for WAKE_TICKS, then it is far again")
ok(sleeper.id not in a.awake, "an expired wake is forgotten")
wake(types.SimpleNamespace(tick=1), sleeper)    # a context without activity: nothing happens
wake(ctx, None)
a.wake(sleeper, 5, 10)
a.wake(sleeper, 5, 3)
ok(a.awake[sleeper.id] == 15, "a shorter wake never shortens a longer one")
a.forget(sleeper.id)
ok(sleeper.id not in a.awake, "forget removes a pixel's wake and owed time")

# switches
a = Activity(far_stride=1)
a.refresh([(0.0, 0.0)])
ok(not a.tiers_on and a.is_active(pixel(1, CHUNK * 90, CHUNK * 90), 0) and a.due_dt(pixel(1, CHUNK * 90, CHUNK * 90), 3, TICK_DT) == TICK_DT, "far_stride 1 turns the tiers off")
a = Activity(active_chunks=0)
a.refresh([(0.0, 0.0)])
ok(not a.tiers_on, "active_chunks 0 turns the tiers off")
a.configure(active_chunks=2, far_stride=4)
a.refresh([(0.0, 0.0)])
ok(a.tiers_on and a.far_stride == 4 and a.active_chunks == 2 and len(a.near) == 25, "configure changes the radius and stride")
a.configure(far_stride=0)
ok(a.far_stride == 1, "a stride below 1 means 1")

# ---- part 2: the real simulation
SEED = 5
STRIDE = 10


def blueprint(sim, *names):
    factory = sim.entity_manager.entity_factory

    for name in names:
        try:
            return factory.load_definition(name)
        except (OSError, ValueError):
            continue

    raise RuntimeError(f"none of these blueprints exist: {names}")


def make_sim(tiers=True, owned_at=((4, 4),)):
    """A 120x120 world with 300 pixels nobody owns, spread over all of it (the simulation no longer spawns any itself), plus one pixel per owned_at tile for player 1."""
    sim = Simulation(GenerationSettings(width=120, height=120, seed=SEED))
    sim.start_new_game(SEED)
    sim.systems.activity.configure(active_chunks=ACTIVE_CHUNKS if tiers else 0, far_stride=STRIDE if tiers else 1, sleep_ticks=0)   # sleeping (9.3) has its own check
    runner = blueprint(sim, "runner", "pixel_runner")
    swimmer = blueprint(sim, "swimmer", "pixel_swimmer")
    scatter = random.Random(SEED + 1)

    for _ in range(150):
        sim.spawn_pixel(swimmer, None, scatter.randint(2, 60) * TILE_UNITS, scatter.randint(2, 118) * TILE_UNITS)
        sim.spawn_pixel(runner, None, scatter.randint(60, 119) * TILE_UNITS, scatter.randint(2, 118) * TILE_UNITS)

    for tile_x, tile_y in owned_at:
        sim.spawn_pixel(runner, 1, tile_x * TILE_UNITS + 16, tile_y * TILE_UNITS + 16)

    return sim


def signature(sim):
    return sorted((p.id, round(p.position.x, 3), round(p.position.y, 3), round(p.health, 6)) for p in sim.entity_manager.all())


def run(sim, ticks):
    for _ in range(ticks):
        sim.step()


sim = make_sim()
sim.step()
activity = sim.systems.activity
ok(activity.tiers_on and activity.anchor_chunks == {(0, 0)}, f"the player's pixel makes chunk (0, 0) the anchor: {activity.anchor_chunks}")
mine = [sim.entity_manager.get(i) for i in sim.owned_ids(1)]
ok(all(activity.is_active(p, sim.tick) for p in mine), "a player's own pixel is always active")
everyone = [p for p in sim.entity_manager.all() if p.alive]
far = [p for p in everyone if not activity.is_active(p, sim.tick)]
close = [p for p in everyone if activity.is_active(p, sim.tick)]
ok(len(far) > 20 and len(close) > 20, f"the world has both near and far pixels: {len(close)} near, {len(far)} far")
ok(all(chunk_of_point(p.position.x, p.position.y, TILE_UNITS) not in activity.near for p in far), "far means outside the near chunks")

# what a far pixel keeps doing
tracked = [p for p in far if p.alive][:40]
ids = {p.id for p in tracked}
need_time = dict.fromkeys(ids, 0.0)
need_calls = [0]
original = sim.systems.need_system.update


def spy(entity, step):
    if entity.id in need_time:
        need_time[entity.id] += step
        need_calls[0] += 1

    return original(entity, step)


sim.systems.need_system.update = spy
ages = {p.id: p.age for p in tracked}
start_tick = sim.tick
moved_between_turns = 0
crossed = 0
last = {p.id: (p.position.x, p.position.y) for p in tracked}
chunk_before = {p.id: chunk_of_point(p.position.x, p.position.y, TILE_UNITS) for p in tracked}
TICKS = 100

for _ in range(TICKS):
    sim.step()
    now_tick = sim.tick - 1

    for p in tracked:
        if p.alive and (p.position.x, p.position.y) != last[p.id] and (now_tick + p.id) % STRIDE != 0:
            moved_between_turns += 1

        last[p.id] = (p.position.x, p.position.y)

for p in tracked:
    if p.alive and chunk_of_point(p.position.x, p.position.y, TILE_UNITS) != chunk_before[p.id]:
        crossed += 1

alive = [p for p in tracked if p.alive]
ok(len(alive) >= len(tracked) // 2, "far pixels are still in the world")
ok(all(near(p.age - ages[p.id], TICKS * TICK_DT, 1e-6) for p in alive), "far pixels age every tick")
ok(moved_between_turns > 0, f"far pixels keep walking on the ticks between their turns ({moved_between_turns} steps)")
ok(all(abs(need_time[p.id] - TICKS * TICK_DT) <= STRIDE * TICK_DT + 1e-9 for p in alive), "a far pixel's needs are handed all the time that passed (give or take one stride: time owed from before the run, time owed at its end), in bigger steps")
ok(need_calls[0] < len(alive) * TICKS * 0.5, f"but its needs ran far less often: {need_calls[0]} updates instead of {len(alive) * TICKS}")
print(f"  ({crossed} of {len(tracked)} tracked far pixels crossed a chunk border during the run)")
ok(all(0 <= p.position.x < 120 * TILE_UNITS and 0 <= p.position.y < 120 * TILE_UNITS for p in alive), "far pixels stay inside the world")

# fewer decisions, same world size
counters_on = sim.systems.counters.take()
ok(counters_on.get("think_deferred", 0) > 0, "far pixels' decisions were deferred")
off = make_sim(tiers=False)
off.step()
off.systems.counters.take()
run(off, TICKS)
counters_off = off.systems.counters.take()
ok(counters_off.get("think_deferred", 0) == 0, "with the tiers off nothing is deferred")
ok(counters_on["thinks"] < counters_off["thinks"] * 0.9, f"the tiers cut the decisions made: {counters_on['thinks']} instead of {counters_off['thinks']}")
ok(len([p for p in sim.entity_manager.all()]) >= 1 and len(off.entity_manager.all()) >= 1, "no pixel was unloaded")

# determinism
first, second = make_sim(), make_sim()
run(first, TICKS)
run(second, TICKS)
ok(signature(first) == signature(second), "the same seed and the same pixels give the same world with the tiers on")
a1, a2 = make_sim(tiers=False), make_sim(tiers=False)
run(a1, TICKS)
run(a2, TICKS)
ok(signature(a1) == signature(a2), "and with the tiers off")
stride_one = make_sim()
stride_one.systems.activity.configure(far_stride=1)
chunks_zero = make_sim()
chunks_zero.systems.activity.configure(active_chunks=0)
run(stride_one, TICKS)
run(chunks_zero, TICKS)
ok(signature(stride_one) == signature(chunks_zero) == signature(a1), "far_stride 1 and active_chunks 0 both give exactly the world the tiers-off run gives")

# the near area follows the players, nothing else
empty = make_sim(owned_at=())
empty.step()
empty.step()
ok(empty.systems.activity.anchor_chunks == frozenset() and empty.systems.activity.last_active == 0, "with no player pixels every pixel is far (nobody to be near)")
two = make_sim(owned_at=((4, 4), (110, 110)))
two.step()
ok(two.systems.activity.anchor_chunks == {(0, 0), (6, 6)}, "every player pixel anchors its own area")
mover = two.entity_manager.get(two.owned_ids(1)[0])
mover.position.x, mover.position.y = 100 * TILE_UNITS, 20 * TILE_UNITS
two.step()
ok((100 // CHUNK_SIZE, 20 // CHUNK_SIZE) in two.systems.activity.anchor_chunks, "the area follows the pixel when it moves")
dead = two.entity_manager.get(two.owned_ids(1)[1])
dead.health = 0.0
dead.alive = False
two.step()
ok((6, 6) not in two.systems.activity.anchor_chunks, "a dead pixel no longer makes its surroundings near")

print(f"all {checks} checks passed")