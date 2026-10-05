import math

from ..entity import StatusEffect, Vec3
from ..behavior.behavior import Param, BlueprintError
from .simContext import TILE_UNITS
from .stimulus import Stimulus

POPULATION_CAP = 500
TRIGGERS = {}
EFFECTS = {}
RULE_KEYS = {"on", "when", "do", "with", "if", "chance", "cooldown"}

STATS = {
    "health": lambda e: e.health / max(e.max_health, 1e-9),
    "energy": lambda e: e.energy / max(e.max_energy, 1e-9),
    "age": lambda e: e.age,
    "carried": lambda e: e.carried(),
}

OPS = {"<": lambda a, b: a < b, ">": lambda a, b: a > b}

CONDITION_PARAMS = {
    "stat": Param(default="health", choices=tuple(STATS)),
    "op": Param(default="<", choices=tuple(OPS)),
    "value": Param(default=0.5, minimum=0.0, maximum=1000.0),
}


class Trigger:
    name = ""
    event = ""
    cost = 1.0
    params = {}
    description = ""

    def subject(self, data):
        return data.get("entity")

    def matches(self, runner, entity, args, data, state):
        return {}


class Effect:
    name = ""
    cost = 1.0
    params = {}
    description = ""

    def run(self, runner, entity, args, event):
        pass


def trigger(cls):
    TRIGGERS[cls.name] = cls()
    return cls


def effect(cls):
    EFFECTS[cls.name] = cls()
    return cls


def distance(a, b):
    return math.hypot(a.position.x - b.position.x, a.position.y - b.position.y)


def nearby(runner, entity, radius, tag=""):
    return [other for other in runner.entities() if other is not entity and (not tag or tag in other.tags) and distance(entity, other) <= radius]


def hurt(runner, target, amount, source=None):
    if not target.alive or amount <= 0:
        return

    target.health -= amount
    runner.events.emit("entity_hurt", entity=target, amount=amount, source=source)

    if target.health <= 0:
        runner.entity_manager.kill(target.id)


@trigger
class OnDeath(Trigger):
    name = "death"
    event = "entity_removed"
    description = "When this pixel dies."


@trigger
class OnHurt(Trigger):
    name = "hurt"
    event = "entity_hurt"
    description = "When this pixel takes damage."


@trigger
class OnClick(Trigger):
    name = "click"
    event = "pixel_clicked"
    params = {"button": Param(default=1, minimum=1, maximum=3)}
    description = "When the player clicks this pixel."

    def matches(self, runner, entity, args, data, state):
        return {} if data.get("button", 1) == args["button"] else None


@trigger
class OnSignal(Trigger):
    name = "signal"
    event = "stimulus_triggered"
    params = {"channel": Param(default="alarm")}
    description = "When it hears a signal on a channel."

    def matches(self, runner, entity, args, data, state):
        return {} if data.get("channel") == args["channel"] else None


@trigger
class OnTrespass(Trigger):
    name = "trespass"
    event = "trespass"
    description = "When another pixel builds or gathers in its territory."

    def subject(self, data):
        return data.get("owner")


@trigger
class OnTimer(Trigger):
    name = "timer"
    event = "frame"
    cost = 1.5
    params = {"every": Param(default=5.0, minimum=0.25, maximum=120.0)}
    description = "Every N seconds."

    def subject(self, data):
        return None

    def matches(self, runner, entity, args, data, state):
        state["clock"] = state.get("clock", 0.0) + data["delta_time"]

        if state["clock"] < args["every"]:
            return None

        state["clock"] = 0.0
        return {}


@trigger
class OnContact(Trigger):
    name = "contact"
    event = "frame"
    cost = 2.0
    params = {
        "radius": Param(default=12.0, minimum=4.0, maximum=96.0, weight=0.02),
        "tag": Param(default=""),
        "who": Param(default="any", choices=("any", "other", "same")),
    }
    description = "When another pixel is within a radius."

    def subject(self, data):
        return None

    def allowed(self, entity, other, who):
        return who == "any" or (who == "same") == (other.owner == entity.owner)

    def matches(self, runner, entity, args, data, state):
        state["clock"] = state.get("clock", 0.0) + data["delta_time"]

        if state["clock"] < 0.2:
            return None

        state["clock"] = 0.0
        found = [other for other in nearby(runner, entity, args["radius"], args["tag"]) if self.allowed(entity, other, args["who"])]
        return {"other": min(found, key=lambda other: distance(entity, other))} if found else None


