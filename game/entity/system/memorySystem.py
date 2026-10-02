from dataclasses import dataclass, field
from typing import Any

from ..entity import Entity

@dataclass
class Memory:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    strength: float = 1.0
    importance: float = 0.0
    age: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data, "strength": self.strength, "importance": self.importance, "age": self.age}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        return cls(type=data["type"], data=dict(data.get("data", {})), strength=float(data.get("strength", 1.0)), importance=float(data.get("importance", 0.0)), age=float(data.get("age", 0.0)))


@dataclass
class MemorySystem:
    memories: dict[int, list[Memory]] = field(default_factory=dict)
    decay_rate: float = 0.001

    def initialize(self, entity: Entity):
        self.memories.setdefault(entity.id, [])

    def remember(self, entity: Entity, memory: Memory):
        self.memories.setdefault(entity.id, []).append(memory)

    def recall(self, entity: Entity, memory_type: str | None = None, limit: int | None = None) -> list[Memory]:
        memories = self.memories.get(entity.id, [])

        if memory_type is not None:
            memories = [memory for memory in memories if memory.type == memory_type]

        memories = sorted(memories, key=lambda memory: memory.strength * (1.0 + memory.importance), reverse=True)

        return memories[:limit] if limit is not None else memories

    def strongest(self, entity: Entity, memory_type: str | None = None) -> Memory | None:
        memories = self.recall(entity, memory_type, 1)

        return memories[0] if memories else None

    def update(self, entity: Entity, delta_time: float):
        memories = self.memories.get(entity.id, [])

        for memory in memories:
            memory.age += delta_time
            memory.strength *= max(0.0, 1.0 - self.decay_rate * delta_time)

        self.memories[entity.id] = [memory for memory in memories if memory.strength > 0.01]

    def forget(self, entity: Entity, memory: Memory):
        if entity.id in self.memories and memory in self.memories[entity.id]:
            self.memories[entity.id].remove(memory)

    def clear(self, entity: Entity):
        self.memories[entity.id] = []

    def to_dict(self) -> dict[str, Any]:
        return {str(entity_id): [memory.to_dict() for memory in memories] for entity_id, memories in self.memories.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any], decay_rate: float = 0.001) -> "MemorySystem":
        memories = {int(entity_id): [Memory.from_dict(memory) for memory in values] for entity_id, values in data.items()}

        return cls(memories=memories, decay_rate=decay_rate)