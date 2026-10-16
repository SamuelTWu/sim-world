"""README 8.3: shots and impacts are sent as small events and animated by the client; no projectile pixel is ever created or streamed.

Pure logic: the transient event log, who gets which event, the wire format, the client's timing, and the renderer's animation with a fake camera.
"""
from types import SimpleNamespace as NS

import pygame

from src.simworld.sim.core import transient_events as fx
from src.simworld.client.render.transient_events import DRAWERS, TransientEvents
from src.simworld.shared import protocol as proto
from src.simworld.client.net.connection import Client
from src.simworld.server.replication.transientsync import MAX_TRANSIENT_PER_MESSAGE, transient_events_for
from src.simworld.server.replication.interest import SpatialGrid, in_area
from src.simworld.shared.protocol import POSITION_SCALE as SCALE
from src.simworld.client.net.replica import decode_transient_events

TILE = 32
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def pixel(pid, owner, x, y, visible=True, tags=(), alive=True):
    return NS(id=pid, owner=owner, alive=alive, visible=visible, tags=set(tags), position=NS(x=x, y=y))


# ---- the log: transient events are noted, positions copied, taken once
log = fx.TransientEventLog()
ctx = NS(transient_events=log)
a, b = pixel(1, 1, 100.0, 200.0), pixel(2, 2, 400.0, 200.0)
fx.fired(ctx, a, b, "arrow")
a.position.x = 9999.0                                     # moving afterwards does not change what was noted
ok(log.items[0]["from"] == (100.0, 200.0) and log.items[0]["to"] == (400.0, 200.0), "the positions are copied when it happens")
fx.hit(ctx, a, b, "melee")
fx.emit(ctx, "explosion", "small", point=(5.0, 6.0))
ok([e["kind"] for e in log.items] == ["fired", "hit", "explosion"] and log.items[2]["to"] == (5.0, 6.0), "fired, hit and a point-only transient event")
ok(len(log.take()) == 3 and log.take() == [], "take() returns them once")
fx.emit(NS(), "fired")                                   # a context without a log: nothing happens, no crash
fx.emit(ctx, "nothing")                                  # no place at all: ignored
ok(log.items == [], "a transient event with no place is ignored")
for _ in range(1000):
    fx.emit(ctx, "spam", point=(1, 1))
ok(len(log.items) == fx.TransientEventLog.MAX_PER_TICK, "a runaway emitter is capped per tick")
log.take()

# ---- the wire format: ints, no pixel ids, survives the protocol
event = proto.transient_event("fired", "arrow", (100.0, 200.0), (400.5, 200.0))
ok(event == {"kind": "fired", "type": "arrow", "from": [100 * SCALE, 200 * SCALE], "to": [round(400.5 * SCALE), 200 * SCALE]}, "small ints, no ids")
message = proto.decode(proto.encode(proto.tick_update(7, events=[event])), proto.SERVER_TYPES)
ok(message["events"] == [event] and "enter" not in message, "a tick_update can carry only events")
ok(proto.PROTOCOL_VERSION >= 6, "the protocol version moved on")

# ---- who gets it
grid = SpatialGrid(TILE)
cell = grid.cell_size
alice_own = [(10, 3 * cell + 100, 3 * cell + 100)]       # Alice has a pixel in cell (3, 3)
near_shot = {"kind": "fired", "type": "arrow", "from": (3 * cell + 200, 3 * cell + 100), "to": (3 * cell + 400, 3 * cell + 100), "source": None, "target": None}
far_shot = {**near_shot, "from": (30 * cell, 30 * cell), "to": (30 * cell + 100, 30 * cell)}
crossing = {**near_shot, "from": (30 * cell, 30 * cell)}           # starts far away but ends near Alice
ok(in_area(grid, alice_own, None, 3 * cell + 5, 3 * cell + 5) and not in_area(grid, alice_own, None, 30 * cell, 30 * cell), "in_area: near her pixel yes, far no")
ok(in_area(grid, [], (0, 0, 100, 100), 50, 50) and not in_area(grid, [], (0, 0, 100, 100), 500, 50) and in_area(grid, [], (0, 0, 100, 100), 120, 50, margin=30), "in_area: her camera, with the margin")
ok(len(transient_events_for([near_shot], 1, alice_own, None, grid)) == 1, "a transient event near her is sent")
ok(transient_events_for([far_shot], 1, alice_own, None, grid) == [], "a transient event far from her is not")
ok(len(transient_events_for([crossing], 1, alice_own, None, grid)) == 1, "a shot that ends where she looks is sent")
ok(len(transient_events_for([far_shot], 1, [], (30 * cell - 50, 30 * cell - 50, 30 * cell + 200, 30 * cell + 50), grid)) == 1, "a transient event in her camera is sent even far from her pixels")
ok(transient_events_for([near_shot], 1, [], None, grid) == [], "a player with no pixels and no camera gets nothing")

