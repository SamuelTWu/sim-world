"""Network layer for the game client.

A background thread owns the socket, so the pygame loop never blocks on the network.
Use it like this:

    client = Client("ws://127.0.0.1:8765", name="sam")
    client.start()                  # returns immediately; connects and sends join in the background

    # each frame
    if client.state == READY:       # welcome received (client.welcome has the seed, settings, checksum)
        for message in client.poll():
            ...                     # tick_update, world_delta, error
        client.command("move", {"ids": [1], "target": [320, 480]})
    elif client.state in (FAILED, CLOSED):
        print(client.error)

    client.close()

Scripts can call client.wait() instead of polling the state. This file imports nothing from game/.
"""
import queue
import threading

from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
from websockets.sync.client import connect

from . import protocol as proto

DEFAULT_URL = "ws://127.0.0.1:8765"

IDLE = "idle"
CONNECTING = "connecting"
READY = "ready"
FAILED = "failed"
CLOSED = "closed"


class Client:
    def __init__(self, url=DEFAULT_URL, name="player", timeout=10.0):
        self.url = url
        self.name = name
        self.timeout = timeout
        self.state = IDLE
        self.error = None
        self.welcome = None
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
        """Block until the join finished. Returns True if the welcome arrived; otherwise see .error."""
        self.done.wait(timeout)
        return self.state == READY

    def poll(self):
        """Return every server message received since the last call, oldest first. Never blocks."""
        messages = []

        while True:
            try:
                messages.append(self.inbox.get_nowait())
            except queue.Empty:
                return messages

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
        """The connection is over: a failed join if the welcome never came, otherwise a closed session."""
        self.finish(FAILED if self.state == CONNECTING else CLOSED, error)

    def receive(self, timeout=None):
        return proto.decode(self.ws.recv(timeout=timeout), accept=proto.SERVER_TYPES)

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