"""Authoritative game server.

One asyncio event loop with two kinds of tasks:
- one tick loop: drains the inbox, applies messages, then runs Simulation.step() at TICK_RATE
- one handler per connection: reads frames, validates them, and pushes them into the inbox

Only the tick loop touches the simulation and the player table. A handler only touches its own
Client, the inbox, and its own websocket. Sending is queued per client, so a slow client can
never stall the tick loop.

Run from the project root:
    python -m server.server [--host 0.0.0.0] [--port 8765] [--seed N] [--max-players N]
"""
import argparse
import asyncio
import time
from collections import namedtuple
from dataclasses import asdict, dataclass, field

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from ..simulation import TICK_DT, TICK_RATE
from . import protocol as proto

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_PLAYERS = 16
MAX_NAME_LENGTH = 24
JOIN_TIMEOUT = 10.0
CLOSE_TIMEOUT = 2.0
MAX_PENDING = 200
OUTBOX_MAX = 256
MAX_BEHIND = 0.25
LOG_INTERVAL = 10.0

POLICY_VIOLATION = 1008
TRY_AGAIN_LATER = 1013

Close = namedtuple("Close", "code reason")


@dataclass(eq=False)
class Client:
    websocket: object
    player_id: int | None = None
    name: str = ""
    pending: int = 0
    closing: bool = False
    outbox: asyncio.Queue = field(default_factory=asyncio.Queue)


def clean_name(name):
    return "".join(char for char in name if char.isprintable()).strip()[:MAX_NAME_LENGTH]


