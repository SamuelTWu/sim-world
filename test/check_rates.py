"""README 9.4: tiered think rates, decided by a table instead of by this code.

Part 1 checks entity/system/activity.py alone: a system key that is not in the table is critical (every tick, never sleeps); a key in the table runs
once in `near` ticks for active pixels and once in `far` ticks for far ones, staggered by pixel id, and is handed ALL the time that passed; nothing
may wait longer than MAX_STRIDE; a pixel can override its own rates; whole-world systems use global_due; the counters; tiers off = full fidelity.
Part 2 runs the real Simulation: with a rate set on "needs" and "think" the needs get the same total time in fewer, bigger steps, every pixel's task
still runs EVERY tick (walking, attacking, terrain and collision tests), and the same seed and rates give the same world.
Run from the folder that contains game/ and server/:  python -m test.check_rates
"""
import random
import types

from game.entity.system.activity import ASLEEP, FAR, MAX_STRIDE, WAKING, ACTIVE, CRITICAL, Activity
from game.entity.system.counters import Counters
from game.entity.system.simContext import TILE_UNITS
from game.simulation import TICK_DT, Simulation
from game.world.chunks import CHUNK_SIZE
from game.world.generator import GenerationSettings

checks = 0
CHUNK = CHUNK_SIZE * TILE_UNITS


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def near(a, b, tolerance=1e-9):
    return abs(a - b) <= tolerance


def pixel(pixel_id, x=0.0, y=0.0, traits=None):
    return types.SimpleNamespace(id=pixel_id, position=types.SimpleNamespace(x=x, y=y), traits=traits or {})


def make(**kwargs):
    activity = Activity(**kwargs)
    activity.counters = Counters()
    activity.refresh([(0.0, 0.0)])   # one anchor at the origin: pixels at the origin are ACTIVE, pixels at CHUNK * 50 are FAR
    return activity


def drive(activity, key, entity, ticks, anchors=((0.0, 0.0),)):
    """Run `due` for one pixel for `ticks` ticks. Returns (the ticks it ran on, the total time it was handed)."""
    ran, total = [], 0.0

    for tick in range(ticks):
        activity.refresh(list(anchors))
        step = activity.due(key, entity, activity.state(entity, tick), TICK_DT, tick)

        if step is not None:
            ran.append(tick)
            total += step

    return ran, total


# ---- part 1: Activity on its own
HERE, THERE = pixel(1), pixel(2, CHUNK * 50, CHUNK * 50)

a = make()
ok(a.state(HERE, 0) == ACTIVE and a.state(THERE, 0) == FAR, "near and far pixels are told apart")
ok(a.rate_of("anything") is CRITICAL and not a.rate_of("anything").sleeps, "a key nobody put in the table is critical")
ran, total = drive(a, "collision", THERE, 100)
ok(len(ran) == 100 and near(total, 100 * TICK_DT), "a critical key runs every tick even for a far pixel, with exactly the tick's time")

a = make()
a.set_rate("wander", near=1, far=4)
ran, total = drive(a, "wander", THERE, 100)
ok(len(ran) == 25 and all(b - c == 4 for c, b in zip(ran, ran[1:])), "a far stride of 4 runs once in 4 ticks, exactly 4 apart")
ok(near(total, 100 * TICK_DT) or 100 * TICK_DT - total <= 3 * TICK_DT + 1e-9, "and is handed all the time that passed (except what it is owed for its next turn)")
ran, total = drive(a, "wander", HERE, 100)
ok(len(ran) == 100, "the same key still runs every tick for a near pixel (near stride 1)")

a = make()
a.set_rate("wander", near=5, far=10)
ran, total = drive(a, "wander", HERE, 100)
ok(len(ran) == 20, "a near stride of 5 slows even a pixel next to a player")
ok(all(near(owed, 0.0) or owed <= 4 * TICK_DT + 1e-9 for owed in [a.owed_for(HERE.id)]), "what is held back never exceeds one stride")
ok(near(total + a.owed_for(HERE.id), 100 * TICK_DT), "handed + still owed = all the time that passed (nothing is lost)")

