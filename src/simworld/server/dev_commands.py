import traceback
from dataclasses import dataclass

from ..shared.dev_commands import COMMANDS, help_lines, validate

DEV_HANDLERS = {}
MAX_TEXT = 1000


@dataclass(frozen=True)
class DevResult:
    ok: bool
    text: str = ""
    data: dict | None = None


def dev_command(name):
    def register(handler):
        if name not in COMMANDS:
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

        handler = DEV_HANDLERS.get(what) if isinstance(what, str) else None

        if handler is None:
            return DevResult(False, "unknown dev command")

        clean, problem = validate(what, args)

        if problem is not None:
            return DevResult(False, problem)

        return finish(handler(server, client, clean))
    except Exception:
        print(f"[server] dev command {str(what)[:32]!r} failed:\n{traceback.format_exc()}", flush=True)
        return DevResult(False, "dev command failed")


@dev_command("help")
def dev_help(server, client, args):
    return DevResult(True, "\n".join(help_lines()), {"commands": sorted(COMMANDS)})