"""README 8.2: positions are small whole numbers, only changed fields are sent, and nothing has a long tail of decimals."""
import random
from types import SimpleNamespace as NS

from src.simworld.shared import protocol as proto
from src.simworld.server.replication import replication
from src.simworld.shared.protocol import POSITION_SCALE as SCALE, from_wire, to_wire
from src.simworld.client.net.replica import apply_tick_update

checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


ok(isinstance(SCALE, int) and SCALE > 0, "the scale is a positive integer")
ok(to_wire(1100.0) == 4400 and from_wire(4400) == 1100.0, "1100 world units is 4400 on the wire and back")
ok(to_wire(0.1) == 0 and to_wire(0.13) == 1 and to_wire(-3.3) == -13, "rounding, negatives included")
ok(to_wire(500 * 32) <= 65535, "the far corner of a 500x500 world fits in 16 bits (3 bytes in msgpack, a float is 9)")
ok(all(isinstance(v, int) for v in (to_wire(12.3456789), to_wire(0), to_wire(1e-9))), "always an int")
rng = random.Random(2)
ok(all(abs(from_wire(to_wire(v)) - v) <= 0.5 / SCALE + 1e-9 for v in (rng.uniform(-100, 17000) for _ in range(5000))), "the round trip is off by at most half a quantum")


def pixel(pid, x, y):
    return NS(id=pid, alive=True, owner=1, name="p", sprite_id="pixel", position=NS(x=x, y=y))


p = pixel(1, 1234.56789, 987.654321)
known = {}
enter, update, leave = replication.diff(known, {1}, {1: p}.get)


def only_small(value):
    return isinstance(value, (str, type(None))) or (isinstance(value, int) and not isinstance(value, bool))


ok(not any(isinstance(v, float) for v in enter[0].values()), "enter carries no floats at all")
ok(enter[0]["x"] == round(1234.56789 * SCALE) and enter[0]["y"] == round(987.654321 * SCALE), "positions are the quantized ints")

wire = proto.decode(proto.encode(proto.tick_update(1, enter=enter)), proto.SERVER_TYPES)
ok(wire["enter"][0]["x"] == enter[0]["x"], "they survive the protocol unchanged")

p.position.x += 0.05
ok(replication.diff(known, {1}, {1: p}.get) == ([], [], []), "a move below one quantum sends nothing")
p.position.x += 10.0
enter, update, leave = replication.diff(known, {1}, {1: p}.get)
ok(update == [{"id": 1, "x": round(p.position.x * SCALE)}], "a move sends the id and the changed coordinate only")
ok(not any(isinstance(v, float) for v in update[0].values()), "and no floats")
p.position.y += 3.0
p.name = "renamed"
update = replication.diff(known, {1}, {1: p}.get)[1]
ok(set(update[0]) == {"id", "y", "name"}, "several changes: only those fields")

# a client reading it back gets the position within half a quantum
mirror = {}
apply_tick_update(mirror, {"enter": [{"id": 1, "x": to_wire(1234.56789), "y": to_wire(987.654321), "name": "p"}]})
ok(abs(mirror[1].position.x - 1234.56789) <= 0.5 / SCALE and abs(mirror[1].position.y - 987.654321) <= 0.5 / SCALE, "the client decodes it back to world units")

# the client refuses floats and other junk where a position should be (an old server, or a damaged message)
before = dict(mirror)
stats = apply_tick_update(mirror, {"enter": [{"id": 2, "x": 1.5, "y": 2}, {"id": 3, "x": "1", "y": 2}, {"id": 4, "x": True, "y": 2}], "update": [{"id": 1, "x": 2.5}]})
ok(set(mirror) == {1} and stats["skipped"] == 4 and mirror[1].position.x == before[1].position.x, "floats where ints belong are skipped, never half-applied")

# whole tick_update messages for a crowd stay small and float-free
crowd = {i: pixel(i, rng.uniform(0, 16000), rng.uniform(0, 16000)) for i in range(200)}
known = {}
enter = replication.diff(known, set(crowd), crowd.get)[0]
for q in crowd.values():
    q.position.x += rng.uniform(-3, 3)

update = replication.diff(known, set(crowd), crowd.get)[1]


def has_float(obj):
    if isinstance(obj, float):
        return True
    if isinstance(obj, dict):
        return any(has_float(v) for v in obj.values())
    if isinstance(obj, list):
        return any(has_float(v) for v in obj)
    return False


ok(not has_float(proto.tick_update(2, enter=enter, update=update)), "a whole tick_update for 200 pixels contains not one float")
ok(all(set(u) <= {"id", "x"} for u in update), "and a pixel that only moved in x is sent as just id and x")

print(f"all {checks} checks passed")