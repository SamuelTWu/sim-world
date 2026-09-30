from dataclasses import dataclass, field
from typing import Callable

from ..entity import Entity


@dataclass
class AttributeDefinition:
    name: str
    default: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    formula: Callable[[dict[str, float]], float] | None = None


@dataclass
class AttributeSystem:
    definitions: dict[str, AttributeDefinition] = field(default_factory=dict)
    temporary: dict[int, dict[str, float]] = field(default_factory=dict)

    def register(self, definition: AttributeDefinition):
        self.definitions[definition.name] = definition

    def initialize(self, entity: Entity):
        for name, definition in self.definitions.items():
            entity.attributes.setdefault(name, definition.default)
        self.update(entity)

    def set(self, entity: Entity, name: str, value: float):
        entity.attributes[name] = self._clamp(name, value)

    def get(self, entity: Entity, name: str, default: float = 0.0) -> float:
        return entity.attributes.get(name, default)

    def modify(self, entity: Entity, name: str, amount: float):
        self.set(entity, name, self.get(entity, name) + amount)

    def add_temporary(self, entity: Entity, name: str, amount: float):
        self.temporary.setdefault(entity.id, {})[name] = amount
        self.update(entity)

    def remove_temporary(self, entity: Entity, name: str):
        self.temporary.get(entity.id, {}).pop(name, None)
        self.update(entity)

    def update(self, entity: Entity):
        for name, definition in self.definitions.items():
            if definition.formula is not None:
                value = definition.formula(entity.attributes)
                value += self.temporary.get(entity.id, {}).get(name, 0.0)
                entity.attributes[name] = self._clamp(name, value)

    def _clamp(self, name: str, value: float) -> float:
        definition = self.definitions.get(name)

        if definition is None:
            return value

        if definition.minimum is not None:
            value = max(definition.minimum, value)

        if definition.maximum is not None:
            value = min(definition.maximum, value)

        return value
