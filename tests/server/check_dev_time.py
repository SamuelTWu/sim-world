import hashlib
import sys
from types import SimpleNamespace

from src.simworld.server import dev_commands as dev
from src.simworld.server.dev_time import MAX_TICKS_PER_LOOP, init_time, ticks_to_run

failures = []


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class FakeSim:
    sandbox = True

    def __init__(self):
        self.tick = 0
        self.systems = SimpleNamespace(counters=None)

    def step(self):
        self.tick += 1


def make():
    server = SimpleNamespace(sim=FakeSim())
    init_time(server)
    return server


def advance(server):
    count = ticks_to_run(server)

    for _ in range(count):
        server.sim.step()

    return count


def command(server, what, **args):
    return dev.run_dev(server, None, what, args)


def run_loops(server, loops):
    return [advance(server) for _ in range(loops)]


server = make()
check("a new server runs one tick per loop", run_loops(server, 100) == [1] * 100 and server.sim.tick == 100)

result = command(server, "pause")
check("pause says where it is", result.ok and result.text == "paused at tick 100" and result.data["paused"] is True and result.data["tick"] == 100, str(result))
check("paused, the tick number stays put", run_loops(server, 50) == [0] * 50 and server.sim.tick == 100)

result = command(server, "step", count=3)
check("step 3 is accepted and says where it will stop", result.ok and "paused again at tick 103" in result.text, str(result))
check("step 3 advances by exactly 3, in one loop", run_loops(server, 5) == [3, 0, 0, 0, 0] and server.sim.tick == 103)
check("the step counter is cleared", server.pending_steps == 0)

result = command(server, "step", count=1)
check("step with the default count of 1", result.ok and run_loops(server, 2) == [1, 0] and server.sim.tick == 104, str(result))
command(server, "step", count=2)
command(server, "step", count=2)
check("steps queued in the same loop add up", server.pending_steps == 4 and advance(server) == 4 and server.sim.tick == 108)
command(server, "step", count=100)
result = command(server, "step", count=1)
check("more than 100 queued steps are refused", result.ok is False and "too many" in result.text and server.pending_steps == 100, str(result))
check("100 steps run in one loop", advance(server) == 100 and server.sim.tick == 208)

result = command(server, "pause")
check("pause toggles back, saying so", result.ok and result.text == "running at tick 208, speed 1x" and result.data["paused"] is False, str(result))
check("running again, one tick per loop", run_loops(server, 3) == [1, 1, 1])

server = make()
result = command(server, "step", count=3)
check("step while running is refused", result.ok is False and result.text == "pause first: /pause" and server.pending_steps == 0 and run_loops(server, 2) == [1, 1], str(result))

server = make()
result = command(server, "speed", factor=4.0)
check("speed 4 runs four ticks per loop", result.ok and run_loops(server, 10) == [4] * 10 and server.sim.tick == 40, str(result))
check("the speed result says where it is", result.text == "speed 4x at tick 0", result.text)

server = make()
command(server, "speed", factor=0.25)
ticks = run_loops(server, 20)
check("speed 0.25 runs one tick per four loops", ticks == [0, 0, 0, 1] * 5 and server.sim.tick == 5, str(ticks))

server = make()
command(server, "speed", factor=1.0)
check("speed 1 is one tick per loop", run_loops(server, 10) == [1] * 10)

server = make()
command(server, "speed", factor=0.25)
run_loops(server, 2)
command(server, "speed", factor=4.0)
check("changing speed forgets the half-collected tick", run_loops(server, 2) == [4, 4])
command(server, "speed", factor=0.25)
run_loops(server, 3)
command(server, "pause")
command(server, "pause")
check("pausing and resuming forgets it too", run_loops(server, 4) == [0, 0, 0, 1])

server = make()
result = command(server, "pause")
result = command(server, "speed", factor=4.0)
check("speed while paused is kept and says it is paused", result.ok and result.text == "speed 4x, paused at tick 0" and run_loops(server, 3) == [0, 0, 0], str(result))
command(server, "pause")
check("it applies after resuming", run_loops(server, 2) == [4, 4])

server = make()
command(server, "pause")
command(server, "step", count=5)
command(server, "pause")
check("leaving pause drops queued steps", server.pending_steps == 0 and run_loops(server, 1) == [1])

