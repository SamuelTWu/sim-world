import asyncio
from dataclasses import asdict

from websockets.asyncio.client import connect

from src.simworld.sim.simulation import Simulation
from src.simworld.world.generator import GenerationSettings
from src.simworld.shared import protocol as proto
from src.simworld.server.server import Server
from src.simworld.server.replication.worldsync import generate_world

PORT = 8798
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


def names(world):
    return [[tile.name for tile in row] for row in world.tiles]


async def main():
    sim = Simulation(GenerationSettings(width=80, height=80, seed=7, mode="sandbox"))
    sim.start_new_game(7)
    ok(sim.world.width != 80 or sim.world.height != 80, "the sandbox ignores the width and height settings")
    server_task = asyncio.create_task(Server(sim, "127.0.0.1", PORT, max_players=2).run())

    alice = await open_client()
    await alice.send(proto.encode(proto.join("alice")))
    welcome = await receive(alice)
    ok(welcome["type"] == proto.WELCOME, "alice gets a welcome")
    ok(welcome["settings"]["mode"] == "sandbox", "the welcome message carries the mode")
    ok(welcome["checksum"] == sim.world.generation_checksum, "the welcome checksum is the server world's")

    generator, world = generate_world(welcome)
    ok(world.generation_checksum == welcome["checksum"], "the client's own world has the server's checksum")
    ok((world.width, world.height) == (sim.world.width, sim.world.height), "the client world has the server's size")
    ok(names(world) == names(sim.world), "every tile name is the same, cell by cell")
    ok(world.labels == sim.world.labels and len(world.labels) > 0, "the labels are the same")
    ok(world.recording is False, "the client world does not record changes")

    without_mode = {**welcome, "settings": {key: value for key, value in welcome["settings"].items() if key != "mode"}}
    other_generator, other = generate_world(without_mode)
    ok(other.generation_checksum != welcome["checksum"], "a client that ignored the mode would build a different world, so the checksum catches it")

    bob = await open_client()
    await bob.send(proto.encode(proto.join("bob")))
    second = await receive(bob)
    ok(generate_world(second)[1].generation_checksum == welcome["checksum"], "a second client gets the same world")

    for ws in (alice, bob):
        await ws.close()

    server_task.cancel()
    print(f"sandbox sync OK ({checks} checks)")


asyncio.run(main())