"""README 8.4: a client that lost its connection rejoins with its player id and gets a fresh welcome plus the nearby state.

A real server and real clients over websockets. Alice and Bob each place a pixel next to each other. Alice's connection is cut; while she
is away a tile near her is changed. Her client then calls reconnect(): she is the same player (same id, same token, her pixel is still hers),
she gets a new welcome, her own pixel, Bob's nearby pixel and the changed tile again from scratch. Then the failure cases: a wrong token, an
unknown player, someone using Alice's id without her token, a rejoin while the old connection is still registered (it is replaced, and its late
disconnect does not throw the new one out), and a rejoin when the server filled up meanwhile. Run from the folder that contains game/ and server/.
"""
import asyncio
import threading
import time

from src.simworld.sim.simulation import Simulation
from src.simworld.world.generator import GenerationSettings
from src.simworld.shared import protocol as proto
from src.simworld.client.net.connection import CLOSED, FAILED, READY, Client
from src.simworld.server.server import Server

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
            return client

        time.sleep(0.1)

    raise RuntimeError("server did not start")


def pump(client, seconds):
    deadline = time.monotonic() + seconds
    replies = []

    while time.monotonic() < deadline:
        replies.extend(client.poll())
        time.sleep(0.02)

    return replies


def wait_for(condition, seconds=5):
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        if condition():
            return True

        time.sleep(0.02)

    return condition()


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


def rejoin_attempt(player_id, token):
    """A brand new Client that claims to be `player_id`. Returns it after the join finished."""
    client = Client(URL, "someone", timeout=5)
    client.session = (player_id, token)
    client.start()
    client.wait(15)
    return client


sim = Simulation(GenerationSettings(width=200, height=200, seed=11))
sim.start_new_game(11)
factory = sim.entity_manager.entity_factory
placeable = [path.stem for path in sorted(factory.definitions_path.glob("*.json")) if factory.load_definition(path.stem).get("placeable", True) is not False and path.stem != "resource_pile"]
BLUEPRINT = next((name for name in ("runner", "commander", "swimmer") if name in placeable), placeable[0] if placeable else None)
ok(BLUEPRINT is not None, "there is a placeable blueprint to test with")
server = Server(sim, "127.0.0.1", PORT, max_players=3)
loop = asyncio.new_event_loop()
threading.Thread(target=lambda: loop.run_until_complete(server.run()), daemon=True).start()

alice, bob = join("alice"), join("bob")
ok(alice.state == READY and bob.state == READY, "alice and bob joined")
ok(alice.session is not None and alice.session[0] == alice.player_id and alice.session[1] == alice.welcome["token"], "alice remembers her player id and token")
ok(len(alice.welcome["token"]) >= 16 and alice.welcome["token"] != bob.welcome["token"], "tokens are long and different per player")
ok("resumed" not in alice.welcome, "a first join is not marked resumed")
alice_id, token, first_tick = alice.player_id, alice.session[1], alice.welcome["tick"]

a_pixel = place(alice, 100, 100)
b_pixel = place(bob, 102, 100)
pump(alice, 0.5)
pump(bob, 0.2)
ok(a_pixel in alice.entities and b_pixel in alice.entities, "before the drop alice knows her pixel and bob's")

# ---- the connection drops
alice.ws.close()
ok(wait_for(lambda: alice.state == CLOSED), "alice's client notices the lost connection")
ok(wait_for(lambda: alice_id not in server.players), "the server removes her from its player table")
ok(sim.entity_manager.get(a_pixel) is not None and sim.entity_manager.get(a_pixel).owner == alice_id, "her pixel stays in the world, still hers")

# ---- while she is away a tile near her changes
changed = (101, 101)
before = sim.world.get_tile(*changed)
after = next(tile for row in sim.world.tiles for tile in row if tile.name != before.name)
loop.call_soon_threadsafe(lambda: sim.world.set_tile(*changed, after))
time.sleep(0.4)

