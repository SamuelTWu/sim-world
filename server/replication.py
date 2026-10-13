"""What the server tells each client about pixels. No networking here, so it can be tested on its own.

Each tick a client is shown the pixels in its visible set (interest.py, `Client.visible`) and is told only what changed:
`enter` (the full state) the first time a pixel is visible, `update` (the id and ONLY the fields that changed) after that,
`leave` when it is no longer visible, or is gone or dead. To stop pixels on the edge of the visible area from flickering
in and out, a pixel enters when it is in the ENTER set (`ids`) but only leaves when it is outside a slightly bigger KEEP
set (`keep`, see interest.visible_ids extra=). The server remembers what it last told each client, in
`known` (id -> the state it sent), so it never repeats itself.
"""
from .protocol import to_wire


def position(entity):
    """The pixel's position as it is sent: whole numbers of 1/POSITION_SCALE world units (protocol.py). A move smaller than that is not sent."""
    return to_wire(entity.position.x), to_wire(entity.position.y)


def entity_state(entity):
    """Everything a client needs to draw a pixel, without its id, already in wire form (x and y are small ints). Add a field here and `enter` / `update` carry it."""
    x, y = position(entity)
    return {"sprite_id": entity.sprite_id, "owner": entity.owner, "name": entity.name, "x": x, "y": y}


def diff(known, ids, lookup, keep=None):
    """Compare what a client knows (`known`: id -> state last sent, changed in place) with the pixels it should see.

    `ids` are the ids that may ENTER, `keep` (a superset of ids; default: same as ids) the ids a client that already has
    a pixel keeps, and `lookup(id)` returns the entity or None. Returns (enter, update, leave): `enter` is a list
    of full states with their "id", `update` a list of {"id", changed fields...}, `leave` a list of ids. Output is ordered by id.
    """
    enter, update, seen = [], [], set()

    keep = ids if keep is None else keep
    stay = {entity_id for entity_id in known if entity_id in keep}

    for entity_id in sorted(set(ids) | stay):
        entity = lookup(entity_id)

        if entity is None or not entity.alive:
            continue

        seen.add(entity_id)
        state = entity_state(entity)
        before = known.get(entity_id)

        if before is None:
            known[entity_id] = state
            enter.append({"id": entity_id, **state})
        elif before != state:
            changed = {key: value for key, value in state.items() if before.get(key) != value}
            known[entity_id] = state
            update.append({"id": entity_id, **changed})

    leave = sorted(entity_id for entity_id in known if entity_id not in seen)

    for entity_id in leave:
        del known[entity_id]

    return enter, update, leave