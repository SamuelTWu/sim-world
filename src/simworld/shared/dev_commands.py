import math
from dataclasses import dataclass

MAX_PROBLEM_NAME = 32


@dataclass(frozen=True)
class Arg:
    kind: type
    required: bool = True
    default: object = None
    low: float | None = None
    high: float | None = None
    choices: tuple | None = None
    max_length: int = 64


@dataclass(frozen=True)
class Spec:
    help: str
    args: dict


COMMANDS = {
    "help": Spec("list the dev commands", {}),
}


def clean_value(name, arg, value):
    kind = arg.kind

    if kind is bool:
        if not isinstance(value, bool):
            return None, f"'{name}' must be true or false"
    elif kind is int:
        if isinstance(value, bool) or not isinstance(value, int):
            return None, f"'{name}' must be a whole number"
    elif kind is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None, f"'{name}' must be a number"

        value = float(value)
    elif kind is str:
        if not isinstance(value, str):
            return None, f"'{name}' must be text"

        if len(value) > arg.max_length:
            return None, f"'{name}' is longer than {arg.max_length} characters"

    if kind in (int, float):
        if arg.low is not None and value < arg.low:
            return None, f"'{name}' must be at least {arg.low}"

        if arg.high is not None and value > arg.high:
            return None, f"'{name}' must be at most {arg.high}"

    if arg.choices is not None and value not in arg.choices:
        return None, f"'{name}' must be one of {', '.join(str(choice) for choice in arg.choices)}"

    return value, None


def validate(what, args):
    spec = COMMANDS.get(what) if isinstance(what, str) else None

    if spec is None:
        return None, "unknown dev command"

    if not isinstance(args, dict):
        return None, "args must be a map"

    for key in args:
        if not isinstance(key, str) or key not in spec.args:
            return None, f"unexpected argument {str(key)[:MAX_PROBLEM_NAME]!r}"

    clean = {}

    for name, arg in spec.args.items():
        if name not in args:
            if arg.required:
                return None, f"missing argument '{name}'"

            if arg.default is not None:
                clean[name] = arg.default

            continue

        value, problem = clean_value(name, arg, args[name])

        if problem is not None:
            return None, problem

        clean[name] = value

    return clean, None


def usage(name):
    spec = COMMANDS[name]
    parts = [f"<{key}>" if arg.required else f"[{key}]" for key, arg in spec.args.items()]
    return " ".join([name] + parts)


def help_lines():
    return [f"{usage(name)}: {COMMANDS[name].help}" for name in sorted(COMMANDS)]