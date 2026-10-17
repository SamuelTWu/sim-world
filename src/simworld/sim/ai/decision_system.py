from dataclasses import dataclass, field
from typing import Any

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

    def evaluate(self, entity, action: Action, context: Any = None) -> float:
        considerations = self.considerations.get(action.name)

        if not considerations:
            return 0.0

        result = 1.0

        for consideration in considerations:
            value = max(0.0, min(1.0, consideration.read(entity, action, context)))
            result *= max(0.0, min(1.0, consideration.curve(value)))

            if result <= 0.0:
                return 0.0

        compensation = 1.0 - 1.0 / len(considerations)
        return result + (1.0 - result) * compensation * result

    def decide(self, entity, actions: list[Action], context: Any = None) -> Decision | None:
        best, best_score = None, 0.0

        for action in actions:
            score = self.evaluate(entity, action, context)

            if score > best_score:
                best, best_score = action, score

        return Decision(best, best_score) if best is not None else None

    def explain(self, entity, action: Action, context: Any = None) -> list[tuple[str, float, float]]:
        rows = []

        for consideration in self.considerations.get(action.name, ()):
            raw = max(0.0, min(1.0, consideration.read(entity, action, context)))
            rows.append((consideration.name, raw, max(0.0, min(1.0, consideration.curve(raw)))))

        return rows