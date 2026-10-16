import math

from .behavior import Behavior, Param
from ..visibility import can_see
from ..combat.attack_method import ATTACK_METHODS, DEFAULT_METHOD, attack_step, load_attack_methods, resolve
from ..core.counters import count
from ..ai.considerations import Consideration, ramp
from ..ai.decision_system import Action
from ..navigation.movement import ARRIVED, BLOCKED, step_toward
from ..ai.task import Task, RUNNING, DONE, FAILED

load_attack_methods()


class OptionalParam(Param):
    """A number that may be left out (None), meaning "use the attack method's own default"."""

    def validate(self, owner, key, value):
        if value is None:
            return None

        return Param(default=1.0, minimum=self.minimum, maximum=self.maximum).validate(owner, key, value)


def hostile(entity, other):
    """Who a pixel may pick to attack by itself: living pixels of somebody else (neutral pixels count) that its owner can see (not invisible, not spies)."""
    if other is entity or not can_see(entity.owner, other):
        return False

    return entity.owner is None or other.owner != entity.owner


def attack_generator(entity, context):
    """The nearest pixels this one may attack by itself.

    Cheap tests first (README 9.7): a squared-distance test keeps only the pixels within sight, and with a proximity index only the pixels in the
    cells around this one are looked at. Then the pixels in sight are put in order of distance (arithmetic only) and the costly `hostile` / `can_see`
    test runs nearest-first until `candidates` hostile pixels are found, so in a crowd it runs a handful of times instead of once per pixel in sight.
    The answer is the same as testing every pixel and keeping the nearest: the nearest hostile pixels are the same either way (ties by id).
    """
    sight = entity.trait("attack", "sight", 160.0)
    wanted = entity.trait("attack", "candidates", 3)
    x, y = entity.position.x, entity.position.y
    limit = sight * sight * 1.000001  # a hair over, so the exact hypot test below decides the edge
    index = getattr(context, "proximity", None)
    pool = index.near(x, y, sight, context.tick) if index is not None else context.entities.all()
    in_sight = []
    looked = 0

    for other in pool:
        dx, dy = other.position.x - x, other.position.y - y
        looked += 1

        if dx * dx + dy * dy > limit or other is entity:
            continue

        distance = math.hypot(dx, dy)

        if distance <= sight:
            in_sight.append((distance, other.id, other))

    in_sight.sort(key=lambda item: item[:2])  # nearest first, ties by id (the pixels themselves are never compared)
    actions = []
    tested = 0

    for distance, other_id, other in in_sight:
        if len(actions) >= wanted:
            break

        tested += 1

        if hostile(entity, other):
            actions.append(Action("attack", {"target": other_id, "distance": distance}))

    count(context, "attack_scans")
    count(context, "attack_looked", looked)
    count(context, "attack_tested", tested)
    return actions


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