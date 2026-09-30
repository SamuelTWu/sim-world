from dataclasses import dataclass, field
from enum import Enum
import random


class State(Enum):
    SOLID = "solid"
    LIQUID = "liquid"
    GAS = "gas"


@dataclass
class Tile:
    color: tuple[int, int, int] | list[tuple[int, int, int]] | tuple[tuple[int, int, int], tuple[int, int, int]]

    hardness: float = 0.0
    collision: float = 0.0
    state: State = State.SOLID
    movement_cost: float = 1.0
    temperature: float = 20.0
    fertility: float = 0.0
    flammability: float = 0.0
    transparency: float = 0.0
    breakable: bool = True
    passable: bool = True
    is_water: bool = False
    magic: float = 0.0
    name: str = "Unknown"

    friction: float = 1.0
    light_emission: float = 0.0
    damage: float = 0.0
    salinity: float = 0.0
    erodibility: float = 0.5
    moisture: float = 0.0
    buildable: bool = True
    burns_into: str | None = None
    footstep_sound: str = "default"
    drops: dict[str, int] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.color = self.resolve_color()

        self.hardness = max(0.0, self.hardness)
        self.collision = max(0.0, min(1.0, self.collision))
        self.movement_cost = max(0.0, self.movement_cost)
        self.fertility = max(0.0, min(1.0, self.fertility))
        self.flammability = max(0.0, min(1.0, self.flammability))
        self.transparency = max(0.0, min(1.0, self.transparency))
        self.friction = max(0.0, self.friction)
        self.light_emission = max(0.0, min(1.0, self.light_emission))
        self.damage = max(0.0, self.damage)
        self.salinity = max(0.0, min(1.0, self.salinity))
        self.erodibility = max(0.0, min(1.0, self.erodibility))
        self.moisture = max(0.0, min(1.0, self.moisture))

    def resolve_color(self) -> tuple[int, int, int]:
        if self._is_rgb(self.color):
            return self._clamp_color(self.color)

        if isinstance(self.color, list):
            if not self.color:
                raise ValueError(f"Tile '{self.name}' has an empty color list.")

            return self._clamp_color(random.choice(self.color))

        if isinstance(self.color, tuple) and len(self.color) == 2 and all(self._is_rgb(color) for color in self.color):
            minimum, maximum = self.color

            return tuple(
                max(0, min(255, int(random.uniform(minimum[i], maximum[i]))))
                for i in range(3)
            )

        raise ValueError(f"Invalid color definition for tile '{self.name}': {self.color}")

    @staticmethod
    def _is_rgb(value) -> bool:
        return isinstance(value, (tuple, list)) and len(value) == 3 and all(isinstance(channel, (int, float)) for channel in value)

    @staticmethod
    def _clamp_color(color) -> tuple[int, int, int]:
        return tuple(max(0, min(255, int(channel))) for channel in color)

    def is_solid(self) -> bool:
        return self.state == State.SOLID

    def is_liquid(self) -> bool:
        return self.state == State.LIQUID

    def is_gas(self) -> bool:
        return self.state == State.GAS

    def can_walk_through(self) -> bool:
        return self.passable and self.collision < 1.0

    def is_hazardous(self) -> bool:
        return self.damage > 0.0

    def emits_light(self) -> bool:
        return self.light_emission > 0.0

    def is_slippery(self) -> bool:
        return self.friction < 0.5

    def is_flammable(self) -> bool:
        return self.flammability > 0.0

    def is_salty(self) -> bool:
        return self.salinity > 0.5

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags