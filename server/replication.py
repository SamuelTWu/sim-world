"""What the server tells each client about pixels. No networking here, so it can be tested on its own.

Each tick a client is shown the pixels in its visible set (interest.py, `Client.visible`) and is told only what changed:
`enter` (the full state) the first time a pixel is visible, `update` (the id and ONLY the fields that changed) after that,
`leave` when it is no longer visible, or is gone or dead. The server remembers what it last told each client, in
`known` (id -> the state it sent), so it never repeats itself.
"""
POSITION_DECIMALS = 2


def position(entity):
    return round(entity.position.x, POSITION_DECIMALS), round(entity.position.y, POSITION_DECIMALS)


def entity_state(entity):
    """Everything a client needs to draw a pixel, without its id. Add a field here and `enter` / `update` carry it."""
    x, y = position(entity)
    return {"sprite_id": entity.sprite_id, "owner": entity.owner, "name": entity.name, "x": x, "y": y}


def diff(known, ids, lookup):
    """Compare what a client knows (`known`: id -> state last sent, changed in place) with the pixels it should see.

    `ids` are the ids to show, and `lookup(id)` returns the entity or None. Returns (enter, update, leave): `enter` is a list
    of full states with their "id", `update` a list of {"id", changed fields...}, `leave` a list of ids. Output is ordered by id.
    """
    enter, update, seen = [], [], set()

    for entity_id in sorted(ids):
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