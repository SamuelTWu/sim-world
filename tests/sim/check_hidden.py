"""README 7.5: invisible pixels and spies are never sent to enemies, and are sent to their owner.

Uses the real visibility rules, grid, visible set and diff with stand-in pixels.
"""
from types import SimpleNamespace as NS

from src.simworld.sim import visibility
from src.simworld.sim.visibility import can_see
from src.simworld.server.replication import replication
from src.simworld.server.replication.interest import SpatialGrid, visible_ids

TILE = 32
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def pixel(pid, owner, x=1000, y=1000, visible=True, tags=()):
    return NS(id=pid, alive=True, owner=owner, name="p", sprite_id="pixel", visible=visible, tags=set(tags), position=NS(x=x, y=y))


plain, ghost, spy, neutral_ghost, dead = pixel(1, 1), pixel(2, 1, visible=False), pixel(3, 1, tags=["spy"]), pixel(4, None, visible=False), pixel(5, 1)
dead.alive = False

ok(can_see(1, plain) and can_see(2, plain), "an ordinary pixel is seen by everyone")
ok(can_see(1, ghost) and can_see(1, spy), "owners see their own invisible pixels and spies")
ok(not can_see(2, ghost), "an invisible pixel is hidden from an enemy")
ok(not can_see(2, spy), "a spy is hidden from an enemy")
ok(not can_see(2, neutral_ghost) and not can_see(None, ghost), "neutral invisible pixels are hidden, and a neutral pixel cannot see invisible ones either")
ok(not can_see(1, dead) and not can_see(2, None), "a dead or missing pixel is seen by nobody")

# the server-side lookup used by replication
pixels = {p.id: p for p in (plain, ghost, spy, neutral_ghost, dead)}
grid = SpatialGrid(TILE)
grid.sync([p for p in pixels.values() if p.alive])
mirror = {}


def lookup_for(player):
    return lambda pid: pixels[pid] if pid in pixels and can_see(player, pixels[pid]) else None


def tick(player, known):
    own = [(p.id, p.position.x, p.position.y) for p in pixels.values() if p.owner == player and p.alive]
    return replication.diff(known, visible_ids(grid, own), lookup_for(player), visible_ids(grid, own, extra=64))


# player 2 owns a pixel next to all of them
pixels[9] = pixel(9, 2, 1010, 1000)
grid.sync([p for p in pixels.values() if p.alive])
known1, known2 = {}, {}
enter1 = {e["id"] for e in tick(1, known1)[0]}
enter2 = {e["id"] for e in tick(2, known2)[0]}
ok(enter1 == {1, 2, 3, 9}, "player 1 is told about their own pixels (invisible and spy too) and the ordinary neighbour")
ok(enter2 == {1, 9}, "player 2 is not told about the invisible pixel, the spy or the neutral invisible pixel, only the ordinary ones")
ok(not ({2, 3, 4} & set(known2)), "nothing hidden is in what the server remembers sending to player 2")

# a pixel turning invisible (or becoming a spy) mid-game leaves the enemy's view at once; and comes back when it is visible again
plain.visible = False
enter, update, leave = tick(2, known2)
ok(leave == [1] and not enter, "an enemy pixel that turns invisible leaves the other player's view")
ok(tick(1, known1) == ([], [], []), "its owner keeps seeing it, with no events")
plain.visible = True
ok([e["id"] for e in tick(2, known2)[0]] == [1], "and it enters again when it turns visible")
plain.tags.add("spy")
ok(tick(2, known2)[2] == [1], "a pixel that becomes a spy leaves too")
plain.tags.discard("spy")
tick(2, known2)

# a hidden pixel that moves is never leaked through update
ghost.position.x += 5
ok(tick(2, known2) == ([], [], []), "a hidden pixel moving sends the enemy nothing")

# reveal hook
visibility.REVEALS.append(lambda viewer, entity: entity.id == 3 and viewer == 2)
ok(can_see(2, spy) and not can_see(2, ghost), "a reveal hook shows exactly what it says")
ok([e["id"] for e in tick(2, known2)[0]] == [3], "and the revealed spy enters")
visibility.REVEALS.clear()
ok(tick(2, known2)[2] == [3], "and leaves when the reveal ends")

# allies (diplomacy hook)
original = visibility.is_ally
visibility.is_ally = lambda viewer, owner: viewer is not None and owner is not None and {viewer, owner} <= {1, 2}
ok(can_see(2, ghost) and can_see(2, spy), "allies see each other's hidden pixels once is_ally says so")
visibility.is_ally = original

print(f"all {checks} checks passed")