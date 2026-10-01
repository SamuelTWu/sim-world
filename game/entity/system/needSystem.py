from dataclasses import dataclass
from typing import Callable

from ..entity import Entity


@dataclass
class Need:
    name: str
    value: float = 0.0
    rate: float = 0.0
    urgency: Callable[[float], float] | None = None
    minimum: float = 0.0
    maximum: float = 1.0

    def update(self, delta_time: float):
        self.value = max(self.minimum, min(self.maximum, self.value + self.rate * delta_time))

    def get_urgency(self) -> float:
        return self.urgency(self.value) if self.urgency else self.value


class NeedSystem:

    def add(self, entity: Entity, need: Need):
        entity.needs[need.name] = need

    def remove(self, entity: Entity, name: str):
        entity.needs.pop(name, None)

    def get(self, entity: Entity, name: str) -> Need | None:
        return entity.needs.get(name)

    def value(self, entity: Entity, name: str, default: float = 0.0) -> float:
        need = self.get(entity, name)
        return need.value if need else default

    def urgency(self, entity: Entity, name: str, default: float = 0.0) -> float:
        need = self.get(entity, name)
        return need.get_urgency() if need else default

    def satisfy(self, entity: Entity, name: str, amount: float):
        need = self.get(entity, name)
        if need:
            need.value = max(need.minimum, need.value - amount)

    def increase(self, entity: Entity, name: str, amount: float):
        need = self.get(entity, name)
        if need:
            need.value = min(need.maximum, need.value + amount)

    def update(self, entity: Entity, delta_time: float):
        for need in entity.needs.values():
            need.update(delta_time)

    def most_urgent(self, entity: Entity) -> Need | None:
        return max(entity.needs.values(), key=lambda need: need.get_urgency(), default=None)
