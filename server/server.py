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
import os
import sys
import threading
import time
from collections import namedtuple
from dataclasses import asdict, dataclass, field

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from game.command import command as commands
from game.simulation import TICK_DT, TICK_RATE
from . import protocol as proto
from . import replication
from game.command.visibility import can_see
from .interest import MAX_VIEW_TILES, SpatialGrid, clean_view, visible_ids
from .chunksync import ChunkSync, batches, wanted_chunks
from game.entity.system.simContext import TILE_UNITS

READY_MARKER = "[server] ready"
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
    known: dict = field(default_factory=dict)
    chunks: ChunkSync = field(default_factory=ChunkSync)
    view: tuple | None = None
    visible: set = field(default_factory=set)
    keep: set = field(default_factory=set)


def clean_name(name):
    return "".join(char for char in name if char.isprintable()).strip()[:MAX_NAME_LENGTH]


MAX_RESULT_ITEMS = 256
VIEW_MARGIN_TILES = 2
LEAVE_EXTRA_TILES = 2  # a pixel enters at the edge of the visible area but only leaves this much further out (7.4)
MAX_NOTICES_PER_TICK = 32


class Server:
    def __init__(self, sim, host=DEFAULT_HOST, port=DEFAULT_PORT, max_players=MAX_PLAYERS):
        self.sim = sim
        self.host = host
        self.port = port
        self.max_players = max_players
        self.inbox = asyncio.Queue()
        commands.load_commands()
        self.commands = commands.CommandContext(sim)
        self.players = {}
        self.grid = SpatialGrid(TILE_UNITS)
        self.next_player_id = 1
        self.tasks = set()

    async def run(self):
        async with serve(self.handle_connection, self.host, self.port, max_size=proto.MAX_MESSAGE_BYTES, compression=None):
            print(f"[server] ws://{self.host}:{self.port} | seed {self.sim.seed} | {TICK_RATE} Hz | up to {self.max_players} players")
            print(READY_MARKER, flush=True)
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
            self.grid.sync(self.sim.entity_manager.all())
            self.send_order_notices()
            self.replicate()
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

    def send_order_notices(self):
        """Tell the player whose order a pixel gave up on (orders.py queues these). The command was accepted earlier; this is the later bad news."""
        notices = getattr(self.sim.systems, "order_notices", None)

        if not notices:
            return

        pending, notices[:] = list(notices), []

        for notice in pending[:MAX_NOTICES_PER_TICK]:
            client = self.players.get(notice["issuer"])

            if client is not None and not client.closing:
                self.send(client, proto.order_failed(notice["id"], notice["kind"], notice["reason"]))

    def replicate(self):
        """Tell each player what changed about the pixels they can see (see replication.py). Silent when nothing changed."""
        for client in self.players.values():
            if client.closing:
                continue

            self.send_terrain(client)
            enter, update, leave = replication.diff(client.known, self.compute_visible(client), self.seen_by(client), client.keep)

            if enter or update or leave:
                self.send(client, proto.tick_update(self.sim.tick, enter, update, leave))

    def send_terrain(self, client):
        """Send tile changes the player has not got: whole logs of chunks that just became near one of their pixels, and new changes in chunks they already have (see chunksync.py)."""
        world = self.sim.world
        points = []

        for entity_id in self.sim.owned_ids(client.player_id):
            entity = self.commands.get_entity(entity_id)

            if entity is not None and entity.alive:
                points.append((entity.position.x, entity.position.y))

        wanted = wanted_chunks(points, TILE_UNITS, world.width, world.height)

        for tiles in batches(client.chunks.update(wanted, world.deltas)):
            self.send(client, proto.world_delta(self.sim.tick, [list(tile) for tile in tiles]))

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
        elif message["type"] == proto.VIEW:
            self.handle_view(client, message)
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

    def handle_view(self, client, message):
        """Remember the part of the world the player's camera shows. A bad rectangle is ignored (the old one stays)."""
        world = self.sim.world
        rect = clean_view(message["rect"], world.width * TILE_UNITS, world.height * TILE_UNITS, MAX_VIEW_TILES * TILE_UNITS)

        if rect is None:
            self.send(client, proto.error(proto.BAD_MESSAGE, "view must be [x0, y0, x1, y1] numbers"))
        else:
            client.view = rect

    def seen_by(self, client):
        """A lookup for replication.diff that returns only pixels this player may be told about (command/visibility.py).

        Everything sent about pixels goes through it, so invisible pixels and spies are never in `enter` or `update` for an enemy,
        and one that turns invisible mid-game simply `leave`s.
        """
        player_id = client.player_id
        get_entity = self.commands.get_entity

        def lookup(entity_id):
            entity = get_entity(entity_id)
            return entity if entity is not None and can_see(player_id, entity) else None

        return lookup

    def compute_visible(self, client):
        """Fills client.visible (pixels near their own pixels or in their camera: what may ENTER) and client.keep (the same area a little bigger: what stays), see interest.py. Returns visible."""
        own = []

        for entity_id in self.sim.owned_ids(client.player_id):
            entity = self.commands.get_entity(entity_id)

            if entity is not None and entity.alive:
                own.append((entity_id, entity.position.x, entity.position.y))

        margin = VIEW_MARGIN_TILES * TILE_UNITS
        client.visible = visible_ids(self.grid, own, client.view, margin=margin)
        client.keep = visible_ids(self.grid, own, client.view, margin=margin, extra=LEAVE_EXTRA_TILES * TILE_UNITS)
        return client.visible

    def handle_command(self, client, message):
        outcome = commands.execute(self.commands, client.player_id, message["name"], message["args"])

        if not outcome.ok:
            self.send(client, proto.error(proto.COMMAND_REJECTED, outcome.reason, seq=message["seq"]))
        elif outcome.info is not None:
            self.send(client, proto.entity_info(outcome.info["id"], outcome.info, seq=message["seq"]))
        else:
            ignored = [[entity_id, reason] for entity_id, reason in list(outcome.ignored.items())[:MAX_RESULT_ITEMS]]
            self.send(client, proto.command_result(message["seq"], outcome.applied[:MAX_RESULT_ITEMS], ignored))

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


def exit_when_stdin_closes():
    """Used by the single-player launcher: when the game closes or crashes, the pipe closes and the server exits."""

    def watch():
        sys.stdin.read()

        try:
            print("[server] launcher closed the pipe, shutting down", flush=True)
        finally:
            os._exit(0)

    threading.Thread(target=watch, name="stdin-watch", daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="Sim World server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="use 0.0.0.0 to accept connections from other machines")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--size", type=int, default=None, help="world width and height in tiles (default: the Simulation default)")
    parser.add_argument("--max-players", type=int, default=MAX_PLAYERS)
    parser.add_argument("--watch-stdin", action="store_true", help="exit when stdin closes (used by the single-player launcher)")
    args = parser.parse_args()

    if args.watch_stdin:
        exit_when_stdin_closes()

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