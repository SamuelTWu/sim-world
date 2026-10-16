"""Putting things down: whatever a pixel holds goes back into the world.

    drop      inventory -> world      a carried pixel is set down, or a resource becomes a pile pixel on the ground
    pickup    world -> inventory      the other half: a pixel picks up a pixel (a dropped pile is a pixel, so it can be picked up again)
    spawn     creates a NEW pixel for a cost; it never touches an inventory

The action: Action("drop", {"item": {"entity": pixel id} or {"resource": name, "amount": n} or {"all": True}, "x": .., "y": ..}).
    {"entity": id}   a pixel this one is carrying is set down at the spot. If other pixels still hold part of it (it was lifted
                     together), this one only lets go of its share and it stays up until the last one lets go.
    {"resource"..}   up to n of the resource leaves the pixel and becomes a pile pixel (a blueprint holding that resource), so the
                     total never changes. Which blueprint is data: DROP_BLUEPRINTS maps a resource name to a blueprint id, anything
                     not listed becomes DEFAULT_BLUEPRINT. THE BLUEPRINT(S) HAVE TO EXIST (add "resource_pile" to your entities, with a
                     sprite); the pile's slots are raised to fit what was dropped. If the pile cannot be made, the pixel keeps it.
    {"all": True}    everything it holds: every carried pixel, and one pile per resource (resources that DROP_GATES refuse stay).
x/y are optional: left out, it drops next to the pixel; given, the pixel walks to within reach of the spot first (carrying what it
holds). Dropping something it does not hold fails (a pixel with less than `amount` drops what it has). Nothing makes a pixel drop on
its own yet (no generator): only orders use it.

DROP_GATES are checks on what may be dropped: functions (ctx, pixel, resource) returning a reason to refuse, or None. Add
unlock or "not here" rules there. They apply to resources only.
"""
import math

from .behavior import Behavior, Param
from src.simworld.sim.entities import inventory
from ..entities.entity import Vec3
from ..navigation.movement import BLOCKED, clamp_to_world, step_toward
from ..core.sim_context import TILE_UNITS
from ..ai.task import Task, RUNNING, DONE, FAILED

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


PUT_DOWN = "put_down"


class DropTask(Task):
    name = "drop"

    def step(self, entity, context, delta_time):
        item = self.data["item"]

        if "all" in item:
            things = [entry[0] for entry in entity.cargo]
            wanted = {name: amount for name, amount in entity.inventory.items() if amount > 0 and not refusal(context, entity, name)}
        elif "entity" in item:
            things, wanted = [item["entity"]], {}
        else:
            things, wanted = [], {item["resource"]: item["amount"]}

        if (not things and not wanted) or any(entity.inventory.get(name, 0) <= 0 or refusal(context, entity, name) for name in wanted if "resource" in item):
            return FAILED

        if "entity" in item and inventory.pair(entity.cargo, item["entity"]) is None:
            return FAILED

        if "x" in self.data and "y" in self.data:
            x, y = float(self.data["x"]), float(self.data["y"])
            reach = reach_of(entity)

            if math.hypot(entity.position.x - x, entity.position.y - y) > reach:
                return FAILED if step_toward(entity, context, x, y, delta_time, reach * 0.8) == BLOCKED else RUNNING
        else:
            angle = context.rng.uniform(0, math.tau)
            x, y = clamp_to_world(context, entity.position.x + math.cos(angle) * TILE_UNITS * 0.5, entity.position.y + math.sin(angle) * TILE_UNITS * 0.5)

        results = [put_down(context, entity, thing_id, x, y) for thing_id in things]
        results += [materialize(context, entity, name, amount, x, y) for name, amount in sorted(wanted.items())]
        return DONE if any(results) else FAILED


def put_down(context, entity, thing_id, x, y):
    """Let go of a carried pixel. It lands at (x, y) once nobody holds any part of it. Returns True if this pixel let go."""
    thing = context.get_entity(thing_id)

    if thing is None or inventory.pair(thing.carried_by, entity.id) is None:
        return False

    inventory.release(thing, context.get_entity, holder_id=entity.id)

    if not thing.carried_by:
        thing.position = Vec3(x, y, thing.position.z)

    context.events.emit(PUT_DOWN, entity=entity, thing=thing)
    return True


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
    description = "Puts what it carries back into the world: a carried pixel, or resources as a pile. Only orders use it so far."

    params = {
        "reach": Param(default=float(TILE_UNITS), minimum=1.0, maximum=640.0, weight=0.01, description="How close it must be to the spot, in world units"),
    }

    def register(self, runner):
        self.add_task(runner, "drop", lambda entity, action, context: DropTask(**action.data))