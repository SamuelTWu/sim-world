import random
from dataclasses import dataclass
from typing import Any

from .eventBus import EventBus
from .territory import Territory

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

    def __post_init__(self):
        if self.rng is None:
            raise ValueError("SimContext needs the Simulation's seeded rng (rng=...).")

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