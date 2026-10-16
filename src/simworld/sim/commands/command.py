"""Handling of player commands. Never trust the client: everything it sends is checked here.

This file is the framework. Each command lives in its own file in game/command/commands/ (move.py, ...) and
registers itself with @command. load_commands() imports that whole folder, so dropping in a new file is enough.

Commands are an aspect of a pixel, not a power of the player. A pixel only obeys a command if it carries the
"command" trait for it, so nothing is commandable until you decide a pixel can be:

    grant(pixel, "move")                       # pixel.traits["command"] = {"move": True}
    revoke(pixel, "move")
    commandable(pixel, "move")                 # True / False

A blueprint can carry the same thing: "traits": {"command": {"move": true}}.

A command never does the work itself. Every pixel action is a behavior (entity/behavior/behaviors/: move, attack, spawn,
pickup), which a pixel can also choose on its own through the decision system. A valid command only validates, then
stores an order on each obeying pixel (pixel.components["order"] = {"kind": behavior name, ...that action's data...})
and emits "order_issued". SystemRunner (entity/system/orders.py) then starts that behavior's task with the order's data
and guarantees nothing else interrupts it. So a command's job is to turn the player's clicks into the action's data.
A pixel needs BOTH the "command" permission for the command AND the behavior of the same name (see GATES).

Adding a command:  new file in game/command/commands/. Subclass Command, set `name`, implement run(), decorate
it with @command. Use the helpers below (clean_args, as_ids, as_point, select_pixels, issue_order).
Selecting several pixels: every pixel command takes "ids", or "box": [x0, y0, x1, y1] (a drag-select rectangle in world units),
which the server turns into the ids of the player's own pixels inside it that may be given that command.
Clicking: the `act` command (commands/act.py) turns one click at a point into any of the other commands.
Adding a command also means: a behavior with the same name, and a line in the `command` behavior's params.
Changing who may be commanded:  add or remove functions in GATES (each returns a reason to refuse, or None).

execute() is the only entry point the server calls. It never raises for bad input.
"""
import importlib
import json
import math
import os
import re
import traceback
from dataclasses import dataclass, field
import pkgutil

from ..core.activity import wake
from ..core.sim_context import TILE_UNITS

BLUEPRINT_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
COMMAND_TRAIT = "command"
ORDER_KEY = "order"
ORDER_ISSUED = "order_issued"
MAX_IDS = 256
PICK_RADIUS = TILE_UNITS * 0.75

COMMANDS = {}
GATES = []
loaded = False


class Rejected(Exception):
    """The command is refused. The message is safe to send back to the player."""


@dataclass
class Outcome:
    ok: bool
    reason: str = ""
    applied: list = field(default_factory=list)
    ignored: dict = field(default_factory=dict)
    info: dict | None = None  # data to send back to the asking player (see `inspect`): the server sends it as an "entity_info" message


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

    def pixels(self):
        """Every living pixel."""
        return self.sim.entity_manager.all()

    def get_entity(self, entity_id):
        try:
            return self.sim.entity_manager.get(entity_id)
        except KeyError:
            return None

    def load_blueprint(self, blueprint_id):
        """The blueprint's definition dict, or None if there is no such blueprint."""
        try:
            return self.sim.entity_manager.entity_factory.load_definition(blueprint_id)
        except (OSError, ValueError):
            return None

    @property
    def behaviors(self):
        """The BehaviorManager: what behaviors exist, their parameters and costs."""
        return self.sim.behavior_manager

    def blueprint_exists(self, blueprint_id):
        return (self.sim.entity_manager.entity_factory.definitions_path / f"{blueprint_id}.json").exists()

    def write_blueprint(self, blueprint_id, definition):
        """Save a definition as <id>.json next to the other blueprints (what `place` and the client's tray read). Never overwrites."""
        factory = self.sim.entity_manager.entity_factory
        path = factory.definitions_path / f"{blueprint_id}.json"
        temporary = path.with_name(f".{blueprint_id}.json.tmp")
        temporary.write_text(json.dumps(definition, indent=4) + "\n", encoding="utf-8")

        try:
            os.link(temporary, path)  # fails if the file exists, so nothing is ever overwritten
        finally:
            temporary.unlink(missing_ok=True)

        factory.definitions.pop(blueprint_id, None)

    def spawn(self, definition, player_id, x, y):
        """Create a pixel from a definition at (x, y), owned by player_id, and record that the player owns it.

        Used by `place` (the player creates a pixel). The `spawn` behavior uses the same Simulation.spawn_pixel through SimContext.
        """
        return self.sim.create_pixel(definition, player_id, x, y)


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


