import asyncio
import threading
import time

from game.simulation import Simulation, TICK_RATE
from game.world.generator import GenerationSettings
from game.server import protocol as proto
from game.server.client import CLOSED, FAILED, READY, Client
from game.server.server import Server

print("starting")

PORT = 8798
URL = f"ws://127.0.0.1:{PORT}"
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def join(name):
    for _ in range(50):
        client = Client(URL, name, timeout=5)
        client.start()

        if client.wait(10) or not (client.error or "").startswith("could not connect"):
            return client

        time.sleep(0.1)

    raise RuntimeError("server did not start")


def wait_for(client, kind, timeout=3.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        for message in client.poll():
            if message["type"] == kind:
                return message

        time.sleep(0.02)

    return None


sim = Simulation(GenerationSettings(width=80, height=80, seed=7, tag_modifiers={"all": {"scale": 1.3}}))
sim.start_new_game(7)
threading.Thread(target=lambda: asyncio.run(Server(sim, "127.0.0.1", PORT, max_players=1).run()), daemon=True).start()

alice = join("alice")
ok(alice.state == READY and alice.player_id == 1, "alice joins as player 1")
ok(alice.welcome["seed"] == 7 and alice.welcome["checksum"] == sim.world.generation_checksum, "welcome has the seed and the world checksum")
ok(alice.welcome["tick_rate"] == TICK_RATE and alice.welcome["settings"]["width"] == 80, "welcome has the tick rate and settings")

ok(alice.command("move", {"ids": [1], "target": [0, 0]}) == 1 and alice.command("move") == 2, "command sequence numbers count up")
reply = wait_for(alice, proto.ERROR)
ok(reply is not None and reply["code"] == proto.COMMAND_REJECTED and reply["seq"] == 1, "server replies to a command")

bob = join("bob")
ok(bob.state == FAILED and proto.SERVER_FULL in bob.error, f"a full server refuses the join ({bob.error})")

lost = Client("ws://127.0.0.1:1", "lost", timeout=2)
lost.start()
ok(not lost.wait(5) and lost.state == FAILED and lost.error.startswith("could not connect"), "an unreachable server fails cleanly")

alice.close()
ok(alice.state == CLOSED and alice.error is None and alice.send(proto.join("x")) is False, "close() ends the session without an error")

time.sleep(0.3)
carol = join("carol")
ok(carol.state == READY and carol.player_id == 2, "a freed slot can be reused")
carol.close()

print(f"client OK ({checks} checks)")