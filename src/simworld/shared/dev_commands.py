import math
import re
from dataclasses import dataclass

NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
MAX_TILE = 1_000_000
MAX_ID = 1_000_000_000
STEP_MAX = 100
SPEEDS = (0.25, 1.0, 4.0)
MAX_SHOWN = 32
POINT_KEYS = ("x", "y")
NEEDS_SELECTION = "select something first"
NEEDS_CURSOR = "point at a tile first"


class DevSyntaxError(Exception):
    pass


@dataclass(frozen=True)
class Arg:
    name: str
    kind: str
    optional: bool = False
    choices: tuple | None = None
    low: float | None = None
    high: float | None = None
    default: object = None
    source: str | None = None


@dataclass(frozen=True)
class Command:
    help: str
    args: tuple = ()
    example: str = ""


ID = Arg("id", "int", optional=True, low=0, high=MAX_ID, source="selected")
AT = Arg("at", "point", optional=True, source="cursor")

DEV_COMMANDS = {
    "pause": Command("pause or resume the simulation", (), "/pause"),
    "step": Command("run this many ticks while paused (1 to 100, default 1)", (Arg("count", "int", optional=True, low=1, high=STEP_MAX, default=1),), "/step 5"),
    "speed": Command("run the simulation at this speed", (Arg("factor", "number", choices=SPEEDS),), "/speed 4"),
    "spawn": Command("create an entity from a blueprint (at the mouse if no point is given)", (Arg("blueprint", "name"), AT), "/spawn wolf 10 12"),
    "delete": Command("remove an entity (the selected one if no id is given)", (ID,), "/delete 3"),
    "wake": Command("wake a frozen or sleeping entity (the selected one if no id is given)", (ID,), "/wake 3"),
    "inspect": Command("show everything about an entity (the selected one if no id is given)", (ID,), "/inspect 3"),
    "tile": Command("paint a tile (at the mouse if no point is given)", (Arg("name", "name"), AT), "/tile stone 4 4"),
    "catalog": Command("list the blueprints and tiles", (), "/catalog"),
    "help": Command("list the commands, or show one", (Arg("command", "name", optional=True),), "/help spawn"),
}


def names():
    return sorted(DEV_COMMANDS)


def shown(value):
    return f"{value:g}" if isinstance(value, float) else str(value)


def keys_of(arg):
    return POINT_KEYS if arg.kind == "point" else (arg.name,)


def usage(what):
    parts = []

    for arg in DEV_COMMANDS[what].args:
        label = "|".join(shown(choice) for choice in arg.choices) if arg.choices else ("x y" if arg.kind == "point" else arg.name)
        parts.append(f"[{label}]" if arg.optional else f"<{label}>")

    return " ".join([f"/{what}"] + parts)


def help_lines():
    return [f"{usage(what)}: {DEV_COMMANDS[what].help}" for what in names()]


def check_number(label, value, low, high):
    try:
        usable = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        value = float(value) if usable else value
    except OverflowError:
        usable = False

    if not usable:
        raise DevSyntaxError(f"'{label}' must be a number")

    if low is not None and value < low:
        raise DevSyntaxError(f"'{label}' must be at least {shown(float(low))}")

    if high is not None and value > high:
        raise DevSyntaxError(f"'{label}' must be at most {shown(float(high))}")

    return value


def check_value(label, arg, value):
    kind = "number" if arg.kind == "point" else arg.kind
    low, high = (-MAX_TILE, MAX_TILE) if arg.kind == "point" else (arg.low, arg.high)

    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise DevSyntaxError(f"'{label}' must be a whole number")

        check_number(label, value, low, high)
    elif kind == "number":
        value = check_number(label, value, low, high)
    elif kind == "name":
        if not isinstance(value, str) or not NAME_PATTERN.fullmatch(value):
            raise DevSyntaxError(f"'{label}' must be a name: letters, digits, _ - . (up to 64)")
    else:
        raise DevSyntaxError(f"'{label}' has an unknown type")

    if arg.choices is not None and value not in arg.choices:
        raise DevSyntaxError(f"'{label}' must be one of {', '.join(shown(choice) for choice in arg.choices)}")

    return value


