import random
from dataclasses import dataclass
from typing import Any

from .event_bus import EventBus
from ..territory.territory import Territory

TILE_UNITS = 32


@dataclass
class SimContext:
    world: Any
    entities: Any
    needs: Any
    events: EventBus
    territory: Territory
    stimuli: Any = None
    maps: Any = None
    rng: random.Random | None = None
    tick: int = 0
    spawn: Any = None
    transient_events: Any = None  # TransientEventLog (transientEvents.py): things that are seen but are not pixels
    activity: Any = None  # Activity (activity.py): which pixels get the expensive systems every tick (9.2)
    counters: Any = None  # Counters (counters.py): how much work was done, for the server's log (9.1)
    proximity: Any = None  # ProximityIndex (proximity.py): who is near a point without looking at every pixel (9.7)
    limits: Any = None

    def __post_init__(self):
        if self.rng is None:
            raise ValueError("SimContext needs the Simulation's seeded rng (rng=...).")

    def get_entity(self, entity_id):
        """The entity with this id (it may be dead and waiting to be removed: check .alive), or None."""
        return self.entities.get(entity_id)

    def load_blueprint(self, blueprint_id):
        """A blueprint's definition dict, or None if there is no such blueprint."""
        try:
            return self.entities.entity_factory.load_definition(blueprint_id)
        except (OSError, ValueError):
            return None

    def tile_coords(self, x, y):
        return int(x // TILE_UNITS), int(y // TILE_UNITS)

    def tile_at(self, x, y):
        return self.world.get_tile(int(x // TILE_UNITS), int(y // TILE_UNITS))

    def environment_at(self, x, y):
        tx, ty = int(x // TILE_UNITS), int(y // TILE_UNITS)
        tile = self.world.get_tile(tx, ty)

        if tile is None:
            return set(), tx, ty

        keys = {tile.name, *tile.tags}

        if tile.is_water:
            keys.add("water")

        feature = self.world.feature_grid[ty][tx] if getattr(self.world, "feature_grid", None) else None

        if feature:
            keys.add(feature)

        return keys, tx, ty

    def map_value(self, name, tx, ty):
        return self.maps.get(name).get(tx, ty) if self.maps is not None else 0.0