# ---- she comes back
stale_entities = alice.entities
alice.reconnect()
ok(alice.wait(30) and alice.state == READY, f"reconnect reaches READY: {alice.error}")
ok(alice.player_id == alice_id, "same player id")
ok(alice.welcome["token"] == token and alice.session == (alice_id, token), "same token")
ok(alice.welcome.get("resumed") is True, "the welcome says it answers a rejoin")
ok(alice.welcome["tick"] > first_tick and alice.welcome["checksum"] == sim.world.generation_checksum, "a fresh welcome: current tick, same world")
ok(alice.entities is not stale_entities, "the client started over with an empty pixel dict")
pump(alice, 1.0)
ok(a_pixel in alice.entities and alice.entities[a_pixel].owner == alice_id, "her own pixel is sent again")
ok(b_pixel in alice.entities, "bob's nearby pixel is sent again")
ok(alice.world.get_tile(*changed).name == after.name, "the tile that changed while she was away is in her new world")
ok(alice.pixel_stats["unknown"] == 0 and alice.pixel_stats["entered"] >= 2, "no update arrived for a pixel she was not told about")
ok(alice_id in server.players and len(server.players) == 2, "the server has her again, once")

seq = alice.command("inspect", {"id": a_pixel})
reply = next((m for m in pump(alice, 1.0) if m.get("seq") == seq), None)
ok(reply is not None and reply["type"] == proto.ENTITY_INFO, f"she can command her pixel again: {reply}")

# ---- ids are not reused, and other players are unaffected
bob_pixels = {i for i in bob.entities}
pump(bob, 0.3)
ok(bob.state == READY and b_pixel in bob.entities and bob_pixels <= set(bob.entities), "bob was not disturbed")

# ---- wrong token, unknown player, id without token
bad = rejoin_attempt(alice_id, "0" * 32)
ok(bad.state == FAILED and "unknown_session" in bad.error and bad.session is None, f"wrong token is refused: {bad.error}")
ok(bad.player_id is None and len(server.players) == 2 and server.players[alice_id].websocket is not None, "the refused attempt did not touch her session")
ghost = rejoin_attempt(99, "0" * 32)
ok(ghost.state == FAILED and "unknown_session" in ghost.error, f"an unknown player id is refused: {ghost.error}")
thief = Client(URL, "thief", timeout=5)
thief.session = (alice_id, "")
thief.start()
thief.wait(15)
ok(thief.state == FAILED and "unknown_session" in thief.error, "using her id without her token is refused")
pump(alice, 0.3)
ok(alice.state == READY and alice_id in server.players, "alice is still connected after all of that")

# ---- a rejoin while the old connection is still registered replaces it
twin = rejoin_attempt(alice_id, token)
ok(twin.state == READY and twin.player_id == alice_id, f"a rejoin works while the old connection is still up: {twin.error}")
ok(wait_for(lambda: alice.state == CLOSED), "the old connection was closed")
time.sleep(0.5)  # the old connection's late disconnect has been processed by now
ok(server.players.get(alice_id) is not None and len(server.players) == 2, "the old connection's disconnect did not remove the new one")
pump(twin, 1.0)
seq = twin.command("inspect", {"id": a_pixel})
reply = next((m for m in pump(twin, 1.0) if m.get("seq") == seq), None)
ok(reply is not None and reply["type"] == proto.ENTITY_INFO, "the new connection controls her pixel")

# ---- a brand new player gets a new id, never alice's
carol = join("carol")
ok(carol.state == READY and carol.player_id not in (alice_id, bob.player_id), "a new player gets a new id")

# ---- the server fills up while she is away: she is told so and keeps her session
twin.ws.close()
ok(wait_for(lambda: alice_id not in server.players), "twin dropped")
dave = join("dave")
ok(dave.state == READY and len(server.players) == 3, "someone else took the free slot")
late = Client(URL, "alice", timeout=5)
late.session = (alice_id, token)
late.start()
late.wait(15)
ok(late.state == FAILED and "server_full" in late.error and late.session == (alice_id, token), f"rejoin is refused while the server is full and the session is kept: {late.error}")
dave.close()
ok(wait_for(lambda: len(server.players) == 2), "dave left")
late.reconnect()
ok(late.wait(30) and late.player_id == alice_id, f"alice gets back in once there is room: {late.error}")

# ---- reconnect() misuse
try:
    bob.reconnect()
    ok(False, "reconnect on a live client must raise")
except RuntimeError:
    ok(True, "reconnect on a live client raises")

try:
    Client(URL).reconnect()
    ok(False, "reconnect on a client that never joined must raise")
except RuntimeError:
    ok(True, "reconnect on a client that never joined raises")

for client in (alice, bob, carol, twin, late, bad, ghost, thief):
    client.close()

print(f"all {checks} checks passed")