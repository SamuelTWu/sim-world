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

    def tile_coords(self, x, y):
        return int(x // TILE_UNITS), int(y // TILE_UNITS)

    def tile_at(self, x, y):
        return self.world.get_tile(int(x // TILE_UNITS), int(y // TILE_UNITS))