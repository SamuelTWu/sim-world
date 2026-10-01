from ..behavior import Behavior, BlueprintError, Param
from ...system.simContext import TILE_UNITS

RULE_KEYS = {"on", "mod", "amount"}
AMOUNT = Param(default=0.0, minimum=-1.0, maximum=10.0, weight=1.0)


def sample(entity, context):
    keys, tx, ty = context.environment_at(entity.position.x, entity.position.y)
    mods = {}

    for rule in entity.trait("adapt", "rules") or []:
        place = rule["on"]

        if place.startswith("map:"):
            strength = rule["amount"] * context.map_value(place[4:], tx, ty)
        elif place in keys:
            strength = rule["amount"]
        else:
            continue

        mods[rule["mod"]] = mods.get(rule["mod"], 0.0) + strength

    entity.components["env_mods"] = mods


class Adapt(Behavior):
    name = "adapt"
    kind = "body"
    tier = 2
    base_cost = 1.0
    description = "Changes its stats depending on the terrain, biome or map values it stands on."

    params = {
        "slots": Param(default=1, minimum=1, maximum=6, weight=1.0, description="How many environment rules it can hold"),
        "rules": Param(default=None, description="List of {in, mod, amount}. 'in' is a tile name, tag, feature, 'water', or 'map:<name>'"),
    }

    def validate(self, values):
        result = super().validate(values)
        rules = result.get("rules") or []

        if len(rules) > result["slots"]:
            raise BlueprintError(f"adapt has {len(rules)} rules but only {result['slots']} slot(s)")

        checked = []

        for rule in rules:
            unknown = set(rule) - RULE_KEYS

            if unknown or not {"on", "mod"} <= set(rule):
                raise BlueprintError(f"adapt rule needs 'in' and 'mod' (optional 'amount'); got {sorted(rule)}")

            checked.append({"on": rule["on"], "mod": rule["mod"], "amount": AMOUNT.validate("adapt", "amount", rule.get("amount", 0.0))})

        result["rules"] = checked

        return result

    def cost(self, values):
        return super().cost(values) + sum(AMOUNT.price(abs(rule["amount"])) + 0.5 for rule in values.get("rules") or [])

    def remove(self, entity):
        entity.components.pop("env_mods", None)

    def register(self, runner):
        runner.events.on("frame", lambda delta_time, **_: tick(runner, delta_time))


def tick(runner, delta_time):
    for entity in runner.entities():
        if "adapt" not in entity.traits:
            continue

        clock = entity.components.get("env_clock", 0.0) - delta_time

        if clock <= 0.0:
            sample(entity, runner.context)
            clock = 0.25 + (entity.id * 0.013) % 0.1

        entity.components["env_clock"] = clock