# hidden pixels cannot be given away by their transient events
ghost, spy, plain = pixel(20, 2, 0, 0, visible=False), pixel(21, 2, 0, 0, tags=["spy"]), pixel(22, 2, 0, 0)
for hidden in (ghost, spy):
    ok(transient_events_for([{**near_shot, "source": hidden}], 1, alice_own, None, grid) == [], "an enemy's hidden pixel shooting is not shown to her")
    ok(transient_events_for([{**near_shot, "target": hidden}], 1, alice_own, None, grid) == [], "or being shot")
    ok(len(transient_events_for([{**near_shot, "source": hidden}], 2, alice_own, None, grid)) == 1, "but its owner sees it")

dead = pixel(23, 2, 0, 0, alive=False)
ok(len(transient_events_for([{**near_shot, "source": plain, "target": dead}], 1, alice_own, None, grid)) == 1, "the killing blow on a pixel that just died is still shown")
ok(len(transient_events_for([near_shot] * 200, 1, alice_own, None, grid)) == MAX_TRANSIENT_PER_MESSAGE, "one message carries a bounded number of events")

# ---- the client: decoding and timing
good = {"kind": "fired", "type": "arrow", "from": [400, 800], "to": [800, 800]}
decoded = decode_transient_events({"events": [good, {"kind": "hit", "from": [1, 2], "to": [3, 4]}, {"kind": 5, "from": [1, 2], "to": [3, 4]}, {"kind": "x", "from": [1.5, 2], "to": [3, 4]}, {"kind": "x", "from": [1], "to": [3, 4]}, "junk", {"kind": "x"}]}, stamp=2.0)
ok([e["kind"] for e in decoded] == ["fired", "hit"] and decoded[0]["from"] == (100.0, 200.0) and decoded[0]["at"] == 2.0, "damaged events are skipped, good ones decoded to world units")

client = Client("ws://unused", "t")
client.welcome = {"player_id": 1, "tick_rate": 20}
client.inbox.put({"type": "tick_update", "tick": 40, "events": [good], "_received": 100.0})
client.poll()
ok(len(client.pending_transient_events) == 1 and client.pending_transient_events[0]["at"] == 2.0, "a transient event is stamped with the server time it happened")
client.clock.offset, client.clock.last = 98.0, None
import time as _t
real = _t.monotonic
_t.monotonic = lambda: 100.0                              # server time now = 2.0 ... minus the one-tick delay = 1.95: not due yet
ok(client.take_transient_events() == [] and len(client.pending_transient_events) == 1, "it waits until the drawing has reached that moment")
_t.monotonic = lambda: 100.2
due = client.take_transient_events()
_t.monotonic = real
ok(len(due) == 1 and client.pending_transient_events == [], "then it is handed over, once")

# ---- no pixels: all of this never creates or sends a pixel
sent = proto.tick_update(7, events=[event] * 5)
ok(set(sent) == {"type", "tick", "events"}, "a tick of only shots contains events and nothing about pixels")

# ---- the renderer: animates and forgets (a fake camera, real pygame calls on a small surface)
pygame.init()
surface = pygame.Surface((400, 300))
camera = NS(world_to_screen=lambda x, y: (x / 4, y / 4), zoom=0.25)
shown = TransientEvents()
shown.add([{"kind": "fired", "type": "arrow", "from": (0.0, 400.0), "to": (800.0, 400.0)}, {"kind": "hit", "type": "melee", "from": (800.0, 400.0), "to": (800.0, 400.0)}, {"kind": "mystery", "type": "", "from": (0, 0), "to": (0, 0)}], now=10.0)
ok(len(shown.items) == 2, "an unknown kind is ignored")
drawn_pixels = []
for t in (10.0, 10.05, 10.1, 10.2):
    surface.fill((0, 0, 0))
    shown.draw(surface, camera, t)
    drawn_pixels.append(sum(1 for x in range(0, 400, 1) for y in (100, 99, 101) if surface.get_at((x, y))[:3] != (0, 0, 0)))

ok(drawn_pixels[0] > 0 or drawn_pixels[1] > 0, "something is drawn while it runs")
shown.draw(surface, camera, 11.0)
ok(shown.items == [], "and everything is gone when it has finished")
shown.add([{"kind": "hit", "type": "", "from": (0, 0), "to": (0, 0)}] * 500, now=0.0)
ok(len(shown.items) <= 64, "only so many are kept at once")
ok(set(DRAWERS) == {"fired", "hit"}, "the renderer knows fired and hit")

print(f"all {checks} checks passed")