from dataclasses import dataclass, field
from typing import Any

from ..entity import Entity
from .considerations import Consideration


@dataclass
class Action:
    name: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    action: Action
    score: float


@dataclass
class DecisionSystem:
    considerations: dict[str, list[Consideration]] = field(default_factory=dict)

    def register(self, action_name: str, consideration: Consideration):
        self.considerations.setdefault(action_name, []).append(consideration)

    def evaluate(self, entity: Entity, action: Action, context: Any = None) -> float:
        considerations = self.considerations.get(action.name, [])

        if not considerations:
            return 0.0

        result = 1.0

        for consideration in considerations:
            value = max(0.0, min(1.0, consideration.read(entity, action, context)))
            value = max(0.0, min(1.0, consideration.curve(value)))
            result *= value

            if result <= 0.0:
                return 0.0

        compensation = 1.0 - 1.0 / len(considerations)
        return result + (1.0 - result) * compensation * result

    def evaluate_all(self, entity: Entity, actions: list[Action], context: Any = None) -> list[Decision]:
        return [Decision(action, self.evaluate(entity, action, context)) for action in actions]

    def decide(self, entity: Entity, actions: list[Action], context: Any = None) -> Decision | None:
        best = max(self.evaluate_all(entity, actions, context), key=lambda decision: decision.score, default=None)
        return best if best is not None and best.score > 0.0 else None

    def rank(self, entity: Entity, actions: list[Action], context: Any = None) -> list[Decision]:
        return sorted(self.evaluate_all(entity, actions, context), key=lambda decision: decision.score, reverse=True)
