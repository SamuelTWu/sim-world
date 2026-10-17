import contextlib
import importlib
import io
import sys
import types
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "src" / "simworld").is_dir())
sys.path.insert(0, str(ROOT))

checks = 0
failures = []


def check(condition, message):
    global checks
    checks += 1

    if not condition:
        failures.append(message)


def install_stand_ins():
    for name in ("msgpack", "websockets", "websockets.asyncio", "websockets.asyncio.server", "websockets.exceptions"):
        try:
            importlib.import_module(name)
        except ImportError:
            module = types.ModuleType(name)
            module.__getattr__ = lambda attribute: (lambda *args, **kwargs: None)
            sys.modules[name] = module

            if name == "websockets.exceptions":
                module.ConnectionClosed = type("ConnectionClosed", (Exception,), {})


install_stand_ins()

from src.simworld.shared import phase as phases
from src.simworld.sim.commands import command as commands
from src.simworld.server.server import Server

quiet = io.StringIO()


def run(phase, name, args=None):
    with contextlib.redirect_stderr(quiet):
        return commands.execute(types.SimpleNamespace(phase=phase), 1, name, {} if args is None else args)


check(phases.allowed(phases.PLACEMENT, "place_colony"), "place_colony is allowed in placement")
check(not phases.allowed(phases.LOBBY, "place_colony") and not phases.allowed(phases.PLAYING, "place_colony"), "place_colony is rejected outside placement")
check(phases.allowed(phases.LOBBY, "lobby_set_ready") and phases.allowed(phases.LOBBY, "lobby_start"), "lobby_* commands are allowed in the lobby")
check(not phases.allowed(phases.PLACEMENT, "lobby_start") and not phases.allowed(phases.PLAYING, "lobby_start"), "lobby_* commands are rejected outside the lobby")
check(phases.allowed(phases.PLAYING, "lobbying") and not phases.allowed(phases.LOBBY, "lobbying"), "the lobby_ pattern needs the underscore")
check(phases.allowed(phases.PLAYING, "move") and not phases.allowed(phases.LOBBY, "move") and not phases.allowed(phases.PLACEMENT, "move"), "other commands default to the playing phase")
check(phases.phases_for("lobby_x") == {phases.LOBBY} and phases.phases_for("anything") == {phases.PLAYING}, "phases_for returns the matching set")
check(set(phases.PHASES) == {phases.LOBBY, phases.PLACEMENT, phases.PLAYING}, "PHASES lists the three phases")

commands.load_commands()
names = sorted(commands.COMMANDS)
check(len(names) > 0, "commands are registered")

for name in names:
    for phase in phases.PHASES:
        outcome = run(phase, name)
        rejected_for_phase = not outcome.ok and outcome.reason == phases.WRONG_PHASE
        check(rejected_for_phase == (not phases.allowed(phase, name)), f"{name} in {phase}: wrong_phase exactly when the phase does not allow it (got {outcome.reason!r})")

for phase in phases.PHASES:
    for name in ("nope", None, 5, ["move"]):
        outcome = run(phase, name)
        check(not outcome.ok and outcome.reason == "unknown command", f"unknown command {name!r} in {phase} stays unknown")

check(commands.CommandContext(types.SimpleNamespace(tick=0)).phase == phases.PLAYING, "a bare CommandContext defaults to the playing phase")

sim = types.SimpleNamespace(tick=42)
server = Server(sim)
check(server.phase == phases.LOBBY and server.commands.phase == phases.LOBBY, "a new server starts in the lobby")
check(server.phase_tick == 42, "phase_tick records the tick the phase began")
check(Server(sim, start_phase=phases.PLAYING).phase == phases.PLAYING, "start_phase sets the first phase")

sim.tick = 99
server.phase = phases.PLACEMENT
check(server.phase == phases.PLACEMENT and server.commands.phase == phases.PLACEMENT and server.phase_tick == 99, "setting the phase updates the command context and phase_tick")

try:
    server.phase = "nope"
    check(False, "an unknown phase is refused")
except ValueError:
    check(server.phase == phases.PLACEMENT and server.phase_tick == 99, "a refused phase leaves the state unchanged")

try:
    Server(sim, start_phase="nope")
    check(False, "an unknown start_phase is refused")
except ValueError:
    check(True, "an unknown start_phase is refused")

sent = []
server.send = lambda client, message: sent.append(message)
client = types.SimpleNamespace(player_id=1)
server.phase = phases.LOBBY
server.handle_command(client, {"type": "command", "name": "move", "args": {}, "seq": 5})
check(len(sent) == 1 and phases.WRONG_PHASE in str(sent[0]), "a command in the wrong phase is answered with wrong_phase")

sent.clear()
server.phase = phases.PLAYING

with contextlib.redirect_stderr(quiet):
    server.handle_command(client, {"type": "command", "name": "move", "args": {}, "seq": 6})

check(len(sent) == 1 and phases.WRONG_PHASE not in str(sent[0]), "the same command in the playing phase passes the phase gate")

if failures:
    for failure in failures:
        print(f"FAILED: {failure}")

    print(f"{len(failures)} of {checks} checks failed")
    sys.exit(1)

print(f"all {checks} checks passed")