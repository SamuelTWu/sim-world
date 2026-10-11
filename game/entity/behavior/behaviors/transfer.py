"""Moving something that ALREADY EXISTS from one holder to another. Nothing is created or destroyed, so totals never change:
    a resource       from one inventory to another
    an entity        onto carriers (a settlement onto 4 pixels, a passenger onto a boat), between carriers, or off them
It is not `spawn` (creates a new pixel, for a cost) and not `drop` (makes something from the inventory exist in the
world). All the slot rules are in entity/inventory.py; this file decides who may reach what.

The action: Action("transfer", {"item": {"resource": name, "amount": n} or {"entity": id}, "from": id or None,
"to": id, [x, y] or None, "with": [pixel ids] (optional)}). `from` / `to` that are missing mean "the acting pixel(s)":
    {"resource": "iron", "amount": 3}, to = B         the pixel gives up to 3 iron to B
    {"resource": "iron", "amount": 3}, from = B       the pixel takes up to 3 iron from B
    {"entity": settlement}                            the pixels pick it up together (their free slots add up)
    {"entity": passenger}, to = boat                  put it on the boat
    {"entity": settlement}, from = A                  take it off A and onto the acting pixels (hand-over)
    {"entity": passenger}, to = [x, y]                set it down there (it was being carried)
For an entity, "with" lists the pixels acting together. Each of them runs its own task and walks to the spot; the first one
to find everybody in reach does the whole move, and the others find it already done. Resources never use "with".

transfer_step(ctx, actors, order) does one try. It returns (status, detail):
    "gone"      something it needs no longer exists (or no acting pixel is left)
    "approach"  somebody is too far away: detail is the (x, y) to go to
    "blocked"   it cannot work (nothing to move, no room, does not fit): detail says why
    "done"      it happened: detail is how much was moved (resources) or True (entities)
A pixel's reach is its "transfer" trait: "traits": {"transfer": {"reach": 48}}.
Nothing makes a pixel transfer on its own yet (no generator): only orders use it.
"""
import math

from ..behavior import Behavior, Param
import game.entity.inventory as inventory
from ...entity import Vec3
from ...system.movement import BLOCKED, step_toward
from ...system.simContext import TILE_UNITS
from ...system.task import Task, RUNNING, DONE, FAILED

DEFAULT_REACH = float(TILE_UNITS)
BLOCKED_PATIENCE = 1.0
WAIT_PATIENCE = 60.0


def reach_of(pixel):
    value = pixel.trait("transfer", "reach", DEFAULT_REACH)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else DEFAULT_REACH


def away(entity, x, y):
    return math.hypot(entity.position.x - x, entity.position.y - y)


def far_spot(actors, spots):
    """The first (x, y) in spots that some acting pixel is too far from, or None if everyone is in reach of all of them."""
    for x, y in spots:
        if any(away(actor, x, y) > reach_of(actor) for actor in actors):
            return x, y

    return None


def spot(entity):
    return entity.position.x, entity.position.y


def alive(entity):
    return entity is not None and entity.alive


def is_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def transfer_step(ctx, actors, order):
    lookup = ctx.get_entity
    actors = [actor for actor in actors if actor.alive]
    item, from_id, to = order["item"], order.get("from"), order.get("to")

    if not actors:
        return "gone", "no pixel left to do it"

    source = lookup(from_id) if from_id is not None else None
    target = lookup(to) if is_id(to) else None

    if (from_id is not None and not alive(source)) or (is_id(to) and not alive(target)):
        return "gone", "the other pixel is gone"

    if "resource" in item:
        return move_resource(actors, item, source, target)

    thing = lookup(item["entity"])

    if not alive(thing):
        return "gone", "the thing to move is gone"

    if isinstance(to, (list, tuple)):
        return set_down(lookup, actors, thing, source, to)

    return load_onto(lookup, actors, thing, source, target)


def move_resource(actors, item, source, target):
    name, amount = item["resource"], item["amount"]
    other = source or target
    far = far_spot(actors, [spot(other)]) if other is not None else None

    if far is not None:
        return "approach", far

    moved = sum(inventory.transfer_resource(source or actor, target or actor, name, amount) for actor in actors)
    return ("done", moved) if moved > 0 else ("blocked", f"no {name} to move, or no room for it")


def load_onto(lookup, actors, thing, source, target):
    holders = [target] if target is not None else actors

    if thing.carried_by and inventory.is_loaded(thing) and all(inventory.pair(thing.carried_by, holder.id) for holder in holders):
        return "done", True

    carried_by_actors = bool(thing.carried_by) and all(inventory.pair(thing.carried_by, actor.id) for actor in actors)
    spots = [] if carried_by_actors else [spot(thing)]
    spots += [spot(entity) for entity in (source, target) if entity is not None]
    far = far_spot(actors, spots)

    if far is not None:
        return "approach", far

    if thing.carried_by and source is None:
        return "blocked", "it is already being carried: say who is carrying it (from)"

    if source is not None and inventory.pair(thing.carried_by, source.id) is None:
        return "blocked", "that pixel is not carrying it"

    if any(holder.id == thing.id for holder in holders):
        return "blocked", "a thing cannot carry itself"

    before = [list(entry) for entry in thing.carried_by]
    entry = inventory.pair(thing.carried_by, source.id) if source is not None else None
    needed = thing.size - (sum(slots for _, slots in before) - (entry[1] if entry else 0))

    if source is not None:
        inventory.release(thing, lookup, holder_id=source.id)

    if inventory.load(thing, holders, lookup):
        return "done", True

    for holder_id, slots in before:
        holder = lookup(holder_id)

        if holder is not None:
            inventory.set_pair(holder.cargo, thing.id, slots)

    thing.carried_by[:] = before
    free = sum(inventory.slots_free(holder) for holder in holders if holder.alive)
    return "blocked", f"it does not fit: it needs {needed} slots and {free} are free"


def set_down(lookup, actors, thing, source, point):
    x, y = float(point[0]), float(point[1])

    if not thing.carried_by:
        return ("done", True) if away(thing, x, y) <= 1.0 else ("blocked", "it is not being carried")

    if source is not None and inventory.pair(thing.carried_by, source.id) is None:
        return "blocked", "that pixel is not carrying it"

    far = far_spot(actors, [spot(thing), (x, y)])

    if far is not None:
        return "approach", far

    inventory.release(thing, lookup, holder_id=source.id if source is not None else None)

    if not thing.carried_by:
        thing.position = Vec3(x, y, thing.position.z)

    return "done", True


class TransferTask(Task):
    name = "transfer"

    def __init__(self, **data):
        super().__init__(**data)
        self.blocked_for = 0.0

    def actors(self, entity, context):
        ids = self.data.get("with")

        if "resource" in self.data["item"] or not ids:
            return [entity]

        group = [context.get_entity(entity_id) for entity_id in ids]
        return [entity] + [other for other in group if alive(other) and other is not entity]

    def step(self, entity, context, delta_time):
        order = {"item": self.data["item"], "from": self.data.get("from"), "to": self.data.get("to")}
        status, detail = transfer_step(context, self.actors(entity, context), order)

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


class Transfer(Behavior):
    name = "transfer"
    kind = "action"
    tier = 1
    base_cost = 1.0
    description = "Gives, takes, picks up, loads and sets down things that already exist. Only orders use it so far."

    params = {
        "reach": Param(default=float(TILE_UNITS), minimum=1.0, maximum=640.0, weight=0.01, description="How close it must be, in world units"),
    }

    def register(self, runner):
        self.add_task(runner, "transfer", lambda entity, action, context: TransferTask(**action.data))