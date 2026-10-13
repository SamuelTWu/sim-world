"""README 7.3: each client is told `enter` once, `update` with only the changed fields, and `leave` when a pixel stops being visible.

Uses the real grid, visible set, diff and client-side apply code, with simple stand-in pixels.
"""
import random
from types import SimpleNamespace as NS

from server import replication
from server.interest import SpatialGrid, visible_ids
from server.replica import apply_tick_update

TILE = 32
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def pixel(pid, x, y, owner=None, name="p", sprite="pixel"):
    return NS(id=pid, alive=True, owner=owner, name=name, sprite_id=sprite, position=NS(x=x, y=y))


pixels = {1: pixel(1, 1000, 1000, owner=1), 2: pixel(2, 1100, 1000, owner=2, name="neighbour"), 3: pixel(3, 9000, 9000, owner=2), 4: pixel(4, 12000, 300, owner=None)}
lookup = pixels.get
grid = SpatialGrid(TILE)
known, mirror = {}, {}   # what the server remembers about this client / what the client holds


def tick(view=None):
    grid.sync(pixels.values())
    own = [(1, pixels[1].position.x, pixels[1].position.y)] if 1 in pixels else []
    enter, update, leave = replication.diff(known, visible_ids(grid, own, view), lookup)
    apply_tick_update(mirror, {"enter": enter, "update": update, "leave": leave})
    return enter, update, leave


enter, update, leave = tick()
ok([e["id"] for e in enter] == [1, 2] and not update and not leave, "first tick: own pixel and the neighbour enter, the far ones do not")
ok(enter[1] == {"id": 2, "sprite_id": "pixel", "owner": 2, "name": "neighbour", "x": 1100.0, "y": 1000.0}, "enter carries the full state")
ok(tick() == ([], [], []), "nothing changed: nothing is sent")

pixels[2].position.x = 1130.5
enter, update, leave = tick()
ok(not enter and update == [{"id": 2, "x": 1130.5}] and not leave, "a move sends only the changed field (x)")
pixels[2].name, pixels[2].position.y = "renamed", 1010
ok(tick()[1] == [{"id": 2, "y": 1010.0, "name": "renamed"}], "changed fields only, several at once")
pixels[2].position.x += 0.001
ok(tick() == ([], [], []), "a change below the position precision is not sent")

ok(tick(view=(8900, 8900, 9100, 9100))[0] == [{"id": 3, "sprite_id": "pixel", "owner": 2, "name": "p", "x": 9000.0, "y": 9000.0}], "the camera moves over a far pixel: it enters")
enter, update, leave = tick(view=(8900, 8900, 9100, 9100))
ok(not (enter or update or leave), "and stays quiet while in view")
ok(tick()[2] == [3], "the camera moves away: it leaves")

pixels[2].position.x = 5000
ok(tick()[2] == [2], "the neighbour walks away: leave")
pixels[2].position.x = 1100
ok([e["id"] for e in tick()[0]] == [2], "and comes back: enter again with the full state")
pixels[2].alive = False
ok(tick()[2] == [2], "a dead pixel leaves")
del pixels[2]
ok(tick() == ([], [], []), "and a removed one is not reported twice")

# the client's copy always equals what it should be able to see
rng = random.Random(4)
pixels.update({100 + i: pixel(100 + i, rng.uniform(0, 4000), rng.uniform(0, 4000), owner=rng.choice([None, 2, 3])) for i in range(300)})
for step in range(60):
    for p in list(pixels.values()):
        if p.id != 1 and rng.random() < 0.4:
            p.position.x += rng.uniform(-200, 200)
            p.position.y += rng.uniform(-200, 200)

    if rng.random() < 0.1 and len(pixels) > 5:
        victim = rng.choice([i for i in pixels if i != 1])
        pixels[victim].alive = False if rng.random() < 0.5 else True
        if rng.random() < 0.5:
            del pixels[victim]

    view = (rng.uniform(0, 3000), rng.uniform(0, 3000), rng.uniform(3000, 4000), rng.uniform(3000, 4000)) if step % 3 else None
    tick(view)
    own = [(1, pixels[1].position.x, pixels[1].position.y)]
    shown = {i for i in visible_ids(grid, own, view) if i in pixels and pixels[i].alive}
    ok(set(mirror) == shown, "the client's pixels are exactly the visible, living ones")
    ok(all((mirror[i].position.x, mirror[i].position.y) == replication.position(pixels[i]) and mirror[i].owner == pixels[i].owner for i in mirror), "and their positions and owners are current")

# 7.4 hysteresis: a pixel walking back and forth over the edge does not flicker
EXTRA = 2 * TILE
pixels.clear()
pixels[1] = pixel(1, 5 * 512 + 100, 5 * 512 + 100, owner=1)           # own pixel in cell (5, 5): enter area is cells 4..6
edge = 7 * 512                                                          # the enter area ends here (x)
pixels[9] = pixel(9, edge - 20, 5 * 512 + 100, owner=2)
known.clear(); mirror.clear(); grid.cells.clear(); grid.where.clear()


def tick2():
    grid.sync(pixels.values())
    own = [(1, pixels[1].position.x, pixels[1].position.y)]
    enter, update, leave = replication.diff(known, visible_ids(grid, own), lookup, visible_ids(grid, own, extra=EXTRA))
    apply_tick_update(mirror, {"enter": enter, "update": update, "leave": leave})
    return enter, update, leave


ok([e["id"] for e in tick2()[0]] == [1, 9], "just inside the enter area: it enters")
events = 0

for x in (edge + 10, edge - 5, edge + 30, edge - 1, edge + EXTRA - 5, edge + 1):
    pixels[9].position.x = x
    enter, update, leave = tick2()
    events += len(enter) + len(leave)
    ok(9 in mirror, f"x={x - edge:+d} from the edge: still there (no flicker)")

ok(events == 0, "no enter or leave while it jitters across the edge")
pixels[9].position.x = edge + EXTRA + 40
ok(tick2()[2] == [9], "beyond the leave area it leaves")
pixels[9].position.x = edge + 10
ok(tick2()[0] == [] and 9 not in mirror, "just outside the enter area it does not come straight back")
pixels[9].position.x = edge - 20
ok([e["id"] for e in tick2()[0]] == [9], "only once it is inside the enter area again")

print(f"all {checks} checks passed")