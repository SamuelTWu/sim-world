"""Network layer for the game client.

A background thread owns the socket, so the pygame loop never blocks on the network.
Use it like this:

    client = Client("ws://127.0.0.1:8765", name="sam")
    client.start()                  # returns immediately: connects, joins, generates the world, checks it

    # each frame
    if client.state in (CONNECTING, GENERATING):
        ...                         # show a loading screen
    elif client.state == READY:     # client.world and client.generator match the server's terrain
        for message in client.poll():
            ...                     # tick_update, world_delta, error
        renderer.render(client.view())  # the renderer only ever sees this snapshot
        client.command("move", {"ids": [1], "target": [320, 480]})
    elif client.state in (FAILED, CLOSED):
        print(client.error)

    client.close()

After the welcome arrives the client generates the world from the seed and settings, and compares its
checksum with the server's. If they differ it goes to FAILED with a clear error and never reaches READY.
Scripts can call client.wait() instead of polling the state. Generation can take a while on big worlds.
This file imports nothing from game/ (the world builder is loaded when it is needed).
"""
import queue
import threading
import time

from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
from websockets.sync.client import connect

from src.simworld.shared import protocol as proto
from .replica import ServerClock, decode_transient_events, Stats, View, apply_tick_update, apply_world_delta, smooth

DEFAULT_URL = "ws://127.0.0.1:8765"

IDLE = "idle"
CONNECTING = "connecting"
GENERATING = "generating"
READY = "ready"
FAILED = "failed"
CLOSED = "closed"


