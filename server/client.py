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

from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
from websockets.sync.client import connect

from . import protocol as proto
from .replica import View, apply_tick_update

DEFAULT_URL = "ws://127.0.0.1:8765"

IDLE = "idle"
CONNECTING = "connecting"
GENERATING = "generating"
READY = "ready"
FAILED = "failed"
CLOSED = "closed"


class Client:
    def __init__(self, url=DEFAULT_URL, name="player", timeout=10.0, world_builder=None):
        self.url = url
        self.name = name
        self.timeout = timeout
        self.world_builder = world_builder
        self.state = IDLE
        self.error = None
        self.welcome = None
        self.generator = None
        self.world = None
        self.entities = {}
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

    def wait(self, timeout=None):
        """Block until the join finished. Returns True if the client is READY; otherwise see .error."""
        self.done.wait(timeout)
        return self.state == READY

    def view(self):
        """A read-only snapshot for the renderer. Only valid once the client is READY."""
        if self.state != READY:
            raise RuntimeError("the client has no world yet")

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
                apply_tick_update(self.entities, message)

            messages.append(message)

    def send(self, message):
        """Send a protocol message. Returns False if the connection is not usable."""
        if self.state != READY:
            return False

        try:
            self.ws.send(proto.encode(message))
        except ConnectionClosed:
            return False

        return True

    def command(self, name, args=None):
        """Send a command with the next sequence number. Returns the seq, or None if it was not sent."""
        self.seq += 1
        return self.seq if self.send(proto.command(self.seq, name, args)) else None

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
            from .worldsync import generate_world as build

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

            self.ws.send(proto.encode(proto.join(self.name)))
            first = self.receive(self.timeout)

            if first["type"] == proto.ERROR:
                self.finish(FAILED, f"server refused the join: {first['message']} ({first['code']})")
                return

            if first["type"] != proto.WELCOME:
                self.finish(FAILED, f"expected welcome, got {first['type']}")
                return

            self.welcome = first
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
                self.inbox.put(self.receive())
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