check("at most four ticks run in one loop", MAX_TICKS_PER_LOOP == 4)
server = make()
server.speed, server.credit = 4.0, 0.9999
check("a full credit never runs more than four", ticks_to_run(server) == 4)
server = make()
server.speed = 100.0
check("an absurd speed is capped at four per loop", ticks_to_run(server) == 4)

for value in (0.5, 2.0, 0, -1, "1", True, None, float("nan"), 8):
    server = make()
    result = command(server, "speed", factor=value)
    check(f"speed {value!r} is refused and changes nothing", result.ok is False and server.speed == 1.0, str(result))

for value in (0, 101, -2, 2.5, "3", True, None):
    server = make()
    command(server, "pause")
    result = command(server, "step", count=value)
    check(f"step {value!r} is refused and queues nothing", result.ok is False and server.pending_steps == 0, str(result))

normal = make()
normal.sim.sandbox = False
check("on a normal server pause, step and speed are refused and nothing changes", all(command(normal, what, **args).text == "not available" for what, args in (("pause", {}), ("step", {"count": 1}), ("speed", {"factor": 4.0}))) and normal.paused is False and normal.speed == 1.0 and normal.pending_steps == 0)

from src.simworld.shared.phase import PLAYING
from src.simworld.server.server import Server
from src.simworld.sim.dev.sandbox_mode import populate_sandbox, prepare_sandbox
from src.simworld.sim.dev.start_units import give_test_units
from src.simworld.sim.simulation import Simulation

SCRIPT = [("loops", 12), ("speed", 4.0), ("loops", 5), ("pause", None), ("loops", 3), ("step", 3), ("loops", 2), ("speed", 0.25), ("pause", None), ("loops", 9), ("speed", 1.0), ("loops", 6), ("pause", None), ("step", 7), ("loops", 2)]


def real_server():
    sim = Simulation()
    seed = prepare_sandbox(sim, None)
    sim.start_new_game(seed)
    populate_sandbox(sim)
    give_test_units(sim, 1)
    return Server(sim, stats_interval=0, start_phase=PLAYING)


def digest(server):
    sim = server.sim
    result = hashlib.sha256()
    result.update(f"{sim.tick}|{sim.world.checksum()}".encode())

    for entity in sorted(sim.entity_manager.all(), key=lambda e: e.id):
        result.update(f"{entity.id}|{float(entity.position.x).hex()}|{float(entity.position.y).hex()}|{float(entity.health).hex()}|{float(entity.energy).hex()}|{entity.alive}".encode())

    for position, name in sorted(sim.world.changes.items()):
        result.update(f"{position}{name}".encode())

    return result.hexdigest()[:16]


def play(script):
    server = real_server()
    ticks = []

    for what, value in script:
        if what == "loops":
            for _ in range(value):
                server.advance()
                ticks.append(server.sim.tick)
        else:
            args = {} if what == "pause" else ({"count": value} if what == "step" else {"factor": value})
            result = dev.run_dev(server, None, what, args)
            assert result.ok, (what, value, result)

    return server, ticks


first, ticks_first = play(SCRIPT)
second, ticks_second = play(SCRIPT)
check("two runs with the same dev commands reach the same tick and the same world", first.sim.tick == second.sim.tick and ticks_first == ticks_second and digest(first) == digest(second), f"{first.sim.tick} {second.sim.tick} {digest(first)} {digest(second)}")
other, _ = play(SCRIPT + [("step", 1), ("loops", 1)])
check("the check is not vacuous: one more step gives a different result", other.sim.tick == first.sim.tick + 1 and digest(other) != digest(first))
check("12 loops at speed 1 gave 12 ticks, then 5 loops at 4 gave 20 more", ticks_first[11] - ticks_first[0] == 11 and ticks_first[16] - ticks_first[11] == 20, str(ticks_first[:18]))

paused = real_server()
paused.advance()
start = paused.sim.tick
dev.run_dev(paused, None, "pause", {})
for _ in range(30):
    paused.advance()
check("a real paused server keeps its tick", paused.sim.tick == start)
dev.run_dev(paused, None, "step", {"count": 3})
paused.advance()
check("a real step 3 advances exactly 3", paused.sim.tick == start + 3)

normal_server = real_server()
normal_server.sim.sandbox = False
normal_server.advance()
check("a normal server still runs one tick per loop", normal_server.sim.tick == 1)

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")