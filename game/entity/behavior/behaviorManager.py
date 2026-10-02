import importlib
import inspect
import pkgutil

from . import behaviors
from .behavior import Behavior, BlueprintError
from ..entity import Entity

class BehaviorManager:
    def __init__(self):
        self.behaviors = {}
        self._load()

    def _load(self):
        for module_info in sorted(
            pkgutil.iter_modules(behaviors.__path__),
            key=lambda m: m.name,
        ):
            module = importlib.import_module(
                f"{behaviors.__name__}.{module_info.name}"
            )

            for _, behavior_class in inspect.getmembers(module, inspect.isclass):
                if (
                    behavior_class is Behavior
                    or not issubclass(behavior_class, Behavior)
                    or behavior_class.__module__ != module.__name__
                ):
                    continue

                self.register(behavior_class())

    def register(self, behavior: Behavior):
        if behavior.name in self.behaviors:
            raise ValueError(
                f"Behavior already registered: {behavior.name}"
            )

        self.behaviors[behavior.name] = behavior

    def get(self, name: str) -> Behavior:
        if name not in self.behaviors:
            raise BlueprintError(
                f"Unknown behavior '{name}'; valid: {self.names()}"
            )

        return self.behaviors[name]

    def all(self):
        return self.behaviors.values()

    def names(self):
        return sorted(self.behaviors)

    def by_kind(self, kind: str):
        return [
            behavior
            for behavior in self.behaviors.values()
            if behavior.kind == kind
        ]

    def by_tier(self, tier: int):
        return [
            behavior
            for behavior in self.behaviors.values()
            if behavior.tier == tier
        ]

    def ordered(self, names):
        return sorted(names, key=lambda name: (self.get(name).tier, name))

    def breakdown(self, traits: dict) -> dict[str, float]:
        return {
            name: self.get(name).cost(
                self.get(name).validate(values)
            )
            for name, values in traits.items()
        }

    def cost(self, traits: dict) -> float:
        return sum(self.breakdown(traits).values())

    def validate_blueprint(
        self,
        blueprint: dict,
        unlocked=None,
        capacity: float | None = None,
    ) -> dict:
        normalized = {}

        for name, values in blueprint.get("traits", {}).items():
            behavior = self.get(name)

            if unlocked is not None and name not in unlocked:
                raise BlueprintError(
                    f"Behavior '{name}' has not been unlocked"
                )

            normalized[name] = behavior.validate(values)

        for name in normalized:
            missing = [
                required
                for required in self.behaviors[name].requires
                if required not in normalized
            ]

            if missing:
                raise BlueprintError(
                    f"Behavior '{name}' requires {missing}"
                )

        total = self.cost(normalized)

        if capacity is not None and total > capacity:
            raise BlueprintError(
                f"Blueprint costs {total:.1f} but capacity is {capacity:.1f}"
            )

        result = dict(blueprint)
        result["traits"] = normalized

        return result

    def apply(self, entity: Entity):
        for name in self.ordered(entity.traits):
            behavior = self.get(name)
            entity.traits[name] = behavior.validate(
                entity.traits[name]
            )
            behavior.apply(entity, entity.traits[name])

    def remove_trait(self, entity: Entity, name: str):
        if name in entity.traits:
            self.get(name).remove(entity)
            del entity.traits[name]

    def register_all(self, runner):
        for name in self.ordered(self.behaviors):
            self.behaviors[name].register(runner)

    def to_dict(self) -> dict:
        """Return the serializable behavior definitions.

        Behavior implementations remain Python code. Only their
        data/configuration is exported.
        """
        return {
            "behaviors": {
                name: behavior.to_dict()
                for name, behavior in sorted(self.behaviors.items())
            }
        }