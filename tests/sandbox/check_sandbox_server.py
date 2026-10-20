import asyncio
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from websockets.asyncio.client import connect

from src.simworld.server.replication.worldsync import generate_world
from src.simworld.shared import protocol as proto
from src.simworld.sim.dev import sandbox_mode
from src.simworld.sim.dev.catalog import ENTITY, gallery_entries
from src.simworld.sim.dev.sandbox_mode import SANDBOX_SEED, populate_sandbox, prepare_sandbox
from src.simworld.sim.simulation import Simulation
from src.simworld.world.generator import GenerationSettings
from src.simworld.world.sandbox import ENTITY_CAPACITY, entity_slots, layout_for, tile_blocks

ROOT = Path(__file__).resolve().parents[2]
SERVER_MODULE = os.environ.get("SIMWORLD_SERVER_MODULE", "src.simworld.server.server")
UNITS = 32
failures = 0


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


def quiet(function, *args, **kwargs):
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


check("the sandbox seed is 0", SANDBOX_SEED == 0)
probe = SimpleNamespace(generation_settings=SimpleNamespace(mode="normal"))
check("no seed given: the sandbox seed is used", prepare_sandbox(probe, None) == 0 and probe.generation_settings.mode == "sandbox" and probe.sandbox is True)
check("an explicit seed is kept", prepare_sandbox(SimpleNamespace(generation_settings=SimpleNamespace(mode="normal")), 7) == 7)

normal = Simulation(GenerationSettings(width=60, height=60, seed=1))
normal.start_new_game(1)
check("a normal simulation is not a sandbox", getattr(normal, "sandbox", False) is False and normal.generation_settings.mode == "normal" and normal.world.labels == [])

sim = Simulation()
seed = prepare_sandbox(sim, None)
quiet(sim.start_new_game, seed)
check("the sandbox simulation builds a sandbox world", sim.generation_settings.mode == "sandbox" and sim.seed == 0 and len(sim.world.labels) == len(tile_blocks()) and sim.world.width >= 64)
check("the world has the layout's size, not the default 500x500", (sim.world.width, sim.world.height) == (layout_for(len(tile_blocks())).width, layout_for(len(tile_blocks())).height))

gallery = quiet(populate_sandbox, sim)
limits = sim.systems.limits
check("the limits are all off", limits.max_per_player == float("inf") and limits.max_in_world == float("inf") and limits.max_spawns == float("inf") and limits.max_spawns_per_owner == float("inf") and limits.max_thinks == 0)

entity_entries = [(kind, name) for kind, name, _ in gallery_entries() if kind == ENTITY]
placed = [entity for kind, _, entity, _, _ in gallery.placed if kind == ENTITY]
check("every entity blueprint in the catalog is placed", len(placed) == min(len(entity_entries), ENTITY_CAPACITY) and len(placed) > 0, f"{len(placed)} placed, {len(entity_entries)} in the catalog; skipped: {gallery.skipped}")
check("the gallery entities are in the world and frozen", all(entity.id in sim.systems.activity.frozen for entity in placed) and len(sim.entity_manager.all()) == len(gallery.placed))

kept = Simulation()
quiet(kept.start_new_game, prepare_sandbox(kept, None))
quiet(populate_sandbox, kept, max_world_pixels=10, max_thinks_per_tick=50)
check("an explicit --max option still wins over the sandbox default", kept.systems.limits.max_in_world == 10 and kept.systems.limits.max_thinks == 50 and kept.systems.limits.max_per_player == float("inf"))

again = Simulation()
quiet(again.start_new_game, prepare_sandbox(again, None))
quiet(populate_sandbox, again)
check("two sandbox simulations are identical", again.world.generation_checksum == sim.world.generation_checksum and [(e.id, e.position.x, e.position.y) for e in again.entity_manager.all()] == [(e.id, e.position.x, e.position.y) for e in sim.entity_manager.all()])


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port):
    process = subprocess.Popen([sys.executable, "-m", SERVER_MODULE, "--sandbox", "--port", str(port), "--stats-interval", "0"], cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line.rstrip()) for line in process.stdout] or lines.put(None), daemon=True).start()
    return process, lines


def wait_ready(process, lines, seconds=90):
    seen = []
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            continue

        if line is None:
            break

        seen.append(line)

        if line.startswith("[server] ready"):
            return True, seen

    return False, seen


async def play(port, expected_slots):
    for _ in range(50):
        try:
            ws = await connect(f"ws://127.0.0.1:{port}")
            break
        except OSError:
            await asyncio.sleep(0.1)
    else:
        raise RuntimeError("the server did not accept a connection")

    await ws.send(proto.encode(proto.join("tester")))
    welcome = proto.decode(await asyncio.wait_for(ws.recv(), 10), proto.SERVER_TYPES)
    generator, world = generate_world(welcome)
    layout = layout_for(len(tile_blocks()))
    top = layout.entity_top
    await ws.send(proto.encode(proto.view([0, max(0, top - 2) * UNITS, world.width * UNITS, world.height * UNITS])))
    entered = {}
    deadline = time.monotonic() + 15

    while time.monotonic() < deadline and len(entered) < expected_slots + 3:
        try:
            message = proto.decode(await asyncio.wait_for(ws.recv(), 2), proto.SERVER_TYPES)
        except asyncio.TimeoutError:
            continue

        if message["type"] == proto.TICK_UPDATE:
            for entry in message.get("enter", []):
                entered[entry["id"]] = entry

    await ws.close()
    return welcome, world, entered


port = free_port()
process, lines = start_server(port)

try:
    ready, output = wait_ready(process, lines)
    check("python -m server.server --sandbox starts and becomes ready", ready, "\n".join(output[-15:]))
    text = "\n".join(output)
    check("the server says SANDBOX MODE", "[server] SANDBOX MODE" in text, text[-400:])
    check("the server reports the gallery it built", "[sandbox] gallery:" in text)
    check("the server uses seed 0", "seed 0" in text)

    if ready:
        welcome, world, entered = asyncio.run(play(port, len(entity_entries)))
        check("the welcome carries the sandbox mode and seed 0", welcome["settings"].get("mode") == "sandbox" and welcome["seed"] == 0)
        check("the client builds the server's world", world.generation_checksum == welcome["checksum"] and len(world.labels) == len(tile_blocks()))
        mine = [entry for entry in entered.values() if entry["owner"] == welcome["player_id"]]
        gallery_seen = sorted((entry for entry in entered.values() if entry["owner"] is None), key=lambda entry: entry["id"])
        check("the joining player has 3 test units", len(mine) == 3, f"{len(mine)} own pixels seen")
        check("the client sees every gallery entity", len(gallery_seen) == len(entity_entries), f"{len(gallery_seen)} seen, {len(entity_entries)} expected")
        slots = entity_slots()[: len(gallery_seen)]
        check("they stand in the gallery slots, in catalog order", [(proto.from_wire(entry["x"]), proto.from_wire(entry["y"])) for entry in gallery_seen] == [((x + 0.5) * UNITS, (y + 0.5) * UNITS) for x, y in slots])
        check("they carry their blueprint names", all(entry["name"] for entry in gallery_seen))
finally:
    process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)