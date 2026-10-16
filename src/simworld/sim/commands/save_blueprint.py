import math
import re

from ..behaviors.behavior import BlueprintError
from .command import Command, Outcome, Rejected, clean_args, command, is_number

SAVE_GATES = []
SAVE_UNLOCKED = None  # None = every behavior counts as unlocked (dummy until the tech tree decides, Phase 5.5)

MAX_NAME = 40
MAX_JSON_DEPTH = 4
MAX_STRING = 64
MAX_ENTRIES = 64
ALLOWED_KEYS = {"name", "tags", "maxHealth", "maxEnergy", "slots", "size", "sprite", "traits", "props", "needs", "inventory"}
SPRITE_KEYS = {"shape", "color", "size", "layer"}


def blueprint_id(name):
    """"Fast Runner!" -> "fast_runner". Only letters, digits and underscores, so it is always a safe file name and a valid id."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48]


def gate_currency(ctx, player_id, blueprint_id, definition, cost):
    """DUMMY: saving is free. Later: take `cost` (the behavior manager's price of the blueprint) from the player's currency, or refuse."""
    return None


def gate_unlocks(ctx, player_id, blueprint_id, definition, cost):
    """DUMMY: every behavior is allowed. Later: refuse behaviors the player's tech tree has not unlocked.
    (BehaviorManager.validate_blueprint already takes an `unlocked` set: pass it through SAVE_UNLOCKED or compute it here.)"""
    return None


SAVE_GATES.extend([gate_currency, gate_unlocks])


def check_json(value, path="blueprint", depth=0):
    """Plain data only, small, finite numbers. The behavior manager checks the meaning of traits; this checks the shape of everything."""
    if depth > MAX_JSON_DEPTH:
        raise Rejected(f"{path} is nested too deeply")

    if isinstance(value, bool) or value is None:
        return

    if isinstance(value, (int, float)):
        if not math.isfinite(value) or abs(value) > 1e9:
            raise Rejected(f"{path} must be a reasonable number")

        return

    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise Rejected(f"{path} is too long")

        return

    if isinstance(value, list):
        if len(value) > MAX_ENTRIES:
            raise Rejected(f"{path} has too many entries")

        for index, item in enumerate(value):
            check_json(item, f"{path}[{index}]", depth + 1)

        return

    if isinstance(value, dict):
        if len(value) > MAX_ENTRIES:
            raise Rejected(f"{path} has too many entries")

        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_STRING:
                raise Rejected(f"{path} has a bad key")

            check_json(item, f"{path}.{key}", depth + 1)

        return

    raise Rejected(f"{path} has a value that cannot be saved")


def check_sprite(sprite):
    if not isinstance(sprite, dict) or not set(sprite) <= SPRITE_KEYS:
        raise Rejected("the sprite may only have shape, color, size and layer")

    color = sprite.get("color", [255, 255, 255])

    if not (isinstance(color, list) and len(color) == 3 and all(isinstance(part, int) and not isinstance(part, bool) and 0 <= part <= 255 for part in color)):
        raise Rejected("the sprite color must be [red, green, blue], each 0 to 255")

    size = sprite.get("size", [16, 16])

    if not (isinstance(size, list) and len(size) == 2 and all(is_number(part) and 4 <= part <= 128 for part in size)):
        raise Rejected("the sprite size must be [width, height], each 4 to 128")

    shape = sprite.get("shape")

    if shape is not None and not (isinstance(shape, list) and 3 <= len(shape) <= 16 and all(isinstance(point, list) and len(point) == 2 and all(is_number(part) and -1.0 <= part <= 1.0 for part in point) for point in shape)):
        raise Rejected("the sprite shape must be 3 to 16 points [x, y], each between -1 and 1")

    layer = sprite.get("layer", 0)

    if not isinstance(layer, int) or isinstance(layer, bool) or not 0 <= layer <= 9:
        raise Rejected("the sprite layer must be a whole number from 0 to 9")


def check_counts(definition):
    for key in ("slots", "size"):
        if key in definition and (not isinstance(definition[key], int) or isinstance(definition[key], bool) or not (0 if key == "slots" else 1) <= definition[key] <= 99):
            raise Rejected(f"{key} must be a whole number" + (" from 0 to 99" if key == "slots" else " from 1 to 99"))

    for key in ("maxHealth", "maxEnergy"):
        if key in definition and (not is_number(definition[key]) or not 0 < definition[key] <= 100000):
            raise Rejected(f"{key} must be a number above 0")

    inventory = definition.get("inventory", {})

    if not isinstance(inventory, dict) or not all(isinstance(item, str) and item and isinstance(count, int) and not isinstance(count, bool) and 0 < count <= 9999 for item, count in inventory.items()):
        raise Rejected("the inventory must map item names to whole numbers above 0")

    if "tags" in definition and not (isinstance(definition["tags"], list) and all(isinstance(tag, str) for tag in definition["tags"])):
        raise Rejected("tags must be a list of words")

    for key in ("props", "needs", "traits"):
        if key in definition and not isinstance(definition[key], dict):
            raise Rejected(f"{key} must be a map")

    for need_name, need in definition.get("needs", {}).items():
        if not (isinstance(need, dict) and set(need) <= {"value", "rate", "minimum", "maximum"} and all(is_number(number) for number in need.values())):
            raise Rejected(f"need '{need_name}' must be numbers for value, rate, minimum and maximum")

    for trait_name, values in definition.get("traits", {}).items():
        if not isinstance(values, dict):
            raise Rejected(f"trait '{trait_name}' must be a map of parameters")


@command
class SaveBlueprint(Command):
    """The PLAYER saves a new blueprint (a pixel design). args: {"name": text, "definition": {...the blueprint...}}.

    The blueprint is written to game/entity/entities/<id>.json, where <id> is made from the name ("Fast Runner" -> fast_runner),
    which is the same folder every other blueprint lives in, so it can be placed on the map straight away. It never overwrites
    an existing blueprint: a name that is taken is refused.

    The definition may only contain: name, tags, maxHealth, maxEnergy, slots, size, sprite, traits, props, needs, inventory.
    (Everything else a JSON file can hold, such as owner, components and position, is not for players to set.) It is checked
    for shape (check_json, check_sprite, check_counts) and then by the behavior manager: unknown behaviors or parameters,
    values out of range, and missing required behaviors are refused with its message. The saved file has the manager's
    normalized traits (every parameter filled in).

    Like place, this is the player's own power: it needs no pixel and no command trait, so `selects` is off.
    SAVE_GATES are checks run last: functions (ctx, player_id, blueprint_id, definition, cost) that return a reason to
    refuse, or None. Two are DUMMIES for now and always pass: gate_currency (charge the blueprint's cost) and gate_unlocks
    (only allow unlocked behaviors). Fill them in when currency and the tech tree exist (Phase 5.5); `cost` is already
    the behavior manager's price for the design.
    """

    name = "save_blueprint"
    selects = False

    def run(self, ctx, player_id, args):
        clean_args(args, "name", "definition")
        name, definition = args["name"], args["definition"]

        if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_NAME or not name.isprintable():
            raise Rejected(f"give the blueprint a name of 1 to {MAX_NAME} letters, digits or spaces")

        name = " ".join(name.split())
        new_id = blueprint_id(name)

        if not new_id:
            raise Rejected("the name needs at least one letter or digit")

        if not isinstance(definition, dict):
            raise Rejected("the blueprint must be a map")

        extra = sorted(set(definition) - ALLOWED_KEYS)

        if extra:
            raise Rejected(f"a blueprint may not set: {extra}")

        check_json(definition)
        check_counts(definition)

        if "sprite" in definition:
            check_sprite(definition["sprite"])

        if ctx.blueprint_exists(new_id):
            raise Rejected(f"there is already a blueprint called '{new_id}': pick another name")

        try:
            checked = ctx.behaviors.validate_blueprint(definition, unlocked=SAVE_UNLOCKED)
            cost = ctx.behaviors.cost(checked.get("traits", {}))
        except BlueprintError as problem:
            raise Rejected(str(problem)) from None

        checked["name"] = name

        for gate in SAVE_GATES:
            reason = gate(ctx, player_id, new_id, checked, cost)

            if reason:
                raise Rejected(reason)

        try:
            ctx.write_blueprint(new_id, checked)
        except FileExistsError:
            raise Rejected(f"there is already a blueprint called '{new_id}': pick another name") from None
        except OSError:
            raise Rejected("the server could not write the blueprint file") from None

        return Outcome(True, applied=[new_id])