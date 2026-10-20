import subprocess
import sys
import time

from src.simworld.client.net.connection import READY, Client
from src.simworld.server import local
from src.simworld.server.local import SERVER_FAILED, SERVER_READY, SERVER_STOPPED, LocalServer
from src.simworld.world.sandbox import tile_blocks

failures = 0


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


class FakePipe:
    def close(self):
        pass


class FakeProcess:
    def __init__(self, command, **kwargs):
        FakeProcess.commands.append(list(command))
        self.stdin = FakePipe()
        self.stdout = iter(())
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


FakeProcess.commands = []


def commands_for(**options):
    real = subprocess.Popen
    local.subprocess.Popen = FakeProcess
    FakeProcess.commands.clear()

    try:
        server = LocalServer(**options)
        server.start()
        time.sleep(0.05)
        server.stop()
    finally:
        local.subprocess.Popen = real

    return FakeProcess.commands[-1]


def without_port(command):
    if "--port" not in command:
        return list(command)

    at = command.index("--port")
    return command[:at] + command[at + 2:]


plain = commands_for()
sandbox = commands_for(sandbox=True)
check("singleplayer has no --sandbox", "--sandbox" not in plain)
check("sandbox adds --sandbox exactly once", sandbox.count("--sandbox") == 1)
check("nothing else changes: the commands differ only by that flag", [part for part in without_port(sandbox) if part != "--sandbox"] == without_port(plain))
check("sandbox=False is the same as leaving it out", without_port(commands_for(sandbox=False)) == without_port(plain))
check("the other options still work with sandbox", "--seed" in commands_for(sandbox=True, seed=5) and "--max-players" in commands_for(sandbox=True))
check("sandbox is remembered on the object", LocalServer(sandbox=True).sandbox is True and LocalServer().sandbox is False)


def wait_ready(server, seconds=90):
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline and server.state not in (SERVER_READY, SERVER_FAILED):
        time.sleep(0.1)

    return server.state


def join(url):
    client = Client(url, "tester", timeout=30)
    client.start()
    client.wait()
    return client


sandbox_server = LocalServer(sandbox=True)
sandbox_server.start()

try:
    state = wait_ready(sandbox_server)
    check("a local sandbox server becomes ready", state == SERVER_READY, f"{state}: {sandbox_server.error}")

    if state == SERVER_READY:
        client = join(sandbox_server.url)
        check("a client reaches READY", client.state == READY, f"{client.state}: {client.error}")

        if client.state == READY:
            check("the world is the sandbox, with seed 0", client.welcome["settings"].get("mode") == "sandbox" and client.welcome["seed"] == 0)
            check("the client rebuilt the same world, labels included", len(client.world.labels) == len(tile_blocks()) and client.world.generation_checksum == client.welcome["checksum"])

        client.close()
finally:
    sandbox_server.stop()

check("the sandbox server stops", sandbox_server.state == SERVER_STOPPED, str(sandbox_server.state))

normal_server = LocalServer(size=100)
normal_server.start()

try:
    state = wait_ready(normal_server)
    check("a local singleplayer server still becomes ready", state == SERVER_READY, f"{state}: {normal_server.error}")

    if state == SERVER_READY:
        client = join(normal_server.url)
        check("singleplayer is unchanged: a normal 100x100 world with no labels", client.state == READY and client.welcome["settings"].get("mode", "normal") == "normal" and (client.world.width, client.world.height) == (100, 100) and client.world.labels == [], f"{client.state}: {client.error}")
        client.close()
finally:
    normal_server.stop()

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)