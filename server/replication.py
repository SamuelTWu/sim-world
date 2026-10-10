"""What the server tells each client about pixels. No networking here, so it can be tested on its own.

For now a client is only told about the pixels it owns (the ones it placed): `enter` the first time, `update`
when one moves, `leave` when one is gone or dead. Phase 7 replaces the list of ids with "pixels near my pixels"
and adds the visibility rules; the enter / update / leave messages stay the same.
"""
POSITION_DECIMALS = 2


def position(entity):
    return round(entity.position.x, POSITION_DECIMALS), round(entity.position.y, POSITION_DECIMALS)


def entity_state(entity):
    x, y = position(entity)
    return {"id": entity.id, "sprite_id": entity.sprite_id, "owner": entity.owner, "name": entity.name, "x": x, "y": y}


def diff(known, ids, lookup):
    """Compare what a client knows (`known`: id -> (x, y), changed in place) with the pixels it should see.

    `ids` are the ids to show, and `lookup(id)` returns the entity or None. Returns (enter, update, leave).
    """
    enter, update, seen = [], [], set()

    for entity_id in ids:
        entity = lookup(entity_id)

        if entity is None or not entity.alive:
            continue

        seen.add(entity_id)
        point = position(entity)

        if entity_id not in known:
            known[entity_id] = point
            enter.append(entity_state(entity))
        elif known[entity_id] != point:
            known[entity_id] = point
            update.append({"id": entity_id, "x": point[0], "y": point[1]})

    leave = [entity_id for entity_id in known if entity_id not in seen]

    for entity_id in leave:
        del known[entity_id]

    return enter, update, leave