"""README 7.7: a pixel walks in and out of range with no flicker, and invisible pixels and spies are never leaked.

A real server and two real clients over websockets. Alice has one pixel. Bob has a pixel that is walked, step by step, across the edge
of Alice's visible area (and jitters back and forth over it), and three more pixels standing next to Alice's: an ordinary one, an
invisible one and a spy. The server moves the walker and flips the flags on its own event loop (pixels are placed with the real `place`
command). Run from the folder that contains game/ and server/, like the other check_*.py files.
"""
import asyncio
import threading
import time

from game.simulation import Simulation
from game.world.generator import GenerationSettings
from server import protocol as proto
from server.client import Client
from server.interest import INTEREST_CELLS, SpatialGrid
from server.server import LEAVE_EXTRA_TILES, Server

PORT = 8796
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
            client.log = []     # every tick_update this client received, as (enter ids, update ids, leave ids)
            return client

        time.sleep(0.1)

    raise RuntimeError("server did not start")


def pump(client, seconds):
    deadline = time.monotonic() + seconds
    replies = []

    while time.monotonic() < deadline:
        for message in client.poll():
            replies.append(message)

            if message["type"] == proto.TICK_UPDATE:
                client.log.append(({s["id"] for s in message.get("enter", ())}, {s["id"] for s in message.get("update", ())}, set(message.get("leave", ()))))

        time.sleep(0.02)

    return replies


def place(client, tile_x, tile_y):
    seq = client.command("place", {"blueprint": BLUEPRINT, "position": at(tile_x, tile_y)})
    ok(seq is not None, f"{client.name}: the place command was sent")
    deadline = time.monotonic() + 5
    result = None

    while result is None and time.monotonic() < deadline:
        for message in pump(client, 0.1):
            if message["type"] in (proto.COMMAND_RESULT, proto.ERROR) and message.get("seq") == seq:
                result = message

    ok(result is not None and result["type"] == proto.COMMAND_RESULT, f"{client.name}: place worked: {result}")
    return result["applied"][0]


def on_server(action):
    """Run something on the server's own event loop (between ticks), then wait a moment for the result to be sent."""
    loop.call_soon_threadsafe(action)


def pixel(pixel_id):
    return sim.entity_manager.get(pixel_id)


sim = Simulation(GenerationSettings(width=200, height=200, seed=11))
sim.start_new_game(11)
factory = sim.entity_manager.entity_factory
placeable = [path.stem for path in sorted(factory.definitions_path.glob("*.json")) if factory.load_definition(path.stem).get("placeable", True) is not False and path.stem != "resource_pile"]
BLUEPRINT = next((name for name in ("pixel_runner", "pixel_commander", "pixel_swimmer") if name in placeable), placeable[0] if placeable else None)
ok(BLUEPRINT is not None, "there is a placeable blueprint to test with")
server = Server(sim, "127.0.0.1", PORT, max_players=4)
loop = asyncio.new_event_loop()
threading.Thread(target=lambda: loop.run_until_complete(server.run()), daemon=True).start()

alice, bob = join("alice"), join("bob")
grid = SpatialGrid(TILE)
cell = grid.cell_size
a_x, a_y = at(100, 100)
edge = (grid.cell_of(a_x, a_y)[0] + INTEREST_CELLS + 1) * cell      # where Alice's enter area ends (no camera view is sent)
keep = edge + LEAVE_EXTRA_TILES * TILE                                # where her keep area ends
row = grid.cell_of(a_x, a_y)[1] * cell + cell / 2
ok(edge + 1500 < 200 * TILE, "the test world is big enough for the walker's start")

# Bob's pixels first, and their flags set, BEFORE Alice has any pixel (so nothing could have been sent to her yet)
walker = place(bob, 180, 100)
plain = place(bob, 101, 100)
ghost = place(bob, 102, 100)
spy = place(bob, 103, 100)
mine = {walker, plain, ghost, spy}


def setup():
    pixel(ghost).visible = False
    pixel(spy).tags.add("spy")

    for pixel_id in mine:
        pixel(pixel_id).props["max_speed"] = 0.0      # no wandering: only the test moves them
        pixel(pixel_id).task = None

    pixel(walker).position.x, pixel(walker).position.y = edge + 1500, row


