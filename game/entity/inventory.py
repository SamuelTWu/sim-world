"""Slots: how much an entity can hold, and what everything takes up. All the rules live here.

Every entity has two numbers (set in its blueprint, "slots" and "size"):
    slots   how much it can hold. A pixel might have 5, a transport 4, a rock 0.
    size    how many slots it takes up when something holds it. A pixel is 1, a settlement might be 20.

Two kinds of things take up slots:
    resources   `entity.inventory` maps a resource name to an amount. One slot holds `stack_size(name)` units of a
                resource (1 unless STACK_SIZES says otherwise), so a pixel with 5 slots holds 5 iron.
    cargo       other entities. A held entity takes `size` slots. That is how a transport carries 4 pixels
                (4 slots, size 1 each) and how a settlement is moved: 20 slots, so 4 pixels with 5 free slots each
                carry it together. The load is split across the carriers ("carried_by") and counts as loaded
                only when every slot of its size is covered.

What something holds does not add to its own size: a transport carrying 4 pixels still takes 1 slot when it is
loaded onto a ship.

Held entities stay in the world; this file only keeps the books. Whatever moves things should use `is_loaded` (a big
structure only travels once it is fully loaded) and move held entities with their carriers. Pixels that add or remove
resources should use add_resource / remove_resource instead of changing `inventory` directly, or the slot limit is
not enforced (`overfull` finds entities that got past it).

`cargo` and `carried_by` are lists of [entity id, slots] pairs (plain data, so they save and send as they are).
Functions that need to update the other side of a link take `lookup(id)`, which returns the entity or None.
This file imports nothing from the game.
"""
import math

STACK_SIZES = {}
EPSILON = 1e-6


def stack_size(resource):
    """Units of a resource per slot (default 1). Set STACK_SIZES["grain"] = 10 to fit 10 grain in a slot."""
    return max(1, STACK_SIZES.get(resource, 1))


def whole_slots(resource, amount):
    return math.ceil(amount / stack_size(resource) - EPSILON) if amount > 0 else 0


def resource_slots(entity):
    return sum(whole_slots(name, amount) for name, amount in entity.inventory.items())


def cargo_slots(entity):
    return sum(slots for _, slots in entity.cargo)


def slots_used(entity):
    return resource_slots(entity) + cargo_slots(entity)


def slots_free(entity):
    return max(0, entity.slots - slots_used(entity))


def overfull(entity):
    """True if the entity holds more than its slots (blueprint data or direct writes to `inventory` can do that)."""
    return slots_used(entity) > entity.slots


def holders_needed(item, slots_each):
    """How many carriers it takes to move `item` if each can give `slots_each` slots (a size-20 settlement, 5 each: 4)."""
    return math.ceil(item.size / slots_each) if slots_each > 0 else math.inf


# resources

def add_resource(entity, resource, amount):
    """Put up to `amount` of a resource in the entity. Returns how much fit (possibly 0), never more than the free room."""
    if amount <= 0 or entity.slots <= 0:
        return 0.0

    have = entity.inventory.get(resource, 0.0)
    own = whole_slots(resource, have)
    room = (own + slots_free(entity)) * stack_size(resource) - have
    added = max(0.0, min(amount, room))

    if added > 0:
        entity.inventory[resource] = have + added

    return added


def remove_resource(entity, resource, amount):
    """Take up to `amount` out. Returns how much was taken. A resource that reaches 0 is removed from the inventory."""
    have = entity.inventory.get(resource, 0.0)
    taken = max(0.0, min(amount, have))

    if taken > 0:
        left = have - taken

        if left > EPSILON:
            entity.inventory[resource] = left
        else:
            del entity.inventory[resource]

    return taken


def transfer_resource(source, target, resource, amount):
    """Move up to `amount` from one entity to another, limited by what the source has and the target has room for."""
    moved = add_resource(target, resource, min(amount, source.inventory.get(resource, 0.0)))
    remove_resource(source, resource, moved)
    return moved


# cargo: holding other entities

def pair(pairs, entity_id):
    return next((entry for entry in pairs if entry[0] == entity_id), None)


