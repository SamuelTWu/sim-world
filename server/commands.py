"""Server-side handling of player commands. Never trust the client: everything it sends is checked here.

Commands are an aspect of a pixel, not a power of the player. A pixel only obeys a command if it carries the
"command" trait for it, so nothing is commandable until you decide a pixel can be:

    grant(pixel, "move")                       # pixel.traits["command"] = {"move": True}
    revoke(pixel, "move")
    commandable(pixel, "move")                 # True / False

A blueprint can carry the same thing: "traits": {"command": {"move": true}}.

What a command does is also left open. A valid command does not move anything by itself: it stores an order on
each obeying pixel (pixel.components["order"]) and emits an "order_issued" event. Whatever you decide should
follow orders (a behavior, a task, a reaction) reads the order or listens for the event.

Adding a command:  subclass Command, set `name`, implement run(), decorate it with @command.
Changing who may be commanded:  add or remove functions in GATES (each returns a reason to refuse, or None).

execute() is the only entry point the server calls. It never raises for bad input.
"""
import math
import traceback
from dataclasses import dataclass, field

from game.entity.system.simContext import TILE_UNITS

COMMAND_TRAIT = "command"
ORDER_KEY = "order"
ORDER_ISSUED = "order_issued"
MAX_IDS = 256

COMMANDS = {}
GATES = []


class Rejected(Exception):
    """The command is refused. The message is safe to send back to the player."""


@dataclass
class Outcome:
    ok: bool
    reason: str = ""
    applied: list = field(default_factory=list)
    ignored: dict = field(default_factory=dict)


class CommandContext:
    """What commands may use from the running simulation. This is the one place that knows its attribute names."""

    def __init__(self, sim):
        self.sim = sim

    @property
    def world(self):
        return self.sim.world

    @property
    def events(self):
        return self.sim.systems.events

    @property
    def tick(self):
        return self.sim.tick

    def get_entity(self, entity_id):
        try:
            return self.sim.entity_manager.get(entity_id)
        except KeyError:
            return None


def commandable(entity, name):
    return bool(entity.trait(COMMAND_TRAIT, name, False))


def grant(entity, *names):
    entity.traits.setdefault(COMMAND_TRAIT, {}).update({name: True for name in names})


def revoke(entity, *names):
    values = entity.traits.get(COMMAND_TRAIT)

    if values:
        for name in names:
            values.pop(name, None)


def gate_owner(ctx, entity, player_id, name):
    return None if entity.owner is not None and entity.owner == player_id else "unavailable"


def gate_alive(ctx, entity, player_id, name):
    return None if entity.alive else "unavailable"


def gate_trait(ctx, entity, player_id, name):
    return None if commandable(entity, name) else "cannot be commanded"


GATES.extend([gate_owner, gate_alive, gate_trait])


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def clean_args(args, *keys):
    if not isinstance(args, dict):
        raise Rejected("the arguments must be a map")

    extra = sorted((key for key in args if key not in keys), key=str)

    if extra:
        raise Rejected(f"unexpected argument(s): {extra}")

    missing = [key for key in keys if key not in args]

    if missing:
        raise Rejected(f"missing argument(s): {missing}")


def as_ids(value):
    if not isinstance(value, list) or not value:
        raise Rejected("ids must be a non-empty list")

    if len(value) > MAX_IDS:
        raise Rejected(f"at most {MAX_IDS} ids per command")

    if not all(is_int(item) for item in value):
        raise Rejected("ids must be integers")

    return list(dict.fromkeys(value))


def as_point(value, ctx):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(is_number(item) for item in value):
        raise Rejected("the target must be [x, y]")

    try:
        x, y = float(value[0]), float(value[1])
    except (OverflowError, ValueError):
        raise Rejected("the target must be finite numbers") from None

    if not (math.isfinite(x) and math.isfinite(y)):
        raise Rejected("the target must be finite numbers")

    world = ctx.world

    if not (0.0 <= x < world.width * TILE_UNITS and 0.0 <= y < world.height * TILE_UNITS):
        raise Rejected("the target is outside the world")

    return x, y


def refusal(ctx, entity, player_id, name):
    for gate in GATES:
        reason = gate(ctx, entity, player_id, name)

        if reason:
            return reason

    return None


def explain(ignored):
    counts = {}

    for reason in ignored.values():
        counts[reason] = counts.get(reason, 0) + 1

    return "no commandable pixels: " + ", ".join(f"{counts[reason]} {reason}" for reason in sorted(counts))


def select_pixels(ctx, player_id, ids, name, strict=False):
    """Resolve ids to the pixels this player may give this command to. Returns (pixels, ignored {id: reason})."""
    pixels, ignored = [], {}

    for entity_id in ids:
        entity = ctx.get_entity(entity_id)
        reason = "unavailable" if entity is None else refusal(ctx, entity, player_id, name)

        if reason:
            ignored[entity_id] = reason
        else:
            pixels.append(entity)

    if not pixels or (strict and ignored):
        raise Rejected(explain(ignored))

    return pixels, ignored


def issue_order(ctx, entity, order):
    entity.components[ORDER_KEY] = order
    events = ctx.events

    if events is not None:
        events.emit(ORDER_ISSUED, entity=entity, order=order)


class Command:
    name = ""
    strict = False

    def run(self, ctx, player_id, args):
        raise NotImplementedError


def command(cls):
    COMMANDS[cls.name] = cls()
    return cls


@command
class Move(Command):
    """Order pixels to go to a point. args: {"ids": [pixel ids], "target": [x, y] in world units}.

    Pixels that are unknown, not yours, dead, or not able to obey are skipped (so a stale id in a group does not
    ruin the order). Set `strict = True` to refuse the whole command instead. The order is stored as
    {"kind": "move", "x", "y", "tick", "issuer"}.
    """

    name = "move"

    def run(self, ctx, player_id, args):
        clean_args(args, "ids", "target")
        ids = as_ids(args["ids"])
        x, y = as_point(args["target"], ctx)
        pixels, ignored = select_pixels(ctx, player_id, ids, self.name, self.strict)

        for pixel in pixels:
            issue_order(ctx, pixel, {"kind": "move", "x": x, "y": y, "tick": ctx.tick, "issuer": player_id})

        return Outcome(True, applied=[pixel.id for pixel in pixels], ignored=ignored)


def execute(ctx, player_id, name, args):
    handler = COMMANDS.get(name) if isinstance(name, str) else None

    if handler is None:
        return Outcome(False, "unknown command")

    try:
        return handler.run(ctx, player_id, args)
    except Rejected as problem:
        return Outcome(False, str(problem))
    except Exception:
        traceback.print_exc()
        return Outcome(False, "the server could not process that command")