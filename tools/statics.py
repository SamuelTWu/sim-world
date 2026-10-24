import random
import tracemalloc

from src.simworld.sim.core.sim_context import TILE_UNITS

STATIC_BLUEPRINT = {"name": "static", "kind": "static", "sprite_id": "pixel", "tags": ["static"]}


def spawn_statics(sim, count, seed, size, around=None, spread=None):
    rng = random.Random(seed + 77)

    for _ in range(count):
        if around is None:
            x, y = rng.randint(2, size - 2) * TILE_UNITS + rng.uniform(4, 28), rng.randint(2, size - 2) * TILE_UNITS + rng.uniform(4, 28)
        else:
            x, y = around[0] + rng.uniform(-spread[0], spread[0]) * TILE_UNITS / 2, around[1] + rng.uniform(-spread[1], spread[1]) * TILE_UNITS / 2

        sim.spawn_pixel(STATIC_BLUEPRINT, None, x, y)


def spawn_statics_measured(sim, count, seed, size, settle_ticks=2):
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    spawn_statics(sim, count, seed, size)

    for _ in range(settle_ticks):
        sim.step()

    after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    return (after - before) / count if count else 0.0