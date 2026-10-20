import traceback
from dataclasses import dataclass

from ..shared.dev_commands import DEV_COMMANDS, STEP_MAX, DevSyntaxError, help_lines, names, usage, validate
from .dev_time import clear_credit

DEV_HANDLERS = {}
MAX_TEXT = 1000


@dataclass(frozen=True)
class DevResult:
    ok: bool
    text: str = ""
    data: dict | None = None


def dev_command(name):
    def register(handler):
        if name not in DEV_COMMANDS:
            raise ValueError(f"dev command {name!r} is not in the table in shared/dev_commands.py")

        if name in DEV_HANDLERS:
            raise ValueError(f"dev command {name!r} already has a handler")

        DEV_HANDLERS[name] = handler
        return handler

    return register


def count_refused(server):
    counters = getattr(getattr(server.sim, "systems", None), "counters", None)

    if counters is not None:
        counters.add("dev_refused", 1)


def finish(result):
    if result is None:
        return DevResult(True)

    if isinstance(result, str):
        return DevResult(True, result[:MAX_TEXT])

    if isinstance(result, DevResult) and isinstance(result.ok, bool) and isinstance(result.text, str) and (result.data is None or isinstance(result.data, dict)):
        return DevResult(result.ok, result.text[:MAX_TEXT], result.data or None)

    raise TypeError(f"a dev handler returned {type(result).__name__}")


def run_dev(server, client, what, args):
    try:
        if getattr(server.sim, "sandbox", False) is not True:
            count_refused(server)
            return DevResult(False, "not available")

        if not isinstance(what, str) or what not in DEV_COMMANDS:
            return DevResult(False, "unknown dev command")

        try:
            clean = validate(what, args)
        except DevSyntaxError as problem:
            return DevResult(False, str(problem))

        handler = DEV_HANDLERS.get(what)

        if handler is None:
            return DevResult(False, "not implemented yet")

        return finish(handler(server, client, clean))
    except Exception:
        print(f"[server] dev command {str(what)[:32]!r} failed:\n{traceback.format_exc()}", flush=True)
        return DevResult(False, "dev command failed")


@dev_command("help")
def dev_help(server, client, args):
    command = args.get("command")

    if command is None:
        return DevResult(True, "\n".join(help_lines()), {"commands": names()})

    if command not in DEV_COMMANDS:
        return DevResult(False, f"unknown command '{command}'")

    return DevResult(True, f"{usage(command)}: {DEV_COMMANDS[command].help}", {"commands": [command]})


def clock_data(server):
    return {"paused": server.paused, "tick": server.sim.tick, "speed": server.speed, "pending": server.pending_steps}


@dev_command("pause")
def dev_pause(server, client, args):
    server.paused = not server.paused
    server.pending_steps = 0
    clear_credit(server)
    tick = server.sim.tick
    return DevResult(True, f"paused at tick {tick}" if server.paused else f"running at tick {tick}, speed {server.speed:g}x", clock_data(server))


@dev_command("step")
def dev_step(server, client, args):
    if not server.paused:
        return DevResult(False, "pause first: /pause")

    count = args["count"]

    if server.pending_steps + count > STEP_MAX:
        return DevResult(False, f"too many steps queued ({server.pending_steps}), try again in a moment")

    server.pending_steps += count
    tick = server.sim.tick
    return DevResult(True, f"stepping {count} from tick {tick}, paused again at tick {tick + server.pending_steps}", clock_data(server))


@dev_command("speed")
def dev_speed(server, client, args):
    server.speed = float(args["factor"])
    clear_credit(server)
    tick = server.sim.tick
    return DevResult(True, f"speed {server.speed:g}x, paused at tick {tick}" if server.paused else f"speed {server.speed:g}x at tick {tick}", clock_data(server))