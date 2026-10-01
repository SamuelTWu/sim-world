from ..behavior import Behavior, BlueprintError, Param
from ...system.rules import validate_rule, rule_cost, install


class React(Behavior):
    name = "react"
    kind = "reaction"
    tier = 3
    base_cost = 1.0
    description = "Holds when/do rules: when something happens, do something."

    params = {
        "slots": Param(default=1, minimum=1, maximum=6, weight=1.0, description="How many rules it can hold"),
        "rules": Param(default=None, description="List of {on, when, do, with, if, chance, cooldown} rules"),
    }

    def validate(self, values):
        result = super().validate(values)
        rules = result.get("rules") or []

        if len(rules) > result["slots"]:
            raise BlueprintError(f"react has {len(rules)} rules but only {result['slots']} slot(s)")

        result["rules"] = [validate_rule(rule) for rule in rules]

        return result

    def cost(self, values):
        return super().cost(values) + sum(rule_cost(rule) for rule in values.get("rules") or [])

    def remove(self, entity):
        entity.components.pop("react_state", None)

    def register(self, runner):
        install(runner)