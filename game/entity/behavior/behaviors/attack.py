import math

from ..behavior import Behavior, Param
from ....command.attack_method import ATTACK_METHODS, DEFAULT_METHOD, attack_step, load_attack_methods, resolve
from ...system.considerations import Consideration, ramp
from ...system.decisionSystem import Action
from ...system.movement import ARRIVED, BLOCKED, step_toward
from ...system.task import Task, RUNNING, DONE, FAILED

load_attack_methods()


class OptionalParam(Param):
    """A number that may be left out (None), meaning "use the attack method's own default"."""

    def validate(self, owner, key, value):
        if value is None:
            return None

        return Param(default=1.0, minimum=self.minimum, maximum=self.maximum).validate(owner, key, value)


def hostile(entity, other):
    """Who a pixel may pick to attack by itself: living, visible pixels of somebody else (neutral pixels count)."""
    if other is entity or not other.alive or not other.visible:
        return False

    return entity.owner is None or other.owner != entity.owner


def attack_generator(entity, context):
    sight = entity.trait("attack", "sight", 160.0)
    found = []

    for other in context.entities.all():
        if hostile(entity, other):
            distance = math.hypot(other.position.x - entity.position.x, other.position.y - entity.position.y)

            if distance <= sight:
                found.append((distance, other.id))

    found.sort()
    return [Action("attack", {"target": target, "distance": distance}) for distance, target in found[: entity.trait("attack", "candidates", 3)]]


def proximity(entity, action, context):
    return 1.0 - action.data["distance"] / max(1.0, entity.trait("attack", "sight", 160.0))


def aggression(entity, action, context):
    return context.needs.urgency(entity, "aggression", 0.0)


class AttackTask(Task):
    """Chase and attack one pixel until it is gone. Done when the target is dead or gone, failed if it cannot get closer."""

    name = "attack"

    def step(self, entity, context, delta_time):
        target = context.get_entity(self.data["target"])
        result = attack_step(context, entity, target)

        if result == "gone":
            return DONE if target is None or not target.alive else FAILED

        if result != "approach":
            return RUNNING

        method, params = resolve(entity)
        stop = max(1.0, method.reach(context, entity, params) * 0.8)
        moved = step_toward(entity, context, target.position.x, target.position.y, delta_time, stop)

        return FAILED if moved == BLOCKED else RUNNING


class Attack(Behavior):
    name = "attack"
    kind = "action"
    tier = 1
    base_cost = 2.0
    description = "Attacks another pixel in its own way (collision unless the method says otherwise). On its own it only picks targets when it is aggressive."

    params = {
        "method": Param(default=DEFAULT_METHOD, choices=tuple(sorted(ATTACK_METHODS)), description="How it attacks (see command/attack_methods)"),
        "damage": OptionalParam(default=None, minimum=0.0, maximum=100.0, weight=0.5, description="Health taken per hit (blank = the method's default)"),
        "reach": OptionalParam(default=None, minimum=1.0, maximum=640.0, weight=0.01, description="How close it must be (blank = the method's default)"),
        "cooldown_ticks": OptionalParam(default=None, minimum=0, maximum=1000, description="Ticks between hits (blank = the method's default)"),
        "sight": Param(default=160.0, minimum=16.0, maximum=640.0, weight=0.01, description="How far it looks for targets on its own"),
        "candidates": Param(default=3, minimum=1, maximum=8, weight=0.1, description="How many targets it considers on its own"),
    }

    def register(self, runner):
        self.add_generator(runner, attack_generator)
        self.add_task(runner, "attack", lambda entity, action, context: AttackTask(target=int(action.data["target"])))
        self.add_consideration(runner, "attack", Consideration(proximity, ramp(0.2, 1.0), "proximity"))
        self.add_consideration(runner, "attack", Consideration(aggression, name="aggression"))