def gate_behavior(ctx, entity, player_id, name):
    """Orders are carried out by the pixel's own behavior of the same name, so it needs that behavior."""
    return None if entity.has_trait(name) else "cannot do that"


GATES.extend([gate_owner, gate_alive, gate_trait, gate_behavior])


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


def as_box(value, ctx):
    """[x0, y0, x1, y1] in world units, in any corner order, clamped to the world. Returns (left, top, right, bottom)."""
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not all(is_number(item) for item in value):
        raise Rejected("the box must be [x0, y0, x1, y1]")

    try:
        x0, y0, x1, y1 = (float(item) for item in value)
    except (OverflowError, ValueError):
        raise Rejected("the box must be finite numbers") from None

    if not all(math.isfinite(item) for item in (x0, y0, x1, y1)):
        raise Rejected("the box must be finite numbers")

    width, height = ctx.world.width * TILE_UNITS, ctx.world.height * TILE_UNITS
    left, right = sorted((max(0.0, min(width, x0)), max(0.0, min(width, x1))))
    top, bottom = sorted((max(0.0, min(height, y0)), max(0.0, min(height, y1))))
    return left, top, right, bottom


def pick_entity(ctx, x, y, accept, radius=PICK_RADIUS):
    """The nearest living pixel within `radius` of (x, y) that accept(pixel) allows, or None. Ties go to the lowest id."""
    best, best_distance = None, radius

    for pixel in sorted(ctx.pixels(), key=lambda entity: entity.id):
        distance = math.hypot(pixel.position.x - x, pixel.position.y - y)

        if distance <= best_distance and accept(pixel):
            best, best_distance = pixel, distance

    return best


def as_blueprint(value, ctx):
    """Resolve a blueprint id (a file name in game/entity/entities, without .json) to (id, definition)."""
    if not isinstance(value, str) or not BLUEPRINT_ID.match(value):
        raise Rejected("unknown blueprint")

    definition = ctx.load_blueprint(value)

    if definition is None:
        raise Rejected("unknown blueprint")

    return value, definition


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
    selects = True

    def selection_name(self, args):
        """The command name a drag-selected box is filtered by (a box only picks pixels that may be given this command)."""
        return self.name

    def run(self, ctx, player_id, args):
        raise NotImplementedError


def command(cls):
    COMMANDS[cls.name] = cls()
    return cls


def load_commands():
    global loaded

    if not loaded:
        package = importlib.import_module(__package__)

        for module_info in sorted(pkgutil.iter_modules(package.__path__), key=lambda info: info.name):
            if module_info.name != "command":
                importlib.import_module(f"{__package__}.{module_info.name}")

        loaded = True


def resolve_box(ctx, player_id, handler, args):
    """Turn {"box": [x0, y0, x1, y1]} into {"ids": [...]}: the player's own pixels inside the box that may be given this command.

    This is drag-select done on the server: the client sends the rectangle it dragged (in world units) instead of listing ids,
    so it works for pixels the client has not heard about yet and does not hit the per-command id limit by accident.
    """
    if "ids" in args:
        raise Rejected("give ids or a box, not both")

    left, top, right, bottom = as_box(args["box"], ctx)
    name = handler.selection_name(args)
    ids = sorted(
        pixel.id
        for pixel in ctx.pixels()
        if pixel.owner is not None and pixel.owner == player_id and left <= pixel.position.x <= right and top <= pixel.position.y <= bottom
        and (not isinstance(name, str) or refusal(ctx, pixel, player_id, name) is None)
    )

    if not ids:
        raise Rejected("no pixels in the box can do that")

    if len(ids) > MAX_IDS:
        raise Rejected(f"{len(ids)} pixels are in the box; at most {MAX_IDS} per command")

    resolved = {key: value for key, value in args.items() if key != "box"}
    resolved["ids"] = ids
    return resolved


def wake_applied(ctx, outcome):
    """A command that was applied to pixels wakes them if they are asleep (9.3), so an order is taken up at once."""
    if not outcome.ok or not outcome.applied:
        return

    context = ctx.sim.systems.context

    for entity_id in outcome.applied:
        entity = ctx.get_entity(entity_id) if is_int(entity_id) else None

        if entity is not None:
            wake(context, entity)


def execute(ctx, player_id, name, args):
    load_commands()
    handler = COMMANDS.get(name) if isinstance(name, str) else None

    if handler is None:
        return Outcome(False, "unknown command")

    try:
        if handler.selects and isinstance(args, dict) and "box" in args:
            args = resolve_box(ctx, player_id, handler, args)

        outcome = handler.run(ctx, player_id, args)
        wake_applied(ctx, outcome)
        return outcome
    except Rejected as problem:
        return Outcome(False, str(problem))
    except Exception:
        traceback.print_exc()
        return Outcome(False, "the server could not process that command")