"""README 7.6: the client keeps a dict of known pixels: adds on enter, patches on update, removes on leave.

Feeds real tick_update messages (built by the server's diff, packed and unpacked by the protocol) into a real Client's poll().
"""
from types import SimpleNamespace as NS

from server import protocol as proto
from server import replication
from server.client import READY, Client
from server.replica import apply_tick_update

checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def pixel(pid, x=100.0, y=200.0, owner=2, name="p", sprite="pixel"):
    return NS(id=pid, alive=True, owner=owner, name=name, sprite_id=sprite, position=NS(x=x, y=y))


def wire(message):
    return proto.decode(proto.encode(message), proto.SERVER_TYPES)   # as it travels


client = Client("ws://unused", "t")
client.state = READY
pixels = {1: pixel(1, owner=1), 2: pixel(2, 300, 40)}
known = {}


def send(ids=None, tick=1):
    enter, update, leave = replication.diff(known, ids if ids is not None else set(pixels), pixels.get)
    client.inbox.put(wire(proto.tick_update(tick, enter, update, leave)))
    return client.poll()


send()
ok(set(client.entities) == {1, 2}, "enter adds the pixels")
e = client.entities[2]
ok((e.id, e.sprite_id, e.owner, e.name, e.position.x, e.position.y) == (2, "pixel", 2, "p", 300.0, 40.0), "with their full state")

pixels[2].position.x = 311.25
send()
ok(client.entities[2].position.x == 311.25 and client.entities[2].position.y == 40.0, "update patches only the fields it carries")
ok(client.entities[2] is e, "the same object is patched, not replaced")

pixels[2].name, pixels[2].sprite_id, pixels[2].owner = "renamed", "tank", 3
send()
ok((e.name, e.sprite_id, e.owner) == ("renamed", "tank", 3), "name, sprite and owner patch too")

del pixels[2]
send()
ok(set(client.entities) == {1}, "leave removes")
ok(client.pixel_stats == {"entered": 2, "updated": 2, "left": 1, "skipped": 0, "unknown": 0}, "the stats count what happened")

client.generator = NS(maps=None, features=None)
client.world = object()
client.welcome = {"player_id": 1}
snapshot = client.view().entities
ok([p.id for p in snapshot] == [1] and client.view().player_id == 1, "the renderer's view lists exactly the known pixels")
pixels[1].position.x = 999.0
send()
ok(snapshot is not client.view().entities and snapshot[0] is client.entities[1], "each view gets a fresh list of the same pixel objects")

# in one message: enter, update, leave are applied in that order; a pixel can leave and a new one enter
mine = {}
apply_tick_update(mine, {"enter": [{"id": 5, "x": 1, "y": 2}], "update": [{"id": 5, "x": 3}], "leave": [5]})
ok(mine == {}, "enter, then update, then leave in one message")

# an enter for a pixel already known replaces it (a resync)
apply_tick_update(mine, {"enter": [{"id": 6, "x": 1, "y": 2, "name": "a"}]})
apply_tick_update(mine, {"enter": [{"id": 6, "x": 9, "y": 9, "name": "b"}]})
ok(len(mine) == 1 and mine[6].name == "b" and mine[6].position.x == 9.0, "a repeated enter replaces")

# damaged messages never half-apply
before = {6: (mine[6].position.x, mine[6].name)}
stats = apply_tick_update(mine, {
    "enter": [{"id": "x", "x": 1, "y": 2}, {"id": 7, "x": "far", "y": 2}, {"id": 8, "y": 2}, {"id": 9, "x": 1, "y": 2, "name": 5}, "junk", {"id": True, "x": 1, "y": 2}, {"id": 10, "x": float("nan"), "y": 1}],
    "update": [{"id": 6, "x": "oops", "name": "zzz"}, {"id": 6, "owner": "bob"}, "junk", {"x": 1}],
    "leave": [[1], None],
})
ok(set(mine) == {6} and (mine[6].position.x, mine[6].name) == before[6], "malformed enters and updates change nothing")
ok(stats["skipped"] == 12 and stats["entered"] == stats["updated"] == stats["left"] == 0, "and are counted as skipped")

# updates and leaves for pixels the client does not have are counted (a missed enter), not crashed on
stats = apply_tick_update(mine, {"update": [{"id": 77, "x": 1}], "leave": [78]})
ok(stats["unknown"] == 2 and set(mine) == {6}, "unknown ids are counted, not applied")

# a long random session: the client's dict always equals what the server last diffed
import random
rng = random.Random(8)
pixels = {i: pixel(i, rng.uniform(0, 500), rng.uniform(0, 500), owner=rng.choice([None, 1, 2])) for i in range(80)}
known.clear(); client.entities.clear()
for step in range(100):
    for p in list(pixels.values()):
        if rng.random() < 0.3:
            p.position.x += rng.uniform(-5, 5)
            p.position.y += rng.uniform(-5, 5)

        if rng.random() < 0.02:
            p.name = rng.choice(["a", "b", "c"])

    shown = {i for i in pixels if rng.random() < 0.8}
    send(ids=shown, tick=step + 2)
    ok(set(client.entities) == set(known) == shown, "same pixels as the server remembers")
    ok(all((client.entities[i].position.x, client.entities[i].position.y) == replication.position(pixels[i]) and client.entities[i].name == pixels[i].name for i in shown), "same positions and names")

ok(client.pixel_stats["unknown"] == 0 and client.pixel_stats["skipped"] == 0, "a clean session never sees an unknown id or a bad entry")
print(f"all {checks} checks passed")