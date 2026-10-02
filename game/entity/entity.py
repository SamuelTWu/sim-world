from dataclasses import dataclass, field
from typing import Any

PROP_DEFAULTS = {
    "max_speed": 0.0,
    "mass": 1.0,
    "friction": 1.0,
    "flammable": 0.0,
    "edible": 0.0,
    "smell": 0.0,
    "conductivity": 0.0,
    "absorbency": 0.0,
    "wetness": 0.0,
    "temperature": 20.0,
    "reach": 0.0,
}


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, data: dict) -> "Vec3":
        return cls(float(data.get("x", 0.0)), float(data.get("y", 0.0)), float(data.get("z", 0.0)))


@dataclass
class StatusEffect:
    name: str
    duration: float
    strength: float = 1.0
    source: int | None = None
    age: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration": self.duration,
            "strength": self.strength,
            "source": self.source,
            "age": self.age,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StatusEffect":
        return cls(
            name=str(data["name"]),
            duration=float(data["duration"]),
            strength=float(data.get("strength", 1.0)),
            source=data.get("source"),
            age=float(data.get("age", 0.0)),
        )


@dataclass
class Entity:
    id: int
    position: Vec3 = field(default_factory=Vec3)
    sprite_id: str = "pixel"
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
    memories: list[Any] = field(default_factory=list)
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "position": self.position.to_dict(),
            "sprite_id": self.sprite_id,
            "name": self.name,
            "kind": self.kind,
            "blueprint_name": self.blueprint_name,
            "owner": self.owner,
            "alive": self.alive,
            "visible": self.visible,
            "age": self.age,
            "health": self.health,
            "max_health": self.max_health,
            "energy": self.energy,
            "max_energy": self.max_energy,
            "home": self.home.to_dict() if self.home is not None else None,
            "task": self.task.to_dict() if self.task is not None else None,
            "task_score": self.task_score,
            "traits": self.traits,
            "props": self.props,
            "tags": sorted(self.tags),
            "inventory": self.inventory,
            "statuses": [status.to_dict() for status in self.statuses],
            "needs": {name: need.to_dict() for name, need in self.needs.items()},
            "memories": [memory.to_dict() for memory in self.memories],
            "components": self.components,
        }

    @classmethod
    def from_dict(cls, data: dict, task_factory=None) -> "Entity":
        from .system.memorySystem import Memory
        from .system.needSystem import Need

        task_data = data.get("task")
        task = task_factory(task_data) if task_data is not None and task_factory is not None else None

        needs = {
            name: Need.from_dict(need_data)
            for name, need_data in data.get("needs", {}).items()
        }

        memories = [
            Memory.from_dict(memory_data)
            for memory_data in data.get("memories", [])
        ]

        return cls(
            id=int(data["id"]),
            position=Vec3.from_dict(data.get("position", {})),
            sprite_id=str(data.get("sprite_id", "pixel")),
            name=str(data.get("name", "pixel")),
            kind=str(data.get("kind", "pixel")),
            blueprint_name=data.get("blueprint_name"),
            owner=data.get("owner"),
            alive=bool(data.get("alive", True)),
            visible=bool(data.get("visible", True)),
            age=float(data.get("age", 0.0)),
            health=float(data.get("health", 1.0)),
            max_health=float(data.get("max_health", 1.0)),
            energy=float(data.get("energy", 1.0)),
            max_energy=float(data.get("max_energy", 1.0)),
            home=Vec3.from_dict(data["home"]) if data.get("home") is not None else None,
            task=task,
            task_score=float(data.get("task_score", 0.0)),
            traits=data.get("traits", {}),
            props=data.get("props", {}),
            tags=set(data.get("tags", [])),
            inventory=data.get("inventory", {}),
            statuses=[StatusEffect.from_dict(status) for status in data.get("statuses", [])],
            needs=needs,
            memories=memories,
            components=data.get("components", {}),
        )