@effect
class Die(Effect):
    name = "die"
    cost = 0.5
    description = "This pixel dies."

    def run(self, runner, entity, args, event):
        runner.entity_manager.kill(entity.id)


@effect
class DamageArea(Effect):
    name = "damage_area"
    cost = 2.0
    params = {
        "radius": Param(default=64.0, minimum=8.0, maximum=256.0, weight=0.02),
        "amount": Param(default=1.0, minimum=0.0, maximum=20.0, weight=0.5),
        "tag": Param(default=""),
        "spare_allies": Param(default=False),
    }
    description = "Damages every pixel within a radius."

    def run(self, runner, entity, args, event):
        for other in nearby(runner, entity, args["radius"], args["tag"]):
            if args["spare_allies"] and other.owner == entity.owner:
                continue
            hurt(runner, other, args["amount"], entity)


@effect
class Spawn(Effect):
    name = "spawn"
    cost = 3.0
    params = {
        "blueprint": Param(default="pixel"),
        "count": Param(default=1, minimum=1, maximum=5, weight=1.0),
        "spread": Param(default=16.0, minimum=0.0, maximum=96.0),
        "energy": Param(default=0.3, minimum=0.0, maximum=1.0, weight=-1.0),
    }
    description = "Creates pixels from a saved blueprint, paid for with energy."

    def run(self, runner, entity, args, event):
        if runner.entity_manager.count() + args["count"] > POPULATION_CAP or entity.energy < args["energy"]:
            return

        entity.energy -= args["energy"]
        blueprint = runner.entity_manager.entity_factory.load_definition(args["blueprint"])
        world = runner.world

        rng = runner.context.rng
        for _ in range(args["count"]):
            child = runner.spawn_blueprint(blueprint, entity.owner)
            angle, radius = rng.uniform(0, math.tau), rng.uniform(0, args["spread"])
            child.position = Vec3(
                max(0.0, min(world.width * TILE_UNITS - 1, entity.position.x + math.cos(angle) * radius)),
                max(0.0, min(world.height * TILE_UNITS - 1, entity.position.y + math.sin(angle) * radius)),
                0.0,
            )


@effect
class EmitStimulus(Effect):
    name = "emit_stimulus"
    cost = 1.5
    params = {
        "channel": Param(default="alarm"),
        "strength": Param(default=1.0, minimum=0.1, maximum=3.0, weight=0.5),
        "radius": Param(default=160.0, minimum=16.0, maximum=640.0, weight=0.005),
        "lifetime": Param(default=3.0, minimum=0.5, maximum=30.0, weight=0.05),
    }
    description = "Sends a signal other pixels can hear."

    def run(self, runner, entity, args, event):
        runner.context.stimuli.emit(Stimulus(entity.position.x, entity.position.y, args["channel"], args["strength"], args["radius"], args["lifetime"], owner=entity.id))


@effect
class SetNeed(Effect):
    name = "set_need"
    cost = 0.5
    params = {"need": Param(default="safety"), "amount": Param(default=0.2, minimum=-1.0, maximum=1.0)}
    description = "Raises a need when positive, satisfies it when negative."

    def run(self, runner, entity, args, event):
        if args["amount"] >= 0:
            runner.need_system.increase(entity, args["need"], args["amount"])
        else:
            runner.need_system.satisfy(entity, args["need"], -args["amount"])


@effect
class ApplyStatus(Effect):
    name = "status"
    cost = 2.0
    params = {
        "name": Param(default="slow"),
        "duration": Param(default=5.0, minimum=0.5, maximum=60.0, weight=0.05),
        "strength": Param(default=0.5, minimum=0.0, maximum=2.0, weight=0.5),
        "radius": Param(default=0.0, minimum=0.0, maximum=192.0, weight=0.02),
    }
    description = "Applies a temporary status to itself, or to everything in a radius."

    def run(self, runner, entity, args, event):
        targets = [entity] if args["radius"] <= 0 else nearby(runner, entity, args["radius"])

        for target in targets:
            target.statuses = [status for status in target.statuses if status.name != args["name"]]
            target.statuses.append(StatusEffect(args["name"], args["duration"], args["strength"], source=entity.id))