class Client:
    def __init__(self, url=DEFAULT_URL, name="player", timeout=10.0, world_builder=None, tile_lookup=None):
        self.url = url
        self.name = name
        self.timeout = timeout
        self.world_builder = world_builder
        self.tile_lookup = tile_lookup
        self.tiles = None
        self.changed_tiles = []
        self.skipped_deltas = 0
        self.state = IDLE
        self.error = None
        self.welcome = None
        self.session = None  # (player_id, token) from the first welcome: what reconnect() uses to take the same player back (8.4)
        self.generator = None
        self.world = None
        self.entities = {}  # the pixels this client knows, id -> ReplicatedEntity: added on enter, patched on update, removed on leave
        self.clock = None  # ServerClock, created once the welcome says the tick rate; used to draw pixels one tick behind (smooth movement)
        self.pending_transient_events = []  # transient events (shots, impacts) received but not yet due: they start when the pixels are drawn up to that moment
        self.pixel_stats = Stats()  # totals of what the server's tick_updates did to self.entities (unknown > 0 means a missed enter)
        self.inbox = queue.Queue()
        self.seq = 0
        self.ws = None
        self.thread = None
        self.closing = False
        self.done = threading.Event()

    @property
    def player_id(self):
        return self.welcome["player_id"] if self.welcome else None

    def start(self):
        if self.state != IDLE:
            raise RuntimeError("client was already started")

        self.state = CONNECTING
        self.thread = threading.Thread(target=self.run, name="client-network", daemon=True)
        self.thread.start()

    def reconnect(self):
        """Rejoin as the same player after the connection was lost (state CLOSED, or FAILED after having joined once). Returns immediately, like start().

        Everything the old connection taught the client (pixels, smoothing clock, pending events, world) is thrown away: the server sends a
        fresh welcome and then the terrain and pixels near the player again, and the world is generated again, because tile changes that
        happened while away in places that are no longer near would otherwise stay missing. If the server no longer knows the player
        (it restarted) the client goes to FAILED with code unknown_session and the session is forgotten: start a new Client to join as a new player.
        """
        if self.session is None:
            raise RuntimeError("nothing to reconnect to: this client never joined")

        if self.state not in (CLOSED, FAILED):
            raise RuntimeError("the client is still connected")

        if self.thread is not None:
            self.thread.join(timeout=2.0)

        self.closing = False
        self.error = None
        self.welcome = None
        self.generator = None
        self.world = None
        self.tiles = None
        self.changed_tiles = []
        self.skipped_deltas = 0
        self.entities = {}
        self.clock = None
        self.pending_transient_events = []
        self.pixel_stats = Stats()
        self.inbox = queue.Queue()
        self.done = threading.Event()
        self.state = CONNECTING
        self.thread = threading.Thread(target=self.run, name="client-network", daemon=True)
        self.thread.start()

    def wait(self, timeout=None):
        """Block until the join finished. Returns True if the client is READY; otherwise see .error."""
        self.done.wait(timeout)
        return self.state == READY

    def view(self):
        """A read-only snapshot for the renderer. Only valid once the client is READY."""
        if self.state != READY:
            raise RuntimeError("the client has no world yet")

        if self.clock is not None:
            render_time = self.clock.render_time(time.monotonic())

            if render_time is not None:
                smooth(self.entities.values(), render_time)

        return View(self.world, self.generator.maps, self.generator.features, list(self.entities.values()), self.player_id)

    def poll(self):
        """Return every server message received since the last call, oldest first. Never blocks.

        Pixel updates are applied to self.entities here, on the caller's thread, so the renderer never sees them change mid-frame.
        """
        messages = []

        while True:
            try:
                message = self.inbox.get_nowait()
            except queue.Empty:
                return messages

            if message["type"] == proto.TICK_UPDATE:
                self.pixel_stats.add(self.apply_pixels(message))

            elif message["type"] == proto.WORLD_DELTA:
                self.apply_delta(message)

            messages.append(message)

    def apply_pixels(self, message):
        """Apply a tick_update, stamped with the server time it belongs to so positions can be smoothed."""
        rate = (self.welcome or {}).get("tick_rate") or 0

        if rate <= 0:
            self.pending_transient_events.extend(decode_transient_events(message))
            return apply_tick_update(self.entities, message)

        if self.clock is None:
            self.clock = ServerClock(1.0 / rate)

        stamp = message["tick"] / rate
        self.clock.observe(stamp, message.get("_received", time.monotonic()))
        self.pending_transient_events.extend(decode_transient_events(message, stamp))
        del self.pending_transient_events[:-512]
        return apply_tick_update(self.entities, message, stamp, 1.0 / rate)

    def take_transient_events(self):
        """The transient events that are due now, as [{"kind", "type", "from", "to", "at"}], and forget them. The renderer animates them itself.

        Pixels are drawn one tick behind the newest data (smooth movement), so a transient event waits until the drawing has reached the moment it
        happened: a shot then leaves the shooter where the shooter is drawn.
        """
        if not self.pending_transient_events:
            return []

        render_time = self.clock.render_time(time.monotonic()) if self.clock is not None else None
        due = [event for event in self.pending_transient_events if event["at"] is None or render_time is None or event["at"] <= render_time]
        taken = {id(event) for event in due}
        self.pending_transient_events = [event for event in self.pending_transient_events if id(event) not in taken]
        return due

    def apply_delta(self, message):
        """Put a world_delta's tile changes onto the locally generated world and remember which tiles changed."""
        if self.tiles is None:
            lookup = self.tile_lookup

            if lookup is None:
                from ...server.replication.worldsync import tiles_by_name as lookup

            self.tiles = lookup()

        changed, skipped = apply_world_delta(self.world, message, self.tiles)
        self.changed_tiles.extend(changed)
        self.skipped_deltas += skipped

    def take_changed_tiles(self):
        """(x, y) of every tile changed by deltas since the last call, then forget them. A renderer that caches terrain redraws these."""
        changed, self.changed_tiles = self.changed_tiles, []
        return changed

    def send(self, message):
        """Send a protocol message. Returns False if the connection is not usable."""
        if self.state != READY:
            return False

        try:
            self.ws.send(proto.encode(message))
        except ConnectionClosed:
            return False

        return True

    def send_view(self, rect):
        """Tell the server which part of the world the camera shows, [x0, y0, x1, y1] in world units. Returns False if not sent."""
        return self.send(proto.view(rect))

    def command(self, name, args=None):
        """Send a command with the next sequence number. Returns the seq, or None if it was not sent."""
        self.seq += 1
        return self.seq if self.send(proto.command(self.seq, name, args)) else None

    def dev(self, what, args=None):
        self.seq += 1
        return self.seq if self.send(proto.dev(self.seq, what, args)) else None

    def close(self):
        self.closing = True

        if self.ws is not None:
            self.ws.close()

        if self.thread is not None:
            self.thread.join(timeout=2.0)

    def finish(self, state, error=None):
        self.error = error
        self.state = state
        self.done.set()

    def end(self, error):
        """The connection is over: a failed join if we never became READY, otherwise a closed session."""
        self.finish(FAILED if self.state in (CONNECTING, GENERATING) else CLOSED, error)

    def receive(self, timeout=None):
        return proto.decode(self.ws.recv(timeout=timeout), accept=proto.SERVER_TYPES)

    def sync_world(self, welcome):
        """Generate the world from the welcome message. Returns an error string, or None if it matches the server."""
        build = self.world_builder

        if build is None:
            from ...server.replication.worldsync import generate_world as build

        try:
            generator, world = build(welcome)
            local = world.generation_checksum
        except Exception as problem:
            return f"could not generate the world from the server's settings: {problem!r}"

        if local != welcome["checksum"]:
            settings = welcome["settings"]
            return (
                f"world mismatch: the server's terrain checksum is {welcome['checksum'][:12]} but this client generated {local[:12]} "
                f"(seed {welcome['seed']}, {settings.get('width')}x{settings.get('height')}). "
                "This client would show a different world than the server, so it refuses to continue. "
                "Make sure the client and the server run the same version of the game."
            )

        self.generator, self.world = generator, world
        return None

    def run(self):
        try:
            self.ws = connect(self.url, open_timeout=self.timeout, max_size=proto.MAX_MESSAGE_BYTES, compression=None)
        except (OSError, InvalidHandshake, InvalidURI) as problem:
            self.finish(FAILED, f"could not connect to {self.url}: {problem}")
            return

        try:
            if self.closing:
                self.finish(CLOSED)
                return

            join = proto.join(self.name, *self.session) if self.session else proto.join(self.name)
            self.ws.send(proto.encode(join))
            first = self.receive(self.timeout)

            if first["type"] == proto.ERROR:
                if first["code"] == proto.UNKNOWN_SESSION:
                    self.session = None

                self.finish(FAILED, f"server refused the join: {first['message']} ({first['code']})")
                return

            if first["type"] != proto.WELCOME:
                self.finish(FAILED, f"expected welcome, got {first['type']}")
                return

            self.welcome = first
            self.session = (first["player_id"], first["token"])
            self.state = GENERATING
            problem = self.sync_world(first)

            if problem:
                self.finish(FAILED, problem)
                return

            if self.closing:
                self.finish(CLOSED)
                return

            self.state = READY
            self.done.set()

            while True:
                message = self.receive()
                message["_received"] = time.monotonic()  # when it arrived, not when the game gets round to polling it (smooth movement uses this)
                self.inbox.put(message)
        except ConnectionClosed as closed:
            if self.closing:
                self.finish(CLOSED)
            else:
                frame = getattr(closed, "rcvd", None)
                self.end(f"server closed the connection ({frame.code} {frame.reason})" if frame else "connection lost")
        except TimeoutError:
            self.finish(FAILED, f"server did not answer the join within {self.timeout:.0f} seconds")
        except proto.ProtocolError as problem:
            self.end(f"bad message from server: {problem}")
        except Exception as problem:
            self.end(f"network error: {problem!r}")
        finally:
            self.ws.close()