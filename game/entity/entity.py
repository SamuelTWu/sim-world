from dataclasses import dataclass, field
from typing import Any

"""putting this here so its not confusing:

Term	What it is	Analogy	Where it lives
Behavior: A capability definition: its parameters, cost, tier, and the code that makes it work    |   A class |   Behavior subclasses in behavior/
Trait: One pixel's copy of an Behavior, with its chosen parameter values  |   An instance |   entity.traits["roam"] = {"speed": 1.5}
Prop: A passive number on a pixel. It does nothing itself, and systems read it    |   A field |   entity.props["flammable"]

tags: labels for targeting ("grass", "enemy"). They have no value, only presence.
inventory: resources the pixel holds, as name to amount.
needs: values that change over time and feed decisions through Need objects.
statuses: temporary effects with a duration.
components: runtime scratch state only (heading, build_index, grudges). Nothing the player edits and nothing saved in a blueprint.
Real fields (health, energy, position, alive): hot values every system reads every frame.
"""

PROP_DEFAULTS = {"max_speed": 0.0, "mass": 1.0, "friction": 1.0, "flammable": 0.0, "edible": 0.0, "smell": 0.0, "conductivity": 0.0, "absorbency": 0.0, "wetness": 0.0, "temperature": 20.0, "reach": 0.0}


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Sprite:
    shape: list | None = None
    image: str | None = None
    character: str | None = None
    color: tuple[int, int, int] = (255, 255, 255)
    size: tuple[int, int] = (16, 16)
    layer: int = 0


@dataclass
class StatusEffect:
    name: str
    duration: float
    strength: float = 1.0
    source: int | None = None
    age: float = 0.0


@dataclass
class Entity:
    id: int
    position: Vec3 = field(default_factory=Vec3)
    sprite: Sprite = field(default_factory=Sprite)
    name: str = "pixel"
    kind: str = "pixel"
    blueprint_name: str | None = None
    owner: int | None = None
    alive: bool = True
    visible: bool = True
    age: float = 0.0
    health: float = 1.0
    max_health: float = 1.0
    energy: float = 1.0
    max_energy: float = 1.0
    home: Vec3 | None = None
    task: Any = None
    task_score: float = 0.0

    traits: dict[str, dict[str, Any]] = field(default_factory=dict)
    props: dict[str, float] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    inventory: dict[str, float] = field(default_factory=dict)
    statuses: list[StatusEffect] = field(default_factory=list)
    needs: dict[str, Any] = field(default_factory=dict)
    components: dict[str, Any] = field(default_factory=dict)

    def prop(self, name: str, default: float | None = None) -> float:
        value = self.props.get(name)

        if value is not None:
            return value

        return PROP_DEFAULTS.get(name, 0.0) if default is None else default

    def has_prop(self, name: str) -> bool:
        return name in self.props

    def has_trait(self, name: str) -> bool:
        return name in self.traits

    def trait(self, name: str, key: str | None = None, default: Any = None) -> Any:
        values = self.traits.get(name)

        if values is None:
            return default

        return values if key is None else values.get(key, default)

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def has_status(self, name: str) -> bool:
        return any(status.name == name for status in self.statuses)

    def carried(self) -> float:
        return sum(self.inventory.values())

    def effective(self, name: str, default: float | None = None) -> float:
        bonus = sum(status.strength for status in self.statuses if status.name == f"{name}_mod") + self.components.get("env_mods", {}).get(name, 0.0)

        return self.prop(name, default) * max(0.0, 1.0 + bonus)

    