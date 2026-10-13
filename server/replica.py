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


def apply_tick_update(entities, message):
    """Apply a tick_update's enter / update / leave to a dict of id -> ReplicatedEntity. Bad entries are skipped."""
    for state in message.get("enter", ()):
        try:
            entities[state["id"]] = ReplicatedEntity(state["id"], state.get("sprite_id", "pixel"), state.get("owner"), state.get("name") or "", Position(float(state["x"]), float(state["y"])))
        except (KeyError, TypeError, ValueError):
            continue

    for state in message.get("update", ()):
        try:
            entity = entities.get(state["id"])

            if entity is None:
                continue

            if "x" in state or "y" in state:
                entity.position = Position(float(state.get("x", entity.position.x)), float(state.get("y", entity.position.y)))

            if "sprite_id" in state:
                entity.sprite_id = state["sprite_id"]

            if "owner" in state:
                entity.owner = state["owner"]

            if "name" in state:
                entity.name = state["name"]
        except (KeyError, TypeError, ValueError):
            continue

    for entity_id in message.get("leave", ()):
        entities.pop(entity_id, None)


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