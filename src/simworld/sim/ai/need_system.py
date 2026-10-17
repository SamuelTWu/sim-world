from dataclasses import dataclass, field
from typing import Any

from .considerations import curve_from

DEFAULT_NEEDS = {}


@dataclass(slots=True)
class Need:
    name: str
    value: float = 0.0
    rate: float = 0.0
    minimum: float = 0.0
    maximum: float = 1.0
    curve: str = "linear"
    curve_args: dict = field(default_factory=dict)
    shaped: Any = field(default=None, init=False, repr=False, compare=False)

    def update(self, delta_time: float):
        self.value = max(self.minimum, min(self.maximum, self.value + self.rate * delta_time))

    def get_urgency(self) -> float:
        span = self.maximum - self.minimum
        fraction = max(0.0, min(1.0, (self.value - self.minimum) / span)) if span > 0 else 0.0

        if self.curve == "linear":
            return fraction

        if self.shaped is None:
            self.shaped = curve_from(self.curve, self.curve_args)

        return max(0.0, min(1.0, self.shaped(fraction)))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "rate": self.rate, "minimum": self.minimum, "maximum": self.maximum, "curve": self.curve, "curve_args": dict(self.curve_args)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Need":
        curve, curve_args = str(data.get("curve", "linear")), dict(data.get("curve_args", {}))
        curve_from(curve, curve_args)
        return cls(name=data["name"], value=float(data.get("value", 0.0)), rate=float(data.get("rate", 0.0)), minimum=float(data.get("minimum", 0.0)), maximum=float(data.get("maximum", 1.0)), curve=curve, curve_args=curve_args)


class NeedSystem:
    def initialize(self, entity):
        for name, spec in DEFAULT_NEEDS.items():
            if name not in entity.needs:
                entity.needs[name] = Need.from_dict({**spec, "name": name})

    def get(self, entity, name: str) -> Need | None:
        return entity.needs.get(name)

    def urgency(self, entity, name: str, default: float = 0.0) -> float:
        need = entity.needs.get(name)
        return need.get_urgency() if need else default

    def satisfy(self, entity, name: str, amount: float):
        need = entity.needs.get(name)

        if need:
            need.value = max(need.minimum, need.value - amount)

    def increase(self, entity, name: str, amount: float):
        need = entity.needs.get(name)

        if need:
            need.value = min(need.maximum, need.value + amount)

    def update(self, entity, delta_time: float):
        for need in entity.needs.values():
            need.update(delta_time)