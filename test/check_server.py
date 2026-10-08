import asyncio

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from game.simulation import Simulation, TICK_RATE
from game.world.generator import GenerationSettings
from ..server.server import protocol as proto
from ..server.server import Server

PORT = 8799
URL = f"ws://127.0.0.1:{PORT}"
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


async def open_client():
    for _ in range(50):
        try:
            return await connect(URL)
        except OSError:
            await asyncio.sleep(0.1)

    raise RuntimeError("server did not start")


async def receive(ws):
    return proto.decode(await asyncio.wait_for(ws.recv(), 5), proto.SERVER_TYPES)


async def closed(ws):
    try:
        await asyncio.wait_for(ws.recv(), 5)
    except ConnectionClosed:
        return True

    return False


async def main():
    sim = Simulation(GenerationSettings(width=80, height=80, seed=7, tag_modifiers={"all": {"scale": 1.3}}))
    sim.start_new_game(7)
    server_task = asyncio.create_task(Server(sim, "127.0.0.1", PORT, max_players=2).run())

    alice = await open_client()
    await alice.send(proto.encode(proto.join("alice")))
    welcome = await receive(alice)
    ok(welcome["type"] == proto.WELCOME and welcome["player_id"] == 1, "alice gets player id 1")
    ok(welcome["seed"] == 7 and welcome["checksum"] == sim.world.generation_checksum, "seed and checksum match the server world")
    ok(welcome["settings"]["width"] == 80 and welcome["tick_rate"] == TICK_RATE, "settings and tick rate")

    await alice.send(proto.encode(proto.command(5, "move", {"ids": [1], "target": [0, 0]})))
    reply = await receive(alice)
    ok(reply["type"] == proto.ERROR and reply["code"] == proto.COMMAND_REJECTED and reply["seq"] == 5, "commands are rejected for now")

    bob = await open_client()
    await bob.send(proto.encode(proto.join("bob")))
    ok((await receive(bob))["player_id"] == 2, "bob gets player id 2")

    carol = await open_client()
    await carol.send(proto.encode(proto.join("carol")))
    ok((await receive(carol))["code"] == proto.SERVER_FULL and await closed(carol), "third player is turned away")

    old = await open_client()
    await old.send(proto.encode({"type": "join", "name": "old", "protocol": 999}))
    ok((await receive(old))["code"] == proto.BAD_PROTOCOL and await closed(old), "wrong protocol version is rejected")

    early = await open_client()
    await early.send(proto.encode(proto.command(1, "move")))
    ok((await receive(early))["code"] == proto.NOT_JOINED and await closed(early), "command before join is rejected")

    text = await open_client()
    await text.send("hello")
    ok((await receive(text))["code"] == proto.BAD_MESSAGE and await closed(text), "text frames are rejected")

    start = sim.tick
    await asyncio.sleep(1.0)
    ok(TICK_RATE * 0.5 <= sim.tick - start <= TICK_RATE * 1.5, f"ticks advance at about {TICK_RATE} Hz (got {sim.tick - start} in 1 s)")

    await alice.close()
    await asyncio.sleep(0.3)
    dave = await open_client()
    await dave.send(proto.encode(proto.join("dave")))
    ok((await receive(dave))["player_id"] == 3, "a freed slot can be reused (ids are never reused)")

    for ws in (bob, dave):
        await ws.close()

    server_task.cancel()
    print(f"server OK ({checks} checks)")


asyncio.run(main())