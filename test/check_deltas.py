"""README 6.7: player A changes a tile, player B (nearby) sees it, player C (far away) only gets it when a pixel of theirs is near.

Runs a real server and three real clients over websockets.
"Mining" does not exist as a command yet, so the tile change is made on the server the way a future mining
behavior will: through world.set_tile(), scheduled onto the server's own event loop.
Run from the folder that contains game/ and server/, like the other check_*.py files.
"""
import asyncio
import threading
import time

from game.simulation import Simulation
from game.world.chunks import chunk_of_tile
from game.world.generator import GenerationSettings
from server import protocol as proto
from server.chunksync import NEAR_CHUNKS
from server.client import READY, Client
from server.server import Server

PORT = 8797
URL = f"ws://127.0.0.1:{PORT}"
TILE = 32
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def at(tile_x, tile_y):
    return [tile_x * TILE + TILE // 2, tile_y * TILE + TILE // 2]


def join(name):
    for _ in range(50):
        client = Client(URL, name, timeout=5)
        client.start()

        if client.wait(15) or not (client.error or "").startswith("could not connect"):
            client.deltas = []
            return client

        time.sleep(0.1)

    raise RuntimeError("server did not start")


def pump(client, seconds, until=None):
    """Poll a client for a while, keeping every world_delta it receives in client.deltas. Returns all messages."""
    seen, deadline = [], time.monotonic() + seconds

    while time.monotonic() < deadline:
        for message in client.poll():
            seen.append(message)

            if message["type"] == proto.WORLD_DELTA:
                client.deltas.extend(tuple(tile) for tile in message["tiles"])

        if until and until(seen):
            break

        time.sleep(0.02)

    return seen


def place(client, tile_x, tile_y):
    seq = client.command("place", {"blueprint": BLUEPRINT, "position": at(tile_x, tile_y)})
    ok(seq is not None, f"{client.name}: the place command was sent (client state: {client.state}, error: {client.error})")
    seen = pump(client, 5, until=lambda messages: any(m["type"] in (proto.COMMAND_RESULT, proto.ERROR) and m.get("seq") == seq for m in messages))
    result = [m for m in seen if m["type"] in (proto.COMMAND_RESULT, proto.ERROR) and m.get("seq") == seq]
    ok(result, f"{client.name}: no reply to place within 5 s. Messages received instead: {[m['type'] for m in seen]}")
    ok(result[0]["type"] == proto.COMMAND_RESULT, f"{client.name}: the server refused place: {result[0]}")


sim = Simulation(GenerationSettings(width=200, height=200, seed=11))
sim.start_new_game(11)
factory = sim.entity_manager.entity_factory
names = sorted(path.stem for path in factory.definitions_path.glob("*.json"))
placeable = [name for name in names if factory.load_definition(name).get("placeable", True) is not False and name != "resource_pile"]
BLUEPRINT = next((name for name in ("runner", "commander", "swimmer") if name in placeable), placeable[0] if placeable else None)
print(f"blueprints in {factory.definitions_path}: {names}; placing '{BLUEPRINT}'")
ok(BLUEPRINT is not None, "there is a placeable blueprint to test with")
server = Server(sim, "127.0.0.1", PORT, max_players=4)
loop = asyncio.new_event_loop()
threading.Thread(target=lambda: loop.run_until_complete(server.run()), daemon=True).start()

A_TILE, B_TILE, C_TILE, CHANGED = (30, 30), (36, 30), (150, 150), (33, 30)
ok(chunk_of_tile(*CHANGED) != chunk_of_tile(*C_TILE), "the changed tile and C are in different chunks")
cx, cy = chunk_of_tile(*CHANGED)
fx, fy = chunk_of_tile(*C_TILE)
ok(max(abs(cx - fx), abs(cy - fy)) > NEAR_CHUNKS, "C is outside A's and B's neighbourhood, and the change is outside C's")

alice, bob, carol = join("alice"), join("bob"), join("carol")
ok(all(c.state == READY for c in (alice, bob, carol)), "three clients joined")

place(alice, *A_TILE)
place(bob, *B_TILE)
place(carol, *C_TILE)

# Each player first gets the change log of the chunks around their own pixel. A fresh world has none, so nothing yet.
for client in (alice, bob, carol):
    pump(client, 0.5)

ok(not alice.deltas and not bob.deltas and not carol.deltas, "no tile changes yet, so no world_delta")

# A "mines" the tile: change it on the server, on the server's own thread.
before = sim.world.get_tile(*CHANGED)
after = next(tile for row in sim.world.tiles for tile in row if tile.name != before.name)
loop.call_soon_threadsafe(lambda: sim.world.set_tile(*CHANGED, after))

for client in (alice, bob, carol):
    pump(client, 1.5)

expected = (*CHANGED, after.name)
ok(expected in alice.deltas, "A receives the change")
ok(expected in bob.deltas, "B (nearby) receives the change")
ok(alice.deltas.count(expected) == 1 and bob.deltas.count(expected) == 1, "each of them receives it once")
ok(alice.world.get_tile(*CHANGED).name == after.name and bob.world.get_tile(*CHANGED).name == after.name, "A's and B's own worlds now show the new tile")
ok(not carol.deltas, "C (far away) received nothing")
ok(carol.world.get_tile(*CHANGED).name == before.name, "C's world still has the old tile")

# C gets close (a pixel placed near the changed tile stands in for walking there: both put a pixel of C's near the chunk).
place(carol, *B_TILE)
pump(carol, 1.5, until=lambda messages: any(m["type"] == proto.WORLD_DELTA for m in messages))
ok(expected in carol.deltas, "C receives the change once a pixel of theirs is near")
ok(carol.world.get_tile(*CHANGED).name == after.name, "C's world now shows the new tile")
ok(carol.take_changed_tiles() == [CHANGED], "the client reports exactly that tile as changed")

# Changed again while everyone is near: everybody gets the newest value only, once.
newest = before  # back to the original tile: still a change, and different from `after`
loop.call_soon_threadsafe(lambda: sim.world.set_tile(*CHANGED, newest))

for client in (alice, bob, carol):
    pump(client, 1.5)
    ok(client.world.get_tile(*CHANGED).name == newest.name, f"{client.name} sees the second change")

ok(len(carol.deltas) == 2, "C got exactly two entries in total (the first change, then the second)")
ok(all(c.skipped_deltas == 0 for c in (alice, bob, carol)), "no delta was skipped")

for client in (alice, bob, carol):
    client.close()

print(f"all {checks} checks passed")