on_server(setup)
pump(bob, 0.5)
a_pixel = place(alice, 100, 100)
pump(alice, 1.0)
pump(bob, 0.2)


def put_walker(x):
    def move():
        pixel(walker).position.x, pixel(walker).position.y = x, row

    on_server(move)
    pump(bob, 0.25)
    return pump(alice, 0.25)


def walker_events(since):
    return [(kind, i) for entry in alice.log[since:] for kind, ids in zip(("enter", "update", "leave"), entry) for i in ids if i == walker]


# ---- no leaks: from the start, Alice has been told about Bob's ordinary pixel, never about the invisible one or the spy
seen = {i for entry in alice.log for ids in entry for i in ids}
ok(plain in seen, "Alice is told about Bob's ordinary pixel next to hers")
ok(ghost not in seen and spy not in seen, "Alice is NOT told about Bob's invisible pixel or his spy")
ok(walker not in seen, "Alice is not told about the walker while it is far away")
ok({ghost, spy} <= {i for entry in bob.log for ids in entry for i in ids}, "Bob is told about his own invisible pixel and spy")

# ---- the walker approaches, jitters over the enter edge, and walks away
start = len(alice.log)
for x in (edge + 600, edge + 300, edge + 100):
    put_walker(x)

ok(not walker_events(start), "outside the enter area: nothing is sent")
put_walker(edge - 30)
ok([kind for kind, _ in walker_events(start)] == ["enter"], "inside the enter area: it enters, once")

mark = len(alice.log)
for x in (edge + 10, edge - 20, edge + 40, edge - 5, keep - 10, edge - 1, edge + 20):
    put_walker(x)

ok(not [e for e in walker_events(mark) if e[0] in ("enter", "leave")], "jittering across the enter edge and into the keep margin: no enter, no leave (no flicker)")

mark = len(alice.log)
put_walker(keep + 200)
ok([kind for kind, _ in walker_events(mark)] == ["leave"], "beyond the keep area: it leaves, once")
put_walker(keep + 800)
put_walker(edge + 15)
ok(not [e for e in walker_events(mark) if e[0] == "enter"], "just outside the enter area it does not come straight back")
put_walker(edge - 50)
ok([kind for kind, _ in walker_events(mark)] == ["leave", "enter"], "it enters again only once it is inside the enter area")
put_walker(edge - 400)
ok(any(kind == "update" for kind, _ in walker_events(mark)), "and while inside, its moves arrive as updates")

# ---- flags flip mid-game: leave at once, and come back when visible again; Bob keeps seeing his own
mark = len(alice.log)
on_server(lambda: setattr(pixel(plain), "visible", False))
pump(alice, 0.4)
ok(("leave", plain) in [(k, i) for entry in alice.log[mark:] for k, ids in zip(("enter", "update", "leave"), entry) for i in ids], "a pixel that turns invisible leaves Alice's view at once")
on_server(lambda: setattr(pixel(plain), "visible", True))
pump(alice, 0.4)
ok(any(plain in entry[0] for entry in alice.log[mark:]), "and enters again when it turns visible")
on_server(lambda: setattr(pixel(ghost), "visible", True))
pump(alice, 0.4)
ok(any(ghost in entry[0] for entry in alice.log[mark:]), "an invisible pixel that is made visible enters")
on_server(lambda: setattr(pixel(ghost), "visible", False))
pump(alice, 0.4)
ok(any(ghost in entry[2] for entry in alice.log[mark:]), "and leaves when made invisible again")

# ---- Alice's client holds exactly what she was told: the walker and Bob's visible pixels, no ghost, no spy
pump(alice, 0.5)
known = set(alice.entities)
ok(a_pixel in known and plain in known and walker in known, "Alice's client knows her pixel, Bob's ordinary pixel and the walker")
ok(ghost not in known and spy not in known, "and not the invisible pixel or the spy")
ok(alice.pixel_stats["unknown"] == 0 and alice.pixel_stats["skipped"] == 0, "no update or leave for a pixel her client did not have")

for client in (alice, bob):
    client.close()

print(f"all {checks} checks passed")