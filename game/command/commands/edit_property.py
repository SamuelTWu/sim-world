import copy

from ...entity import inventory
from ...entity.behavior.behavior import BlueprintError
from ..command import Command, Outcome, Rejected, clean_args, command, is_int, is_number

# DUMMY prices: what one more unit of a stat costs. Real numbers (and real currency) come with Phase 5.5.
STAT_PRICES = {"health": 1.0, "energy": 1.0, "slots": 2.0, "size": 0.0}
STAT_LIMITS = {"health": (1.0, 1000.0), "energy": (1.0, 1000.0), "slots": (0, 99), "size": (1, 99)}
WHOLE_STATS = ("slots", "size")
MAX_CHANGES = 32
EDIT_GATES = []
EDIT_UNLOCKED = None  # None = every behavior counts as unlocked (dummy until the tech tree decides, Phase 5.5)
PROPERTY_EDITED = "property_edited"


def pay_edit_cost(ctx, player_id, cost):
    """DUMMY: upgrades are free. Later: take `cost` from the player's currency and return False if they cannot pay."""
    return True


def gate_unlocks(ctx, player_id, pixel, changes, cost):
    """DUMMY: every behavior may be added and every stat raised. Later: refuse what the player's tech tree has not unlocked."""
    return None


EDIT_GATES.append(gate_unlocks)


def contents(ctx, pixel):
    """What fills the pixel's slots, one entry per slot used (so the panel can draw them): resources first, then carried pixels.
    {"kind": "resource", "key": name, "label": "iron x3", "amount": 3} or {"kind": "pixel", "key": sprite id, "label": "Fast Runner #7", "id": 7}."""
    slots = []

    for name, amount in sorted(pixel.inventory.items()):
        left = amount

        for _ in range(inventory.whole_slots(name, amount)):
            here = min(left, inventory.stack_size(name))
            left -= here
            slots.append({"kind": "resource", "key": name, "label": f"{name} x{round(here, 2):g}" + (f" (of {round(amount, 2):g})" if here != amount else ""), "amount": here})

    for held_id, count in pixel.cargo:
        held = ctx.get_entity(held_id)
        label = f"{held.name} #{held_id}" if held is not None else f"#{held_id}"

        for _ in range(count):
            slots.append({"kind": "pixel", "key": held.sprite_id if held is not None else "", "label": label + (f" ({count} slots)" if count > 1 else ""), "id": held_id})

    return slots


def describe(ctx, pixel):
    """Everything the client needs to show and edit a pixel: its stats, behaviors with their parameters, what it holds, and the prices."""
    return {
        "id": pixel.id,
        "name": pixel.name,
        "blueprint": pixel.blueprint_name or "",
        "sprite_id": pixel.sprite_id,
        "stats": {"health": pixel.max_health, "energy": pixel.max_energy, "slots": pixel.slots, "size": pixel.size},
        "now": {"health": pixel.health, "energy": pixel.energy},
        "traits": copy.deepcopy(pixel.traits),
        "inventory": dict(pixel.inventory),
        "cargo": [entry[0] for entry in pixel.cargo],
        "contents": contents(ctx, pixel),
        "slots_used": inventory.slots_used(pixel),
        "carried": bool(pixel.carried_by),
        "prices": dict(STAT_PRICES),
        "limits": {key: list(value) for key, value in STAT_LIMITS.items()},
    }


def own_pixel(ctx, player_id, pixel_id):
    """The pixel, if it exists, is alive and is yours. One message for all three, so ids cannot be probed."""
    pixel = ctx.get_entity(pixel_id) if is_int(pixel_id) else None

    if pixel is None or not pixel.alive or pixel.owner is None or pixel.owner != player_id:
        raise Rejected("unavailable")

    return pixel


@command
class Inspect(Command):
    """Ask for one of your pixels' attributes. args: {"id": pixel id}. Changes nothing; the server answers with an "entity_info" message
    (the same data `edit_property` returns). Only your own pixels can be inspected, because the client only knows those (Phase 7 widens this)."""

    name = "inspect"
    selects = False

    def run(self, ctx, player_id, args):
        clean_args(args, "id")
        return Outcome(True, applied=[args["id"]], info=describe(ctx, own_pixel(ctx, player_id, args["id"])))


