from dataclasses import dataclass
from typing import Any, Callable

from ..entity import Entity


class BlueprintError(ValueError):
    pass


@dataclass
class Param:
    default: Any = 1.0
    minimum: float | None = None
    maximum: float | None = None
    weight: float = 0.0
    choices: tuple | None = None
    description: str = ""

    def validate(self, owner: str, key: str, value: Any) -> Any:
        label = f"{owner}.{key}"

        if isinstance(self.default, bool):
            if not isinstance(value, bool):
                raise BlueprintError(f"{label} must be true or false, got {value!r}")

            return value

        if self.choices is not None:
            if value not in self.choices:
                raise BlueprintError(f"{label} must be one of {list(self.choices)}, got {value!r}")

            return value

        if isinstance(self.default, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BlueprintError(f"{label} must be a number, got {value!r}")

            if self.minimum is not None and value < self.minimum:
                raise BlueprintError(f"{label} must be at least {self.minimum}, got {value}")

            if self.maximum is not None and value > self.maximum:
                raise BlueprintError(f"{label} must be at most {self.maximum}, got {value}")

            return value

        return value

    def price(self, value: Any) -> float:
        if self.weight == 0.0 or isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0

        return self.weight * max(0.0, value - (self.minimum or 0.0))


class Behavior:
    name = "behavior"
    kind = "action"
    tier = 0
    base_cost = 1.0
    requires: tuple[str, ...] = ()
    params: dict[str, Param] = {}
    description = ""

    def validate(self, values: dict[str, Any] | None) -> dict[str, Any]:
        values = dict(values or {})
        unknown = set(values) - set(self.params)

        if unknown:
            raise BlueprintError(f"{self.name} has no parameter(s) {sorted(unknown)}; valid: {sorted(self.params)}")

        return {key: spec.validate(self.name, key, values[key]) if key in values else spec.default for key, spec in self.params.items()}

    def cost(self, values: dict[str, Any]) -> float:
        return self.base_cost + sum(spec.price(values.get(key, spec.default)) for key, spec in self.params.items())

    def apply(self, entity: Entity, values: dict[str, Any]):
        pass

    def remove(self, entity: Entity):
        pass

    def register(self, runner):
        pass

    def values_for(self, entity: Entity) -> dict[str, Any] | None:
        return entity.traits.get(self.name)

    def gate(self, generator: Callable) -> Callable:
        def gated(entity, context):
            if self.name not in entity.traits:
                return []

            return generator(entity, context)

        return gated

    def add_generator(self, runner, generator: Callable):
        runner.register_action_generator(self.gate(generator))

    def add_task(self, runner, action_name: str, factory: Callable):
        runner.register_task(action_name, factory)

    def add_consideration(self, runner, action_name: str, consideration):
        runner.decision_system.register(action_name, consideration)