def validate(what, args):
    command = DEV_COMMANDS.get(what) if isinstance(what, str) else None

    if command is None:
        raise DevSyntaxError("unknown dev command")

    if not isinstance(args, dict):
        raise DevSyntaxError("args must be a map")

    allowed = {key for arg in command.args for key in keys_of(arg)}

    for key in args:
        if not isinstance(key, str) or key not in allowed:
            raise DevSyntaxError(f"unexpected argument {str(key)[:MAX_SHOWN]!r}")

    clean = {}

    for arg in command.args:
        keys = keys_of(arg)
        given = [key in args for key in keys]

        if not any(given):
            if arg.default is not None:
                clean[arg.name] = arg.default
            elif not arg.optional or arg.source is not None:
                raise DevSyntaxError(f"missing argument '{arg.name}'")

            continue

        for key, present in zip(keys, given):
            if not present:
                raise DevSyntaxError(f"missing argument '{key}'")

            clean[key] = check_value(key, arg, args[key])

    return clean


def parse_int(word):
    try:
        return int(word)
    except ValueError:
        raise DevSyntaxError(f"'{word[:MAX_SHOWN]}' is not a whole number") from None


def parse_number(word):
    try:
        value = float(word)
    except ValueError:
        raise DevSyntaxError(f"'{word[:MAX_SHOWN]}' is not a number") from None

    if not math.isfinite(value):
        raise DevSyntaxError(f"'{word[:MAX_SHOWN]}' is not a number")

    return value


def selected_id(context):
    value = context.get("selected")

    if isinstance(value, bool) or not isinstance(value, int):
        raise DevSyntaxError(NEEDS_SELECTION)

    return value


def cursor_point(context):
    value = context.get("cursor")

    try:
        x, y = value
        return float(x), float(y)
    except (TypeError, ValueError):
        raise DevSyntaxError(NEEDS_CURSOR) from None


def parse(text, context=None):
    if not isinstance(text, str):
        raise DevSyntaxError("type a command, or /help")

    context = context if isinstance(context, dict) else {}
    words = text.split()

    if words and words[0].startswith("/"):
        words[0] = words[0][1:]

    if not words or not words[0]:
        raise DevSyntaxError("type a command, or /help")

    what = words[0].lower()

    if what not in DEV_COMMANDS:
        raise DevSyntaxError(f"unknown command '{what[:MAX_SHOWN]}': type /help for the list")

    words = words[1:]
    command = DEV_COMMANDS[what]
    args = {}
    index = 0

    for arg in command.args:
        if index >= len(words):
            if arg.source == "selected":
                args[arg.name] = selected_id(context)
            elif arg.source == "cursor":
                args["x"], args["y"] = cursor_point(context)
            elif not arg.optional and arg.default is None:
                raise DevSyntaxError(f"missing <{'x y' if arg.kind == 'point' else arg.name}>, usage: {usage(what)}")

            continue

        word = words[index]

        if arg.kind == "point":
            if word == "~" and arg.source == "cursor":
                args["x"], args["y"] = cursor_point(context)
                index += 1
            elif index + 1 >= len(words):
                raise DevSyntaxError(f"a point needs two numbers, x and y, or ~ for the mouse, usage: {usage(what)}")
            else:
                args["x"], args["y"] = parse_number(word), parse_number(words[index + 1])
                index += 2
        elif arg.kind == "int" and word == "@" and arg.source == "selected":
            args[arg.name] = selected_id(context)
            index += 1
        elif arg.kind == "int":
            args[arg.name] = parse_int(word)
            index += 1
        elif arg.kind == "number":
            args[arg.name] = parse_number(word)
            index += 1
        else:
            args[arg.name] = word
            index += 1

    if index < len(words):
        raise DevSyntaxError(f"too many arguments, usage: {usage(what)}")

    return what, validate(what, args)