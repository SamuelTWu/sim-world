"""Starts the game server as a background process on this machine, for single player.

    local = LocalServer(seed=None)
    local.start()                         # returns immediately
    ...                                   # each frame: local.state is SERVER_STARTING, then SERVER_READY (or a failure)
    client = Client(local.url, "player")  # connect like any other client
    ...
    local.stop()

The server listens on 127.0.0.1 only. It runs in its own process so it generates the world in parallel with
the client, never competes with the game for the interpreter lock, and a server crash cannot take the game down.
The server also exits on its own if the game dies, because it watches the pipe the launcher keeps open.
"""
import atexit
import collections
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

from .server import READY_MARKER

ROOT = Path(__file__).resolve().parents[1]

SERVER_STARTING = "starting"
SERVER_READY = "ready"
SERVER_FAILED = "failed"
SERVER_EXITED = "exited"
SERVER_STOPPED = "stopped"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LocalServer:
    def __init__(self, seed=None, size=None, max_players=4):
        self.seed = seed
        self.size = size
        self.max_players = max_players
        self.port = None
        self.process = None
        self.state = None
        self.error = None
        self.stopping = False
        self.log = collections.deque(maxlen=30)

    @property
    def url(self):
        return f"ws://127.0.0.1:{self.port}"

    def start(self):
        self.port = free_port()
        command = [sys.executable, "-m", "server.server", "--host", "127.0.0.1", "--port", str(self.port), "--max-players", str(self.max_players), "--watch-stdin",]

        if self.seed is not None:
            command += ["--seed", str(self.seed)]

        if self.size is not None:
            command += ["--size", str(self.size)]

        self.state = SERVER_STARTING
        self.process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"}, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self.pump, name="local-server-log", daemon=True).start()
        atexit.register(self.stop)

    def pump(self):
        for line in self.process.stdout:
            self.log.append(line.rstrip())
            print(line, end="", flush=True)

            if READY_MARKER in line and self.state == SERVER_STARTING:
                self.state = SERVER_READY

        code = self.process.wait()
        tail = " | ".join(list(self.log)[-3:])

        if self.stopping:
            self.state = SERVER_STOPPED
        elif self.state == SERVER_STARTING:
            self.error = f"the server exited with code {code} before it was ready. Last output: {tail}"
            self.state = SERVER_FAILED
        else:
            self.error = f"the server exited unexpectedly (code {code}). Last output: {tail}"
            self.state = SERVER_EXITED

    def stop(self):
        if self.process is None or self.stopping:
            return

        self.stopping = True

        try:
            self.process.stdin.close()
        except OSError:
            pass

        try:
            self.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            self.process.terminate()

            try:
                self.process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.process.kill()

        atexit.unregister(self.stop)