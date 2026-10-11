"""Materializing something from a pixel's inventory into the world.

    drop      inventory -> world      the resource leaves the pixel and becomes a pile pixel on the ground
    transfer  moves something that already exists (a pile can be picked up again with transfer)
    spawn     creates a NEW pixel for a cost; it never touches an inventory

A drop moves resources out of the pixel and creates a pile pixel (a blueprint holding that resource) where it lands, so the
total amount never changes. Which blueprint a resource becomes is data: DROP_BLUEPRINTS maps a resource name to a blueprint
id, anything not listed becomes DEFAULT_BLUEPRINT. THE BLUEPRINT(S) HAVE TO EXIST (add "resource_pile" to your entities,
with a sprite); the pile's slots are raised to fit what was dropped. If the pile cannot be made, the pixel keeps its resource.

The action: Action("drop", {"item": {"resource": name, "amount": n} or {"all": True}, "x": .., "y": ..}). {"all": True} puts
everything the pixel holds on the ground, one pile per resource (resources that DROP_GATES refuse stay with it). x/y are optional: left out, it
drops next to the pixel; given, the pixel walks to within reach of the spot first. A pixel with less than `amount` drops what
it has; with none, the task fails. Only resources are dropped: putting a pixel or structure down is `transfer` (to a point).
Nothing makes a pixel drop on its own yet (no generator): only orders use it.

DROP_GATES are checks on what may be dropped: functions (ctx, pixel, resource) returning a reason to refuse, or None. Add
unlock or "not here" rules there.
"""
import math

from ..behavior import Behavior, Param
from ... import inventory
from ...system.movement import BLOCKED, clamp_to_world, step_toward
from ...system.simContext import TILE_UNITS
from ...system.task import Task, RUNNING, DONE, FAILED

DEFAULT_BLUEPRINT = "resource_pile"
DROP_BLUEPRINTS = {}
DROP_GATES = []
DROPPED = "dropped"


def refusal(ctx, pixel, resource):
    for gate in DROP_GATES:
        reason = gate(ctx, pixel, resource)

        if reason:
            return reason

    return None


def reach_of(pixel):
    return float(pixel.trait("drop", "reach", TILE_UNITS))


class DropTask(Task):
    name = "drop"

    def step(self, entity, context, delta_time):
        item = self.data["item"]
        wanted = {name: amount for name, amount in entity.inventory.items() if amount > 0 and not refusal(context, entity, name)} if "all" in item else {item["resource"]: item["amount"]}

        if not wanted or any(entity.inventory.get(name, 0) <= 0 or refusal(context, entity, name) for name in wanted):
            return FAILED

        if "x" in self.data and "y" in self.data:
            x, y = float(self.data["x"]), float(self.data["y"])
            reach = reach_of(entity)

            if math.hypot(entity.position.x - x, entity.position.y - y) > reach:
                return FAILED if step_toward(entity, context, x, y, delta_time, reach * 0.8) == BLOCKED else RUNNING
        else:
            angle = context.rng.uniform(0, math.tau)
            x, y = clamp_to_world(context, entity.position.x + math.cos(angle) * TILE_UNITS * 0.5, entity.position.y + math.sin(angle) * TILE_UNITS * 0.5)

        results = [materialize(context, entity, name, amount, x, y) for name, amount in sorted(wanted.items())]
        return DONE if any(results) else FAILED


def materialize(context, entity, name, amount, x, y):
    """Turn up to `amount` of the pixel's resource into a pile at (x, y). Returns True if it happened; otherwise nothing changed."""
    definition = context.load_blueprint(DROP_BLUEPRINTS.get(name, DEFAULT_BLUEPRINT))

    if definition is None:
        return False

    taken = inventory.remove_resource(entity, name, amount)

    if taken <= 0:
        return False

    definition = dict(definition)
    definition["slots"] = max(definition.get("slots", 0) if isinstance(definition.get("slots"), int) else 0, inventory.whole_slots(name, taken))
    pile = context.spawn(definition, entity.owner, x, y)

    if inventory.add_resource(pile, name, taken) != taken:
        inventory.add_resource(entity, name, taken)
        context.entities.kill(pile.id)
        return False

    context.events.emit(DROPPED, entity=entity, pile=pile, resource=name, amount=taken)
    return True


class Drop(Behavior):
    name = "drop"
    kind = "action"
    tier = 1
    base_cost = 1.0
    description = "Puts resources from its inventory on the ground as a pile. Only orders use it so far."

    params = {
        "reach": Param(default=float(TILE_UNITS), minimum=1.0, maximum=640.0, weight=0.01, description="How close it must be to the spot, in world units"),
    }

    def register(self, runner):
        self.add_task(runner, "drop", lambda entity, action, context: DropTask(**action.data))