def set_pair(pairs, entity_id, slots):
    entry = pair(pairs, entity_id)

    if entry is not None:
        entry[1] = slots
    else:
        pairs.append([entity_id, slots])


def drop_pair(pairs, entity_id):
    pairs[:] = [entry for entry in pairs if entry[0] != entity_id]


def carried_slots(item):
    """How many of the item's slots are covered by carriers."""
    return sum(slots for _, slots in item.carried_by)


def is_carried(item):
    return bool(item.carried_by)


def is_loaded(item):
    """True when carriers cover all of the item's size: it can now travel with them."""
    return carried_slots(item) >= item.size


def holds(holder, item_id, lookup):
    """True if `item_id` is in the holder's cargo, directly or inside something it carries."""
    seen, pending = set(), [holder]

    while pending:
        current = pending.pop()

        for entity_id, _ in current.cargo:
            if entity_id == item_id:
                return True

            if entity_id not in seen:
                seen.add(entity_id)
                held = lookup(entity_id)

                if held is not None:
                    pending.append(held)

    return False


def load(item, holders, lookup):
    """Load `item` onto one or more holders, taking the slots it still needs from them in the order given.

    All or nothing: if the holders together do not have enough free slots, nothing changes and this returns False.
    It also refuses when the item is a holder itself, when a holder is dead, appears twice, or is held by the item
    (no loops), and when the item is already fully loaded. Loading more onto a partly loaded item tops it up.
    """
    needed = item.size - carried_slots(item)
    unique = list(dict.fromkeys(id(holder) for holder in holders))

    if needed <= 0 or len(unique) != len(holders) or not holders:
        return False

    if any(holder is item or not holder.alive or holds(item, holder.id, lookup) for holder in holders):
        return False

    plan = []

    for holder in holders:
        give = min(needed, slots_free(holder))

        if give > 0:
            plan.append((holder, give))
            needed -= give

    if needed > 0:
        return False

    for holder, give in plan:
        mine = pair(holder.cargo, item.id)
        set_pair(holder.cargo, item.id, (mine[1] if mine else 0) + give)
        set_pair(item.carried_by, holder.id, (pair(item.carried_by, holder.id) or [0, 0])[1] + give)

    return True


def release(item, lookup, holder_id=None):
    """Take the item off one holder (or all of them). A big item that loses a carrier is no longer loaded."""
    for entity_id, _ in list(item.carried_by):
        if holder_id is not None and entity_id != holder_id:
            continue

        holder = lookup(entity_id)

        if holder is not None:
            drop_pair(holder.cargo, item.id)

        drop_pair(item.carried_by, entity_id)


def drop_all(holder, lookup):
    """Put down everything the holder is holding (for when it dies or is removed). Returns the ids that were released."""
    ids = [entity_id for entity_id, _ in holder.cargo]

    for entity_id in ids:
        item = lookup(entity_id)

        if item is not None:
            release(item, lookup, holder.id)

    holder.cargo.clear()
    return ids


def check(entities, lookup):
    """Problems with the books, as readable strings: over capacity, one-sided links, wrong totals, loops. For tests and audits."""
    problems = []

    for entity in entities:
        if overfull(entity):
            problems.append(f"{entity.id}: holds {slots_used(entity)} slots but has {entity.slots}")

        if carried_slots(entity) > entity.size:
            problems.append(f"{entity.id}: carried by {carried_slots(entity)} slots but its size is {entity.size}")

        for entity_id, slots in entity.cargo:
            held = lookup(entity_id)
            back = pair(held.carried_by, entity.id) if held is not None else None

            if held is None or back is None or back[1] != slots:
                problems.append(f"{entity.id}: cargo {entity_id} is not matched by the other side")

        for entity_id, slots in entity.carried_by:
            holder = lookup(entity_id)
            back = pair(holder.cargo, entity.id) if holder is not None else None

            if holder is None or back is None or back[1] != slots:
                problems.append(f"{entity.id}: carried_by {entity_id} is not matched by the other side")

        if holds(entity, entity.id, lookup):
            problems.append(f"{entity.id}: holds itself")

    return problems