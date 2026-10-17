import math
from dataclasses import dataclass, field
from typing import Any

MAX_PER_ENTITY = 64
FORGET_BELOW = 0.01


@dataclass
class Memory:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    strength: float = 1.0
    importance: float = 0.0
    age: float = 0.0
    key: str | None = None

    def weight(self) -> float:
        return self.strength * (1.0 + self.importance)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data, "strength": self.strength, "importance": self.importance, "age": self.age, "key": self.key}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        return cls(type=data["type"], data=dict(data.get("data", {})), strength=float(data.get("strength", 1.0)), importance=float(data.get("importance", 0.0)), age=float(data.get("age", 0.0)), key=data.get("key"))


@dataclass
class MemorySystem:
    memories: dict[int, list[Memory]] = field(default_factory=dict)
    decay_rate: float = 0.001

    def remember(self, entity, memory: Memory) -> Memory:
        known = self.memories.setdefault(entity.id, [])

        if memory.key is not None:
            for old in known:
                if old.type == memory.type and old.key == memory.key:
                    old.data, old.strength, old.age = memory.data, max(old.strength, memory.strength), 0.0
                    old.importance = max(old.importance, memory.importance)
                    return old

        known.append(memory)

        if len(known) > MAX_PER_ENTITY:
            known.remove(min(known, key=lambda item: (item.weight(), -item.age)))

        return memory

    def recall(self, entity, memory_type: str | None = None, limit: int | None = None) -> list[Memory]:
        known = self.memories.get(entity.id, ())
        found = [memory for memory in known if memory_type is None or memory.type == memory_type]
        found.sort(key=Memory.weight, reverse=True)
        return found[:limit] if limit is not None else found

    def nearest(self, entity, memory_type: str, x: float, y: float, kind: str | None = None) -> Memory | None:
        best, best_distance = None, math.inf

        for memory in self.memories.get(entity.id, ()):
            data = memory.data

            if memory.type != memory_type or "x" not in data or "y" not in data or (kind is not None and data.get("kind") != kind):
                continue

            distance = (data["x"] - x) ** 2 + (data["y"] - y) ** 2

            if distance < best_distance:
                best, best_distance = memory, distance

        return best

    def update(self, entity, delta_time: float):
        known = self.memories.get(entity.id)

        if not known:
            return

        factor, faded = math.exp(-self.decay_rate * delta_time), False

        for memory in known:
            memory.age += delta_time
            memory.strength *= factor
            faded = faded or memory.strength < FORGET_BELOW

        if faded:
            self.memories[entity.id] = [memory for memory in known if memory.strength >= FORGET_BELOW]

    def remove(self, entity):
        self.memories.pop(entity.id, None)

    def to_dict(self) -> dict[str, Any]:
        return {str(entity_id): [memory.to_dict() for memory in known] for entity_id, known in self.memories.items() if known}

    @classmethod
    def from_dict(cls, data: dict[str, Any], decay_rate: float = 0.001) -> "MemorySystem":
        return cls(memories={int(entity_id): [Memory.from_dict(item) for item in values] for entity_id, values in data.items()}, decay_rate=decay_rate)