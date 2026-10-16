"""Picking up a pixel: it goes into the pickup pixel's inventory (cargo) and stays there until it is dropped.

Everything that used to be a "transfer" is this plus `drop`: a pixel picks something up, carries it, and puts it down
somewhere else. Nothing is created or destroyed. It is not `spawn` (creates a NEW pixel, for a cost). All the slot rules
are in entity/inventory.py (a held pixel takes `size` slots of its holder, so a pixel with 5 free slots cannot pick up a
size-20 settlement alone, but 4 pixels can lift it together).

The action: Action("pickup", {"target": pixel id, "with": [pixel ids] (optional)}). "with" lists the pixels lifting
together. Each of them runs its own task and walks to the target; the first one to find everybody in reach does the whole
pickup, and the others find it already done.

pickup_step(ctx, actors, target_id) does one try. It returns (status, detail):
    "gone"      the target no longer exists (or no acting pixel is left)
    "approach"  somebody is too far away: detail is the (x, y) to go to
    "blocked"   it cannot work (already carried by someone, does not fit, would carry itself): detail says why
    "done"      the target is held by every acting pixel (it may already have been)
A pixel's reach is its "pickup" trait: "traits": {"pickup": {"reach": 48}}.
Nothing makes a pixel pick things up on its own yet (no generator): only orders use it.
"""
import math

from .behavior import Behavior, Param
from src.simworld.sim.entities import inventory
from ..navigation.movement import BLOCKED, step_toward
from ..core.sim_context import TILE_UNITS
from ..ai.task import Task, RUNNING, DONE, FAILED

DEFAULT_REACH = float(TILE_UNITS)
BLOCKED_PATIENCE = 1.0
WAIT_PATIENCE = 60.0
PICKED_UP = "picked_up"


def reach_of(pixel):
    value = pixel.trait("pickup", "reach", DEFAULT_REACH)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else DEFAULT_REACH


def away(entity, x, y):
    return math.hypot(entity.position.x - x, entity.position.y - y)


def pickup_step(ctx, actors, target_id):
    actors = [actor for actor in actors if actor.alive]

    if not actors:
        return "gone", "no pixel left to do it"

    thing = ctx.get_entity(target_id)

    if thing is None or not thing.alive:
        return "gone", "the thing to pick up is gone"

    if any(actor.id == thing.id for actor in actors):
        return "blocked", "a pixel cannot pick itself up"

    if thing.carried_by and inventory.is_loaded(thing) and all(inventory.pair(thing.carried_by, actor.id) for actor in actors):
        return "done", True

    if any(entry[0] not in {actor.id for actor in actors} for entry in thing.carried_by):
        return "blocked", "somebody else is carrying it"

    far = next(((thing.position.x, thing.position.y) for actor in actors if away(actor, thing.position.x, thing.position.y) > reach_of(actor)), None)

    if far is not None:
        return "approach", far

    if inventory.load(thing, actors, ctx.get_entity):
        ctx.events.emit(PICKED_UP, entity=actors[0], thing=thing)
        return "done", True

    free = sum(inventory.slots_free(actor) for actor in actors)
    return "blocked", f"it does not fit: it needs {thing.size - inventory.carried_slots(thing)} slots and {free} are free"


class PickupTask(Task):
    name = "pickup"

    def __init__(self, **data):
        super().__init__(**data)
        self.blocked_for = 0.0

    def actors(self, entity, context):
        group = [context.get_entity(entity_id) for entity_id in self.data.get("with") or ()]
        return [entity] + [other for other in group if other is not None and other.alive and other is not entity]

    def step(self, entity, context, delta_time):
        status, detail = pickup_step(context, self.actors(entity, context), self.data["target"])

        if status == "done":
            return DONE

        if status == "gone":
            return FAILED

        if status == "blocked":
            self.blocked_for += delta_time
            return FAILED if self.blocked_for > BLOCKED_PATIENCE else RUNNING

        self.blocked_for = 0.0

        if self.elapsed > WAIT_PATIENCE:
            return FAILED

        x, y = detail

        if away(entity, x, y) > reach_of(entity):
            return FAILED if step_toward(entity, context, x, y, delta_time, reach_of(entity) * 0.8) == BLOCKED else RUNNING

        return RUNNING


class Pickup(Behavior):
    name = "pickup"
    kind = "action"
    tier = 1
    base_cost = 1.0
    description = "Picks up another pixel and carries it in its inventory until it drops it. Only orders use it so far."

    params = {
        "reach": Param(default=float(TILE_UNITS), minimum=1.0, maximum=640.0, weight=0.01, description="How close it must be, in world units"),
    }

    def register(self, runner):
        self.add_task(runner, "pickup", lambda entity, action, context: PickupTask(**action.data))