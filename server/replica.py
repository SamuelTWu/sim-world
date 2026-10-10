"""What the client knows about the game, in the form the renderer reads.

Everything here comes from the client's own generated world or from messages the server sent.
The renderer is only ever given a View, never a Simulation. This file imports nothing from game/.
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
            entities[state["id"]] = ReplicatedEntity(state["id"], state.get("sprite_id", "pixel"), state.get("owner"), Position(float(state["x"]), float(state["y"])))
        except (KeyError, TypeError, ValueError):
            continue

    for state in message.get("update", ()):
        try:
            entity = entities.get(state["id"])

            if entity is not None:
                entity.position = Position(float(state["x"]), float(state["y"]))
        except (KeyError, TypeError, ValueError):
            continue

    for entity_id in message.get("leave", ()):
        entities.pop(entity_id, None)