@effect
class Anger(Effect):
    name = "anger"
    cost = 1.0
    params = {"severity": Param(default=1.0, minimum=0.1, maximum=3.0)}
    description = "Holds a grudge against whoever caused the event."

    def run(self, runner, entity, args, event):
        offender = event.get("offender") or event.get("source")

        if offender is None or offender is entity:
            return

        amount = args["severity"] * event.get("severity", 1.0)
        runner.need_system.increase(entity, "safety", amount * 0.2)
        grudges = entity.components.setdefault("grudges", {})
        grudges[offender.id] = grudges.get(offender.id, 0.0) + amount


def fill(owner, specs, values):
    values = dict(values or {})
    unknown = set(values) - set(specs)

    if unknown:
        raise BlueprintError(f"{owner} has no parameter(s) {sorted(unknown)}; valid: {sorted(specs)}")

    return {key: spec.validate(owner, key, values[key]) if key in values else spec.default for key, spec in specs.items()}


def validate_rule(rule):
    unknown = set(rule) - RULE_KEYS

    if unknown:
        raise BlueprintError(f"react rule has unknown key(s) {sorted(unknown)}; valid: {sorted(RULE_KEYS)}")

    on, do = rule.get("on"), rule.get("do")

    if on not in TRIGGERS:
        raise BlueprintError(f"react rule has unknown trigger {on!r}; valid: {sorted(TRIGGERS)}")

    if do not in EFFECTS:
        raise BlueprintError(f"react rule has unknown effect {do!r}; valid: {sorted(EFFECTS)}")

    condition = rule.get("if")

    return {
        "on": on,
        "do": do,
        "when": fill(f"react.{on}", TRIGGERS[on].params, rule.get("when")),
        "with": fill(f"react.{do}", EFFECTS[do].params, rule.get("with")),
        "if": fill("react.if", CONDITION_PARAMS, condition) if condition is not None else None,
        "chance": Param(default=1.0, minimum=0.0, maximum=1.0).validate("react", "chance", rule.get("chance", 1.0)),
        "cooldown": Param(default=0.0, minimum=0.0, maximum=300.0).validate("react", "cooldown", rule.get("cooldown", 0.0)),
    }


def validate_rules(rules):
    return [validate_rule(rule) for rule in rules]


def rule_cost(rule):
    t, e = TRIGGERS[rule["on"]], EFFECTS[rule["do"]]
    return t.cost + e.cost + sum(spec.price(rule["when"][key]) for key, spec in t.params.items()) + sum(spec.price(rule["with"][key]) for key, spec in e.params.items())


def dispatch(runner, trigger, data):
    subject = trigger.subject(data)
    pool = [subject] if subject is not None else [entity for entity in runner.entities() if entity.alive]

    for entity in pool:
        react = entity.traits.get("react")
        rules = react.get("rules") if react else None

        if not rules:
            continue

        for index, rule in enumerate(rules):
            if rule["on"] != trigger.name:
                continue

            state = entity.components.setdefault("react_state", {}).setdefault(str(index), {})
            extra = trigger.matches(runner, entity, rule["when"], data, state)

            if extra is None or state.get("ready", 0.0) > entity.age:
                continue

            if rule["chance"] < 1.0 and runner.context.rng.random() > rule["chance"]:
                continue

            condition = rule["if"]

            if condition is not None and not OPS[condition["op"]](STATS[condition["stat"]](entity), condition["value"]):
                continue

            state["ready"] = entity.age + rule["cooldown"]
            EFFECTS[rule["do"]].run(runner, entity, rule["with"], {**data, **extra})


def listener_for(runner, trigger):
    def listener(**data):
        dispatch(runner, trigger, data)

    return listener


def install(runner):
    for trigger in TRIGGERS.values():
        runner.events.on(trigger.event, listener_for(runner, trigger))