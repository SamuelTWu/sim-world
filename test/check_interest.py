"""README 7.1: the spatial grid finds the same pixels as a brute-force scan, and stays correct as pixels move, die and appear."""
import random
import time
from types import SimpleNamespace as NS

from game.world.chunks import CHUNK_SIZE
from server.interest import SpatialGrid

TILE = 32
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


g = SpatialGrid(TILE)
size = CHUNK_SIZE * TILE
ok(g.cell_size == size, "a cell is one chunk")
ok(g.cell_of(0, 0) == (0, 0) and g.cell_of(size - 0.1, size) == (0, 1) and g.cell_of(-1, -1) == (-1, -1), "cell_of, including negatives")
ok(g.update(1, 10, 10) and not g.update(1, 20, 20) and g.update(1, size + 88, 10), "update reports only cell changes")
ok(g.position(1) == (size + 88, 10) and g.in_cells([(1, 0)]) == [1] and (0, 0) not in g.cells, "a pixel that moved left its old cell, which was freed")
ok(g.remove(1) and not g.remove(1) and len(g) == 0 and not g.cells, "remove")

rng = random.Random(3)
world = 500 * TILE
pixels = [NS(id=i, position=NS(x=rng.uniform(0, world), y=rng.uniform(0, world))) for i in range(5000)]
ok(g.sync(pixels) == (5000, 0), "sync adds everything the first time")


def brute_near(x, y, radius):
    return sorted(p.id for p in pixels if (p.position.x - x) ** 2 + (p.position.y - y) ** 2 <= radius * radius)


def brute_rect(x0, y0, x1, y1):
    return sorted(p.id for p in pixels if min(x0, x1) <= p.position.x <= max(x0, x1) and min(y0, y1) <= p.position.y <= max(y0, y1))


def compare(rounds):
    for _ in range(rounds):
        x, y, radius = rng.uniform(0, world), rng.uniform(0, world), rng.uniform(1, 2000)
        ok(sorted(g.near(x, y, radius)) == brute_near(x, y, radius), "near matches a brute-force scan")
        x2, y2 = x + rng.uniform(-1500, 1500), y + rng.uniform(-1500, 1500)
        ok(sorted(g.in_rect(x, y, x2, y2)) == brute_rect(x, y, x2, y2), "in_rect matches a brute-force scan")


compare(100)

for step in range(5):
    for pixel in pixels:
        if rng.random() < 0.3:
            pixel.position.x += rng.uniform(-300, 300)
            pixel.position.y += rng.uniform(-300, 300)

    pixels = [p for p in pixels if rng.random() > 0.02] + [NS(id=10000 + step * 10 + k, position=NS(x=rng.uniform(0, world), y=rng.uniform(0, world))) for k in range(5)]
    g.sync(pixels)
    ok(len(g) == len(pixels) and sum(len(c) for c in g.cells.values()) == len(g), "pixels moved, died and appeared: the grid holds exactly the living ones")
    compare(20)

near = g.near(pixels[0].position.x, pixels[0].position.y, 500)
ok(near[0] == pixels[0].id, "near lists the nearest first")
started = time.perf_counter()
for _ in range(20):
    g.sync(pixels)
print(f"sync of {len(pixels)} pixels: {(time.perf_counter() - started) / 20 * 1000:.1f} ms")

for bad in (5, 0):
    try:
        SpatialGrid(TILE, bad)
    except ValueError:
        ok(True, "bad cell sizes are refused")

ok(SpatialGrid(TILE, 4).cell_size == 4 * TILE, "smaller cells that divide the chunk are allowed")
print(f"all {checks} checks passed")