a = make()
a.set_rate("wander", near=4, far=None)
ran, _ = drive(a, "wander", THERE, 40)
ok(len(ran) == 4, "far = None means the server's FAR_STRIDE (10)")
a.configure(far_stride=5)
a.refresh([(0.0, 0.0)])
ok(len(drive(a, "wander", THERE, 100)[0]) == 20, "and follows configure(far_stride=...)")

a = make()
a.set_rate("wander", near=1000, far=1000)
ran, _ = drive(a, "wander", HERE, 100)
ok(len(ran) == 100 // MAX_STRIDE, f"no stride can exceed MAX_STRIDE ({MAX_STRIDE})")
a.set_rate("x", near=0, far=-5)
ok(a.rates["x"].near == 1 and a.rates["x"].far == 1, "a stride below 1 means 1")

# staggering
a = make()
a.set_rate("wander", near=1, far=10)
starts = set()

for i in range(20):
    ran, _ = drive(a, "wander", pixel(100 + i, CHUNK * 50, CHUNK * 50), 10)
    starts.add(ran[0])

ok(len(starts) == 10, "pixels take their turns on different ticks (staggered by id)")

# sleeping per key
a = make()
a.set_rate("slow", near=1, far=1, sleeps=True)
a.set_rate("alert", near=1, far=1, sleeps=False)
a.sleeping[HERE.id] = 50                      # asleep until tick 50
asleep = a.state(HERE, 10)
ok(asleep == ASLEEP, "a pixel with a wake time in the future is asleep")
ok(a.due("slow", HERE, asleep, TICK_DT, 10) is None and a.owed_for(HERE.id) > 0, "a key that sleeps is skipped while the pixel sleeps (the time is kept)")
ok(near(a.due("alert", HERE, asleep, TICK_DT, 10), TICK_DT), "a key with sleeps=False still runs for a sleeping pixel")
ok(a.due("critical_one", HERE, asleep, TICK_DT, 10) == TICK_DT, "and so does a critical key")
woke = a.state(HERE, 50)
ok(woke == WAKING and near(a.due("slow", HERE, woke, TICK_DT, 50), 2 * TICK_DT), "a key that slept is handed everything it missed when the pixel wakes")
ok(a.owed_for(HERE.id) == 0.0, "nothing is owed after that")

# per-pixel override
a = make()
a.set_rate("wander", near=1, far=10)
careful = pixel(3, CHUNK * 50, CHUNK * 50, traits={"rates": {"wander": {"far": 1}}})
lazy = pixel(4, 0.0, 0.0, traits={"rates": {"wander": {"near": 5, "sleeps": False}}})
ok(len(drive(a, "wander", careful, 100)[0]) == 100, "a pixel's own 'rates' trait can make a key run every tick even when far")
ok(len(drive(a, "wander", lazy, 100)[0]) == 20, "or slow a key down when near")
ok(a.rate_of("wander", lazy).sleeps is False and a.rate_of("wander").sleeps is True, "the override only changes that pixel")
odd = pixel(5, traits={"rates": "garbage"})
ok(a.rate_of("wander", odd) is a.rates["wander"], "a malformed 'rates' trait is ignored")
a.critical("wander")
ok(a.rate_of("wander") is CRITICAL, "critical(key) makes a key run every tick again")

# whole-world systems
a = make()
ok(a.global_due("territory", 3, TICK_DT) == TICK_DT, "a whole-world system not in the table runs every tick")
a.set_rate("territory", near=4)
runs, total = [], 0.0

for tick in range(40):
    step = a.global_due("territory", tick, TICK_DT)

    if step is not None:
        runs.append(tick)
        total += step

ok(len(runs) == 10 and near(total + a.global_owed.get("territory", 0.0), 40 * TICK_DT), "a whole-world system with near 4 runs once in 4 ticks and gets all the time")
b = Activity()
b.set_rate("territory", near=4)
ok(b.global_due("territory", 3, TICK_DT) == TICK_DT, "before the first refresh everything runs every tick")

# counters
a = make()
a.set_rate("wander", near=1, far=5)
drive(a, "wander", THERE, 50)
a.refresh([(0.0, 0.0)])
values = a.counters.take()
ok(values.get("wander_runs") == 10 and values.get("wander_skips") == 40, f"runs and skips are counted per key: {values}")

# off
a = Activity()
a.set_rate("wander", near=5, far=5)
ok(a.due("wander", HERE, ACTIVE, TICK_DT, 3) == TICK_DT, "until refresh() nothing is tiered")
a = make(far_stride=1, active_chunks=0)
a.set_rate("wander", near=1, far=None)
ok(len(drive(a, "wander", THERE, 30)[0]) == 30, "with the tiers off a far pixel is active (near stride applies)")
a.forget(THERE.id)
ok(a.owed_for(THERE.id) == 0.0, "forget clears everything owed to a pixel")

print(f"part 1: {checks} checks passed")

# ---- part 2: the real simulation
SEED = 5
TICKS = 100


def blueprint(sim, *names):
    factory = sim.entity_manager.entity_factory

    for name in names:
        try:
            return factory.load_definition(name)
        except (OSError, ValueError):
            continue

    raise RuntimeError(f"none of these blueprints exist: {names}")


def make_sim(rates=None, tiers=False):
    """A 120x120 world with 200 pixels nobody owns and one player pixel. The tiers (near/far) are off unless asked, so only `rates` makes a difference."""
    sim = Simulation(GenerationSettings(width=120, height=120, seed=SEED))
    sim.start_new_game(SEED)
    sim.systems.activity.configure(active_chunks=3 if tiers else 0, far_stride=10 if tiers else 1, sleep_ticks=0)

    for key, spec in (rates or {}).items():
        sim.systems.activity.set_rate(key, **spec)

    runner = blueprint(sim, "runner", "pixel_runner")
    swimmer = blueprint(sim, "swimmer", "pixel_swimmer")
    scatter = random.Random(SEED + 1)

    for _ in range(100):
        sim.spawn_pixel(swimmer, None, scatter.randint(2, 60) * TILE_UNITS, scatter.randint(2, 118) * TILE_UNITS)
        sim.spawn_pixel(runner, None, scatter.randint(60, 119) * TILE_UNITS, scatter.randint(2, 118) * TILE_UNITS)

    sim.spawn_pixel(runner, 1, 4 * TILE_UNITS + 16, 4 * TILE_UNITS + 16)
    return sim


def signature(sim):
    return sorted((p.id, round(p.position.x, 3), round(p.position.y, 3), round(p.health, 6)) for p in sim.entity_manager.all())


def measure(sim, ticks=TICKS):
    """Run, and report what the systems were handed: need time per pixel, number of need updates, run_task calls per pixel."""
    sim.step()
    sim.systems.counters.take()
    need_time, need_calls, task_calls = {}, [0], {}
    need_original = sim.systems.need_system.update
    task_original = sim.systems.run_task

    def need_spy(entity, step):
        need_time[entity.id] = need_time.get(entity.id, 0.0) + step
        need_calls[0] += 1
        return need_original(entity, step)

    def task_spy(entity, step):
        task_calls[entity.id] = task_calls.get(entity.id, 0) + 1
        return task_original(entity, step)

    sim.systems.need_system.update = need_spy
    sim.systems.run_task = task_spy
    born = {p.id for p in sim.entity_manager.all()}

    for _ in range(ticks):
        sim.step()

    return {"need_time": need_time, "need_calls": need_calls[0], "task_calls": task_calls, "counters": sim.systems.counters.take(), "born": born}


base_sim = make_sim()
base = measure(base_sim)
ok(base["counters"].get("thinks", 0) > 0 and base["need_calls"] > 0, "the baseline (no rates) runs needs and decisions")
ok(base["counters"].get("needs_skips", 0) == 0 and base["counters"].get("think_deferred", 0) == 0, "with an empty table nothing is skipped")

rated_sim = make_sim(rates={"needs": {"near": 5, "far": 5}, "think": {"near": 4, "far": 4}})
rated = measure(rated_sim)
alive = [i for i in rated["born"] if rated_sim.entity_manager.get(i) is not None and rated_sim.entity_manager.get(i).alive]
ok(len(alive) >= len(rated["born"]) // 2, "pixels are still in the world")
ok(all(abs(rated["need_time"].get(i, 0.0) - TICKS * TICK_DT) <= 5 * TICK_DT + 1e-9 for i in alive), "with a needs stride of 5 every pixel is still handed all the time that passed (give or take one stride)")
ok(rated["need_calls"] < base["need_calls"] * 0.35, f"in far fewer, bigger steps: {rated['need_calls']} need updates instead of {base['need_calls']}")
ok(rated["counters"]["thinks"] < base["counters"]["thinks"] * 0.8, f"decisions are cut by the think rate: {rated['counters']['thinks']} instead of {base['counters']['thinks']}")
ok(rated["counters"].get("needs_skips", 0) > 0 and rated["counters"].get("needs_runs", 0) > 0, "needs_runs and needs_skips are counted")
ok(all(rated["task_calls"].get(i, 0) == TICKS for i in alive), "BUT every pixel's task (walking, attacking, terrain and collision tests) still ran on every one of the ticks")
ok(base["counters"].get("tile_checks", 0) == 0 or rated["counters"].get("tile_checks", 0) > 0, "so the terrain was still tested (when the baseline pixels walked at all)")
print(f"  (terrain tests: {base['counters'].get('tile_checks', 0)} without rates, {rated['counters'].get('tile_checks', 0)} with)")

# a key nobody listed is critical: its time is never skipped; rates set for other keys leave it alone
only_memory = make_sim(rates={"memory": {"near": 5, "far": 5}})
result = measure(only_memory)
ok(result["counters"].get("needs_skips", 0) == 0 and result["counters"].get("memory_skips", 0) > 0, "only the keys in the table are slowed")

# critical() puts the world back exactly
restored = make_sim(rates={"needs": {"near": 5, "far": 5}, "think": {"near": 4, "far": 4}})
restored.systems.activity.critical("needs")
restored.systems.activity.critical("think")
plain = make_sim()

for _ in range(TICKS):
    restored.step()
    plain.step()

ok(signature(restored) == signature(plain), "critical() on every key gives exactly the world with an empty table")

# the table composes with the near/far tiers
tiered = make_sim(rates={"needs": {"near": 2, "far": 20}}, tiers=True)
res = measure(tiered)
far_ids = [i for i in res["born"] if tiered.entity_manager.get(i) is not None and not tiered.systems.activity.is_active(tiered.entity_manager.get(i), tiered.tick)]
ok(len(far_ids) > 10, "the tiered world has far pixels")
ok(all(abs(res["need_time"].get(i, 0.0) - TICKS * TICK_DT) <= 20 * TICK_DT + 1e-9 for i in far_ids), "far pixels with a far stride of 20 still get all their time, in steps of up to a second")

# a pixel's own trait works in the real simulation
override = make_sim(rates={"needs": {"near": 5, "far": 5}})
chosen = [p for p in override.entity_manager.all() if p.owner is None][:20]

for p in chosen:
    p.traits["rates"] = {"needs": {"near": 1, "far": 1}}

res = measure(override)
ok(all(res["need_time"].get(p.id, 0.0) > 0 for p in chosen if p.alive), "pixels with a rates trait are still updated")
ok(sum(1 for p in chosen if p.alive and abs(res["need_time"].get(p.id, 0.0) - TICKS * TICK_DT) < 1e-6) >= len([p for p in chosen if p.alive]) // 2, "and get their needs every tick, whatever the table says")

# determinism
rates = {"needs": {"near": 3, "far": 7}, "think": {"near": 2, "far": 6}, "memory": {"near": 4}}
first, second = make_sim(rates=rates, tiers=True), make_sim(rates=rates, tiers=True)

for _ in range(TICKS):
    first.step()
    second.step()

ok(signature(first) == signature(second), "the same seed and the same rates give the same world")

print(f"all {checks} checks passed")