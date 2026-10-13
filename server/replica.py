"""What the client knows about the game, in the form the renderer reads.

Everything here comes from the client's own generated world or from messages the server sent.
Terrain deltas from the server are applied to its world here too (apply_world_delta). The renderer is only ever given a View, never a Simulation. This file imports nothing from game/.
"""
from dataclasses import dataclass, field


@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0


@dataclass
class ReplicatedEntity:
    """A pixel as the client sees it. Phase 7 fills these in from enter / update / leave messages."""

    id: int
    sprite_id: str = "pixel"
    owner: int | None = None
    name: str = ""
    position: Position = field(default_factory=Position)


@dataclass(frozen=True)
class View:
    """A snapshot for one frame: the client's world, its map and feature data, and the entities it knows about."""

    world: object
    maps: object
    features: object
    entities: list
    player_id: int | None = None


class Stats(dict):
    """Counts of what apply_tick_update did, for tests and debugging: entered, updated, left, skipped (malformed entries), unknown (an
    update or leave for a pixel the client does not have, which means it missed an enter: the server does not repeat itself)."""

    def __init__(self):
        super().__init__(entered=0, updated=0, left=0, skipped=0, unknown=0)

    def add(self, other):
        for key, value in other.items():
            self[key] += value


def is_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def apply_tick_update(entities, message):
    """Apply a tick_update to the client's dict of known pixels (id -> ReplicatedEntity), in the order enter, update, leave.

    enter adds a pixel with its full state (or replaces one the client already had), update patches only the fields it carries,
    leave removes. Malformed entries are skipped and never half-applied. Returns a Stats with what happened.
    """
    stats = Stats()

    for state in message.get("enter", ()):
        try:
            entity_id, x, y = state["id"], state["x"], state["y"]
            sprite_id, owner, name = state.get("sprite_id", "pixel"), state.get("owner"), state.get("name") or ""

            if not (is_id(entity_id) and is_number(x) and is_number(y) and isinstance(sprite_id, str) and (owner is None or is_id(owner)) and isinstance(name, str)):
                raise ValueError("bad enter")

            entities[entity_id] = ReplicatedEntity(entity_id, sprite_id, owner, name, Position(float(x), float(y)))
            stats["entered"] += 1
        except (KeyError, TypeError, ValueError, AttributeError):
            stats["skipped"] += 1

    for state in message.get("update", ()):
        try:
            entity = entities.get(state["id"])

            if entity is None:
                stats["unknown"] += 1
                continue

            x, y = state.get("x", entity.position.x), state.get("y", entity.position.y)
            sprite_id, owner, name = state.get("sprite_id", entity.sprite_id), state.get("owner", entity.owner), state.get("name", entity.name)

            if not (is_number(x) and is_number(y) and isinstance(sprite_id, str) and (owner is None or is_id(owner)) and isinstance(name, str)):
                raise ValueError("bad update")

            entity.position, entity.sprite_id, entity.owner, entity.name = Position(float(x), float(y)), sprite_id, owner, name
            stats["updated"] += 1
        except (KeyError, TypeError, ValueError, AttributeError):
            stats["skipped"] += 1

    for entity_id in message.get("leave", ()):
        try:
            if entities.pop(entity_id, None) is None:
                stats["unknown"] += 1
            else:
                stats["left"] += 1
        except TypeError:
            stats["skipped"] += 1

    return stats


def apply_world_delta(world, message, tiles_by_name):
    """Apply a world_delta's [x, y, tile_name] entries on top of the locally generated world, in order.

    `tiles_by_name` maps a tile name to the Tile object. Entries that are malformed, outside the world, or name a
    tile this client does not know are skipped. Returns (changed, skipped): the (x, y) of every tile that really
    changed (for the renderer to redraw), and how many entries were skipped. Applying the same entry twice is harmless.
    """
    changed, skipped = [], 0

    for entry in message.get("tiles", ()):
        try:
            x, y, name = entry
            tile = tiles_by_name.get(name)

            if tile is None or isinstance(x, bool) or isinstance(y, bool) or not world.is_inside(x, y):
                skipped += 1
            elif world.set_tile(x, y, tile):
                changed.append((x, y))
        except (TypeError, ValueError):
            skipped += 1

    return changed, skipped