class Server:
    def __init__(self, sim, host=DEFAULT_HOST, port=DEFAULT_PORT, max_players=MAX_PLAYERS):
        self.sim = sim
        self.host = host
        self.port = port
        self.max_players = max_players
        self.inbox = asyncio.Queue()
        self.players = {}
        self.next_player_id = 1
        self.tasks = set()

    async def run(self):
        async with serve(self.handle_connection, self.host, self.port, max_size=proto.MAX_MESSAGE_BYTES, compression=None):
            print(f"[server] ws://{self.host}:{self.port} | seed {self.sim.seed} | {TICK_RATE} Hz | up to {self.max_players} players")
            await self.tick_loop()

    async def tick_loop(self):
        next_time = time.monotonic()
        window_start = next_time
        steps = 0
        total = longest = 0.0

        while True:
            started = time.monotonic()
            self.process_inbox()
            self.sim.step()
            elapsed = time.monotonic() - started

            steps += 1
            total += elapsed
            longest = max(longest, elapsed)

            now = time.monotonic()

            if now - window_start >= LOG_INTERVAL:
                print(f"[server] tick {self.sim.tick} | players {len(self.players)} | step avg {total / steps * 1000:.1f} ms, max {longest * 1000:.1f} ms (budget {TICK_DT * 1000:.0f} ms)")
                window_start, steps, total, longest = now, 0, 0.0, 0.0

            next_time += TICK_DT

            if now - next_time > MAX_BEHIND:
                next_time = now

            await asyncio.sleep(max(0.0, next_time - now))

    def process_inbox(self):
        while not self.inbox.empty():
            client, message = self.inbox.get_nowait()
            self.handle(client, message)

    def handle(self, client, message):
        if message is None:
            self.disconnect(client)
            return

        client.pending -= 1

        if client.closing:
            return

        if message["type"] == proto.JOIN:
            self.handle_join(client, message)
        elif client.player_id is None:
            self.reject(client, proto.NOT_JOINED, "send join first")
        else:
            self.handle_command(client, message)

    def handle_join(self, client, message):
        if client.player_id is not None:
            self.reject(client, proto.BAD_MESSAGE, "already joined")
        elif message["protocol"] != proto.PROTOCOL_VERSION:
            self.reject(client, proto.BAD_PROTOCOL, f"server speaks protocol {proto.PROTOCOL_VERSION}, you sent {message['protocol']}")
        elif len(self.players) >= self.max_players:
            self.reject(client, proto.SERVER_FULL, f"server is full ({self.max_players} players)", TRY_AGAIN_LATER)
        else:
            client.player_id = self.next_player_id
            self.next_player_id += 1
            client.name = clean_name(message["name"]) or f"player{client.player_id}"
            self.players[client.player_id] = client
            self.send(client, proto.welcome(client.player_id, self.sim.seed, asdict(self.sim.generation_settings), self.sim.world.generation_checksum, self.sim.tick, TICK_RATE))
            print(f"[server] player {client.player_id} '{client.name}' joined ({len(self.players)}/{self.max_players})")

    def handle_command(self, client, message):
        self.send(client, proto.error(proto.COMMAND_REJECTED, "commands are not implemented yet", seq=message["seq"]))

    def disconnect(self, client):
        client.closing = True

        if client.player_id is not None and self.players.pop(client.player_id, None) is not None:
            print(f"[server] player {client.player_id} '{client.name}' left ({len(self.players)}/{self.max_players})")

    def send(self, client, message):
        if client.closing:
            return

        if client.outbox.qsize() >= OUTBOX_MAX:
            self.drop(client, "too slow", TRY_AGAIN_LATER)
            return

        client.outbox.put_nowait(proto.encode(message))

    def reject(self, client, code, text, close_code=POLICY_VIOLATION):
        if client.closing:
            return

        client.closing = True
        client.outbox.put_nowait(proto.encode(proto.error(code, text)))
        client.outbox.put_nowait(Close(close_code, code))

    def drop(self, client, reason, close_code):
        if client.closing:
            return

        client.closing = True
        self.spawn(client.websocket.close(close_code, reason))

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def receive(self, client, raw):
        if client.closing:
            return

        try:
            message = proto.decode(raw, accept=proto.CLIENT_TYPES)
        except proto.ProtocolError as problem:
            self.reject(client, proto.BAD_MESSAGE, str(problem))
            return

        if client.pending >= MAX_PENDING:
            self.drop(client, "too many messages", POLICY_VIOLATION)
            return

        client.pending += 1
        self.inbox.put_nowait((client, message))

    async def handle_connection(self, websocket):
        client = Client(websocket)
        sender = asyncio.create_task(self.send_loop(client))

        try:
            self.receive(client, await asyncio.wait_for(websocket.recv(), JOIN_TIMEOUT))

            async for raw in websocket:
                self.receive(client, raw)
        except asyncio.TimeoutError:
            self.reject(client, proto.NOT_JOINED, f"send join within {JOIN_TIMEOUT:.0f} seconds")
        except ConnectionClosed:
            pass
        finally:
            self.inbox.put_nowait((client, None))

            if client.closing and not sender.done():
                await asyncio.wait({sender}, timeout=CLOSE_TIMEOUT)

            sender.cancel()

    async def send_loop(self, client):
        try:
            while True:
                item = await client.outbox.get()

                if isinstance(item, Close):
                    await client.websocket.close(item.code, item.reason)
                    return

                await client.websocket.send(item)
        except ConnectionClosed:
            pass


def main():
    parser = argparse.ArgumentParser(description="Sim World server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="use 0.0.0.0 to accept connections from other machines")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--size", type=int, default=None, help="world width and height in tiles (default: the Simulation default)")
    parser.add_argument("--max-players", type=int, default=MAX_PLAYERS)
    args = parser.parse_args()

    from game.simulation import Simulation

    print("[server] generating world...")
    sim = Simulation()

    if args.size:
        sim.generation_settings.width = sim.generation_settings.height = args.size

    sim.start_new_game(args.seed)

    try:
        asyncio.run(Server(sim, args.host, args.port, args.max_players).run())
    except KeyboardInterrupt:
        print("\n[server] stopped")


if __name__ == "__main__":
    main()