@command
class EditProperty(Command):
    """Change ("upgrade") one of your pixels' attributes for a cost. args: {"id": pixel id, "set": {path: value, ...}}.

    Paths: "health", "energy" (the maximums), "slots", "size", "traits.<behavior>.<parameter>" to change a behavior's setting, and
    "traits.<behavior>" with a map of parameters ({} for the defaults) to give the pixel a behavior it does not have yet.
    Removing a behavior is not possible. Everything in one command happens together or not at all.

    Checks: the pixel must be yours and alive; every behavior setting is validated by the behavior manager (range, type,
    required behaviors); stats stay inside STAT_LIMITS; slots cannot drop below what the pixel holds, and size cannot change
    while it is being carried. Nothing to change is refused.

    Cost: the behavior manager's price of the new behaviors/settings minus the old (a downgrade never earns anything back), plus
    STAT_PRICES per unit a stat goes up. EDIT_GATES are checks run last: functions (ctx, player_id, pixel, changes, cost) that return a
    reason to refuse, or None. Two things are DUMMIES for now: gate_unlocks (always passes) and pay_edit_cost (free). Raising
    health or energy raises the current value by the same amount; lowering the maximum caps the current value.

    Changed behaviors are re-applied to the pixel (BehaviorManager.apply), so a new speed takes effect straight away. The answer is
    an "entity_info" message with the pixel's new attributes and "paid" (the cost).
    """

    name = "edit_property"
    selects = False

    def run(self, ctx, player_id, args):
        clean_args(args, "id", "set")
        pixel = own_pixel(ctx, player_id, args["id"])
        changes = args["set"]

        if not isinstance(changes, dict) or not changes:
            raise Rejected("nothing to change")

        if len(changes) > MAX_CHANGES:
            raise Rejected(f"at most {MAX_CHANGES} changes per command")

        stats, traits = {}, copy.deepcopy(pixel.traits)

        for path, value in changes.items():
            self.read_change(path, value, stats, traits)

        manager = ctx.behaviors

        try:
            old_cost = manager.cost(pixel.traits)
            checked = manager.validate_blueprint({"traits": traits}, unlocked=EDIT_UNLOCKED)["traits"]
            new_cost = manager.cost(checked)
        except BlueprintError as problem:
            raise Rejected(str(problem)) from None

        cost = max(0.0, new_cost - old_cost) + self.check_stats(pixel, stats)
        current = {"health": pixel.max_health, "energy": pixel.max_energy, "slots": pixel.slots, "size": pixel.size}
        stats = {key: value for key, value in stats.items() if value != current[key]}
        touched = [name for name in checked if checked[name] != pixel.traits.get(name)]

        if not touched and not stats:
            raise Rejected("nothing to change")

        for gate in EDIT_GATES:
            reason = gate(ctx, player_id, pixel, changes, cost)

            if reason:
                raise Rejected(reason)

        if not pay_edit_cost(ctx, player_id, cost):
            raise Rejected("you cannot afford that")

        for name in touched:
            if name in pixel.traits:
                manager.get(name).remove(pixel)

            pixel.traits[name] = checked[name]

        manager.apply(pixel)
        self.apply_stats(pixel, stats)
        events = ctx.events

        if events is not None:
            events.emit(PROPERTY_EDITED, entity=pixel, changes=dict(changes), cost=cost)

        info = describe(ctx, pixel)
        info["paid"] = round(cost, 4)
        return Outcome(True, applied=[pixel.id], info=info)

    @staticmethod
    def read_change(path, value, stats, traits):
        if not isinstance(path, str):
            raise Rejected("a property path must be text")

        parts = path.split(".")

        if len(parts) == 1 and path in STAT_LIMITS:
            if not is_number(value):
                raise Rejected(f"{path} must be a number")

            stats[path] = value
        elif parts[0] == "traits" and len(parts) == 3:
            if not isinstance(traits.get(parts[1]), dict):
                raise Rejected(f"it has no '{parts[1]}' behavior to change (add it first)")

            traits[parts[1]][parts[2]] = value
        elif parts[0] == "traits" and len(parts) == 2:
            if parts[1] in traits:
                raise Rejected(f"it already has '{parts[1]}'")

            if not isinstance(value, dict):
                raise Rejected(f"{path} must be a map of settings ({{}} for the defaults)")

            traits[parts[1]] = value
        else:
            raise Rejected(f"you cannot change '{path}'")

    @staticmethod
    def check_stats(pixel, stats):
        """Refuses stat values that are out of range or impossible right now. Returns what the increases cost."""
        cost = 0.0
        current = {"health": pixel.max_health, "energy": pixel.max_energy, "slots": pixel.slots, "size": pixel.size}

        for key, value in stats.items():
            low, high = STAT_LIMITS[key]

            if key in WHOLE_STATS and not is_int(value):
                raise Rejected(f"{key} must be a whole number")

            if not low <= value <= high:
                raise Rejected(f"{key} must be from {low} to {high}")

            if key == "slots" and value < inventory.slots_used(pixel):
                raise Rejected(f"it holds {inventory.slots_used(pixel)} slots' worth: put some down first")

            if key == "size" and value != pixel.size and pixel.carried_by:
                raise Rejected("its size cannot change while it is being carried")

            cost += max(0.0, value - current[key]) * STAT_PRICES[key]

        return cost

    @staticmethod
    def apply_stats(pixel, stats):
        if "health" in stats:
            pixel.health = min(stats["health"], pixel.health + max(0.0, stats["health"] - pixel.max_health))
            pixel.max_health = float(stats["health"])

        if "energy" in stats:
            pixel.energy = min(stats["energy"], pixel.energy + max(0.0, stats["energy"] - pixel.max_energy))
            pixel.max_energy = float(stats["energy"])

        for key in WHOLE_STATS:
            if key in stats:
                setattr(pixel, key, stats[key])