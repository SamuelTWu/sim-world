from dataclasses import dataclass, field
from typing import Any
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class MovementProfile:
    max_speed: float = 0.0
    acceleration: float = 0.0
    deceleration: float = 0.0
    jump_impulse: float = 0.0
    air_control: float = 0.0
    gravity: float = 9.81
    traction: float = 1.0
    friction: float = 1.0
    turn_rate: float = 0.0
    reach: float = 0.0
    grab_reach: float = 0.0
    climb_speed: float = 0.0
    can_air_control: bool = False
    can_attach: bool = False
    can_climb: bool = False
    can_swing: bool = False
    anchor: float = 0.0
    charge: float = 0.0


@dataclass
class Physics:
    mass: float = 1.0
    rigid: bool = True
    friction: float = 1.0
    velocity: Vec3 = field(default_factory=Vec3)


@dataclass
class Material:
    flammable: float = 0.0
    edible: float = 0.0
    smell_strength: float = 0.0
    conductivity: float = 0.0
    absorbency: float = 0.0


@dataclass
class State:
    wetness: float = 0.0
    temperature: float = 20.0
    damage: float = 0.0
    burning: bool = False
    held_by: int | None = None


@dataclass
class Blueprint:
    name: str = ""
    data: Any = None
    progress: float = 0.0
    active: bool = True


@dataclass
class ConstructionIntent:
    blueprint: Blueprint | None = None
    motivation: float = 0.0
    priority: float = 0.0


@dataclass
class Sprite:
    shape: list | None = None
    image: str | None = None
    character: str | None = None
    color: tuple[int, int, int] = (255, 255, 255)
    size: tuple[int, int] = (16, 16)
    layer: int = 0


@dataclass
class Entity:
    id: int
    position: tuple[float, float] = (0.0, 0.0)
    sprite: Sprite = field(default_factory=Sprite)
    movement: MovementProfile = field(default_factory=MovementProfile)
    physics: Physics = field(default_factory=Physics)
    material: Material = field(default_factory=Material)
    state: State = field(default_factory=State)
    attributes: dict[str, float] = field(default_factory=dict)
    needs: dict[str, Any] = field(default_factory=dict)
    components: dict[str, Any] = field(default_factory=dict)
    task: Any = None
    task_score: float = 0.0


