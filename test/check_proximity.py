"""README 9.7: the proximity index (entity/system/proximity.py) and the attack generator that uses it.

Part 1: the index alone. It must contain EVERY pixel within the radius (a pixel may also come back from a little farther: the caller does the exact
test), skip the dead, rebuild once per tick (or after invalidate), and still find pixels that moved a little since it was built.
Part 2: the real Simulation. attack_generator gives exactly the same candidates with the index as with the old scan of every pixel, it looks at far
fewer pixels, and a run with the index gives exactly the same world as a run without it (so the speed-up changes nothing the game does).
Run from the folder that contains game/ and server/:  python -m test.check_proximity
"""
import math
import random
import types

from game.entity.behavior.behaviors.attack import attack_generator
from game.entity.system.proximity import CELL_UNITS, DRIFT_UNITS, ProximityIndex
from game.entity.system.simContext import TILE_UNITS
from game.simulation import Simulation
from game.world.generator import GenerationSettings

checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


class Pixel:
    def __init__(self, pixel_id, x, y, alive=True):
        self.id, self.alive = pixel_id, alive
        self.position = types.SimpleNamespace(x=x, y=y)


class Pixels:
    def __init__(self, pixels):
        self.pixels = pixels
        self.calls = 0

    def all(self):
        self.calls += 1
        return list(self.pixels)


def ids(pixels):
    return {p.id for p in pixels}


# ---- part 1: the index alone
scatter = random.Random(3)
pixels = [Pixel(i, scatter.uniform(-500, 4000), scatter.uniform(-500, 4000)) for i in range(600)]
pixels[5].alive = False
manager = Pixels(pixels)
index = ProximityIndex(manager)
bad = 0

for _ in range(200):
    x, y, radius = scatter.uniform(-300, 3800), scatter.uniform(-300, 3800), scatter.choice([30.0, 160.0, 400.0])
    exact = {p.id for p in pixels if p.alive and math.hypot(p.position.x - x, p.position.y - y) <= radius}
    got = ids(index.near(x, y, radius, 1))
    bad += not exact <= got

ok(bad == 0, "every living pixel within the radius is in the short-list, for 200 random queries")
ok(5 not in ids(index.near(pixels[5].position.x, pixels[5].position.y, 50.0, 1)), "a dead pixel is never in it")
ok(len(index.near(2000.0, 2000.0, 160.0, 1)) < 100, "and the list is short compared with the 600 pixels")
ok(index.rebuilds == 1 and manager.calls == 1, "the pixels were bucketed once for all those queries in the tick")
index.near(0.0, 0.0, 10.0, 2)
ok(index.rebuilds == 2, "a new tick rebuilds it, lazily")
index.invalidate()
index.near(0.0, 0.0, 10.0, 2)
ok(index.rebuilds == 3, "invalidate() rebuilds it at the next query even in the same tick")

# pixels that move after the buckets were built are still found (within DRIFT_UNITS)
moved = Pixel(900, 1000.0, 1000.0)
pixels.append(moved)
index.invalidate()
index.near(0.0, 0.0, 1.0, 5)
moved.position.x += DRIFT_UNITS * 0.9
ok(900 in ids(index.near(1000.0 + DRIFT_UNITS * 0.9, 1000.0, 5.0, 5)), "a pixel that has stepped a little since the buckets were built is still found")
moved.position.x += 5000.0
ok(900 in ids(index.near(6000.0, 1000.0, 5.0, 6)), "and from the next tick it is found where it is")
ok(ids(ProximityIndex(Pixels([])).near(0.0, 0.0, 100.0, 0)) == set(), "an empty world gives an empty list")
ok(CELL_UNITS >= TILE_UNITS and DRIFT_UNITS >= TILE_UNITS, "the cell and the margin are at least a tile")

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


def make_sim(use_index=True):
    sim = Simulation(GenerationSettings(width=120, height=120, seed=SEED))
    sim.start_new_game(SEED)
    sim.systems.activity.configure(sleep_ticks=0)
    kinds = [blueprint(sim, "runner", "pixel_runner"), blueprint(sim, "swimmer", "pixel_swimmer"), blueprint(sim, "commander", "pixel_commander")]
    spread = random.Random(SEED + 1)

    for i in range(240):
        sim.spawn_pixel(kinds[i % 3], None if i % 4 else 2, spread.randint(2, 60) * TILE_UNITS, spread.randint(2, 60) * TILE_UNITS)   # crowded: many are in sight of each other

    sim.spawn_pixel(kinds[0], 1, 4 * TILE_UNITS + 16, 4 * TILE_UNITS + 16)

    if not use_index:
        sim.systems.context.proximity = None

    return sim


def signature(sim):
    return sorted((p.id, round(p.position.x, 3), round(p.position.y, 3), round(p.health, 6)) for p in sim.entity_manager.all())


sim = make_sim()
sim.step()
context = sim.systems.context
live = [p for p in sim.entity_manager.all() if p.alive]
sim.systems.counters.take()
with_index = {p.id: [(a.name, a.data["target"], a.data["distance"]) for a in attack_generator(p, context)] for p in live}
looked_with = sim.systems.counters.take()
index_saved = context.proximity
context.proximity = None
without = {p.id: [(a.name, a.data["target"], a.data["distance"]) for a in attack_generator(p, context)] for p in live}
looked_without = sim.systems.counters.take()
context.proximity = index_saved
ok(with_index == without, "attack_generator gives exactly the same candidates, in the same order, with the index as with the scan of every pixel")
ok(sum(1 for v in with_index.values() if v) > 20, "and many pixels actually have someone to attack in this crowd")
ok(looked_with["attack_looked"] < looked_without["attack_looked"] * 0.5, f"but it looked at far fewer pixels: {looked_with['attack_looked']} instead of {looked_without['attack_looked']}")
ok(looked_with["attack_scans"] == looked_without["attack_scans"], "for the same number of scans (counters attack_scans and attack_looked)")

first, second, plain = make_sim(), make_sim(), make_sim(use_index=False)

for _ in range(TICKS):
    first.step()
    second.step()
    plain.step()

ok(signature(first) == signature(second), "the same seed gives the same world with the index")
ok(signature(first) == signature(plain), f"and exactly the world the scan of every pixel gives, after {TICKS} ticks of a crowd that fights")
ok(first.systems.context.proximity.rebuilds <= TICKS + 5 + 241, "the index is rebuilt at most once per tick (plus spawns)")

print(f"all {checks} checks passed")