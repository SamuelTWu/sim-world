"""README 7.2: the set of visible pixel ids is own pixels + their neighbouring cells + the camera view, and nothing else."""
import math
import random
from types import SimpleNamespace as NS

from src.simworld.server.replication.interest import INTEREST_CELLS, SpatialGrid, clean_view, visible_ids

TILE = 32
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


grid = SpatialGrid(TILE)
size = grid.cell_size
world = 500 * TILE
rng = random.Random(9)
pixels = {i: (rng.uniform(0, world), rng.uniform(0, world)) for i in range(4000)}
mine = [(1_000_001, 100 * size + 5, 100 * size + 5), (1_000_002, 40 * size + 200, 9 * size + 10)]
pixels.update({pid: (x, y) for pid, x, y in mine})

for pid, (x, y) in pixels.items():
    grid.update(pid, x, y)

ok(visible_ids(grid, []) == set(), "no own pixels and no view: nothing is visible")
ok({m[0] for m in mine} <= visible_ids(grid, mine), "own pixels are always visible")

# near own pixels: exactly the pixels in the (2k+1)x(2k+1) block of cells around each
near = visible_ids(grid, mine)
expect = {pid for pid, (x, y) in pixels.items() if any(abs(grid.cell_of(x, y)[0] - grid.cell_of(ox, oy)[0]) <= INTEREST_CELLS and abs(grid.cell_of(x, y)[1] - grid.cell_of(ox, oy)[1]) <= INTEREST_CELLS for _, ox, oy in mine)}
ok(near == expect, "near-own = pixels in the cells around own pixels")
far = [pid for pid in pixels if pid not in near]
ok(far and len(near) < len(pixels) / 10, "far pixels are not visible")

# the camera adds a rectangle elsewhere
view = (300 * TILE, 300 * TILE, 340 * TILE, 330 * TILE)
seen = visible_ids(grid, mine, view)
inside = {pid for pid, (x, y) in pixels.items() if view[0] <= x <= view[2] and view[1] <= y <= view[3]}
ok(seen == near | inside and inside - near, "visible = near own + inside the camera")
margin = 2 * TILE
wide = visible_ids(grid, mine, view, margin=margin)
ok(wide == near | {pid for pid, (x, y) in pixels.items() if view[0] - margin <= x <= view[2] + margin and view[1] - margin <= y <= view[3] + margin}, "the margin widens the camera view")

# a moving pixel: visible when its cell is near own pixels or in view, not otherwise
pixels[7] = (100 * size + 10, 100 * size + 10)
grid.update(7, *pixels[7])
ok(7 in visible_ids(grid, mine), "a pixel next to mine is visible")
grid.update(7, 250 * size, 250 * size)
ok(7 not in visible_ids(grid, mine), "it walks away: no longer visible")
ok(7 in visible_ids(grid, mine, (250 * size - 10, 250 * size - 10, 250 * size + 10, 250 * size + 10)), "unless my camera is on it")

# bad rectangles
big = 160 * TILE
ok(clean_view([0, 0, 10, 10], world, world, big) == (0.0, 0.0, 10.0, 10.0), "a good rectangle is kept")
ok(clean_view([10, 10, 0, 0], world, world, big) == (0.0, 0.0, 10.0, 10.0), "corners in any order")
ok(clean_view([-500, -500, 100, 100], world, world, big) == (0.0, 0.0, 100.0, 100.0), "clipped to the world")
huge = clean_view([0, 0, world, world], world, world, big)
ok(huge[2] - huge[0] == big and huge[3] - huge[1] == big, "a huge rectangle is cut down to the maximum size")
for bad in (None, [1, 2, 3], [1, 2, 3, "4"], [0, 0, math.inf, 5], [0, 0, math.nan, 5], [True, 0, 1, 1], "abcd", [world + 1000, 0, world + 2000, 10]):
    ok(clean_view(bad, world, world, big) is None, f"refused: {bad!r}")

print(f"all {checks} checks passed")