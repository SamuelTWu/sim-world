"""Carrying out a transfer order. The `transfer` command only stores the order; this does the moving.

A transfer moves something that ALREADY EXISTS (nothing is created or destroyed, so the totals never change):
    a resource       from one inventory to another
    an entity        onto carriers (a settlement onto 4 pixels, a passenger onto a boat), between carriers, or off them
It is not `spawn` (creates a new pixel, for a cost) and not `drop` (makes something from the inventory exist in the
world). All the slot rules are in entity/inventory.py; this file only decides who may reach what.

The order (see commands/transfer.py): {"kind": "transfer", "item": {"resource": name, "amount": n} or {"entity": id},
"from": id or None, "to": id, [x, y] or None, ...}. `from` and `to` that are missing mean "the acting pixel(s)":
    {"resource": "iron", "amount": 3}, to = B         each acting pixel gives up to 3 iron to B
    {"resource": "iron", "amount": 3}, from = B       each acting pixel takes up to 3 iron from B
    {"entity": settlement}                            the acting pixels pick it up together (their free slots add up)
    {"entity": passenger}, to = boat                  put it on the boat
    {"entity": settlement}, from = A                  take it off A and onto the acting pixels (hand-over)
    {"entity": passenger}, to = [x, y]                set it down there (it was being carried)

Whatever carries orders out should call `transfer_step(ctx, actors, order)` each tick. It returns (status, detail):
    "gone"      something it needs no longer exists (or no acting pixel is left): drop the order
    "approach"  somebody is too far away: move the acting pixels closer (reach is `reach_of`)
    "blocked"   it cannot work (nothing to move, no room, does not fit): detail says why. Retry or give up.
    "done"      it happened: detail is how much was moved (resources) or True (entities)
A pixel's "reach" can be changed with a "transfer" trait: "traits": {"transfer": {"reach": 48}}.
"""
import math

from ..entity import inventory
from ..entity.entity import Vec3
from ..entity.system.simContext import TILE_UNITS

TRAIT = "transfer"
DEFAULT_REACH = float(TILE_UNITS)


def reach_of(pixel):
    trait = pixel.traits.get(TRAIT)
    value = trait.get("reach") if isinstance(trait, dict) else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else DEFAULT_REACH


def away(entity, x, y):
    return math.hypot(entity.position.x - x, entity.position.y - y)


def all_near(actors, spots):
    """True if every acting pixel is within its reach of every (x, y) in spots."""
    return all(away(actor, x, y) <= reach_of(actor) for actor in actors for x, y in spots)


def spot(entity):
    return entity.position.x, entity.position.y


def alive(entity):
    return entity is not None and entity.alive


def transfer_step(ctx, actors, order):
    lookup = ctx.get_entity
    actors = [actor for actor in actors if actor.alive]
    item, from_id, to = order["item"], order.get("from"), order.get("to")

    if not actors:
        return "gone", "no pixel left to do it"

    source = lookup(from_id) if from_id is not None else None
    target = lookup(to) if isinstance(to, int) and not isinstance(to, bool) else None

    if (from_id is not None and not alive(source)) or (isinstance(to, int) and not isinstance(to, bool) and not alive(target)):
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
    pairs = [(source or actor, target or actor) for actor in actors]
    other = source or target

    if other is not None and not all_near(actors, [spot(other)]):
        return "approach", "too far from the other pixel"

    moved = sum(inventory.transfer_resource(giver, taker, name, amount) for giver, taker in pairs)
    return ("done", moved) if moved > 0 else ("blocked", f"no {name} to move, or no room for it")


def load_onto(lookup, actors, thing, source, target):
    holders = [target] if target is not None else actors
    carried_by_actors = {entity_id for entity_id, _ in thing.carried_by} >= {actor.id for actor in actors} and bool(thing.carried_by)
    spots = [] if carried_by_actors else [spot(thing)]
    spots += [spot(entity) for entity in (source, target) if entity is not None]

    if spots and not all_near(actors, spots):
        return "approach", "too far away"

    if thing.carried_by and source is None:
        return "blocked", "it is already being carried: say who is carrying it (from)"

    if source is not None and inventory.pair(thing.carried_by, source.id) is None:
        return "blocked", "that pixel is not carrying it"

    if any(holder.id == thing.id for holder in holders):
        return "blocked", "a thing cannot carry itself"

    before = [list(entry) for entry in thing.carried_by]
    entry = inventory.pair(thing.carried_by, source.id) if source is not None else None
    held_by_source = entry[1] if entry else 0
    needed = thing.size - (sum(slots for _, slots in before) - held_by_source)

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
        return "blocked", "it is not being carried"

    if source is not None and inventory.pair(thing.carried_by, source.id) is None:
        return "blocked", "that pixel is not carrying it"

    if not all_near(actors, [spot(thing), (x, y)]):
        return "approach", "too far from the spot"

    inventory.release(thing, lookup, holder_id=source.id if source is not None else None)

    if not thing.carried_by:
        thing.position = Vec3(x, y, thing.position.z)

    return "done", True