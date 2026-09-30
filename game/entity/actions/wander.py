import math
import random

from ..entity_systems.decisionSystem import Action
from ..entity_systems.considerations import Consideration, ramp
from ..entity_systems.task import Task, RUNNING, DONE, FAILED
from ..entity_systems.simContext import TILE_UNITS

CANDIDATES = 6
MIN_RANGE = 48.0
MAX_RANGE = 160.0
SAMPLE = 8.0
ARRIVAL = 4.0
TIMEOUT = 10.0


def path_cost(context, x, y, target_x, target_y):
    max_x = context.world.width * TILE_UNITS - 0.001
    max_y = context.world.height * TILE_UNITS - 0.001
    target_x = max(0.0, min(max_x, target_x))
    target_y = max(0.0, min(max_y, target_y))
    steps = max(1, int(math.hypot(target_x - x, target_y - y) // SAMPLE))
    total = 0.0

    for i in range(1, steps + 1):
        t = i / steps
        sample_x = max(0.0, min(max_x, x + (target_x - x) * t))
        sample_y = max(0.0, min(max_y, y + (target_y - y) * t))
        tile = context.tile_at(sample_x, sample_y)

        if tile is None or not tile.can_walk_through():
            return None

        total += max(0.1, tile.movement_cost)

    return total / steps


def wander_generator(entity, context):
    actions = []
    max_x = context.world.width * TILE_UNITS - 0.001
    max_y = context.world.height * TILE_UNITS - 0.001

    for _ in range(CANDIDATES):
        angle = random.uniform(0, math.tau)
        distance = random.uniform(MIN_RANGE, MAX_RANGE)
        x = max(0.0, min(max_x, entity.position.x + math.cos(angle) * distance))
        y = max(0.0, min(max_y, entity.position.y + math.sin(angle) * distance))
        actions.append(Action("wander", {"x": x, "y": y, "angle": angle, "cost": path_cost(context, entity.position.x, entity.position.y, x, y)}))

    return actions


def terrain(entity, action, context):
    cost = action.data["cost"]
    return 0.0 if cost is None else min(1.0, 1.0 / cost)


def persistence(entity, action, context):
    heading = entity.components.get("heading")
    return 1.0 if heading is None else (1.0 + math.cos(action.data["angle"] - heading)) / 2.0


def restlessness(entity, action, context):
    return context.needs.urgency(entity, "exploration", 0.5)


def jitter(entity, action, context):
    return random.random()


CONSIDERATIONS = [
    Consideration(terrain, name="terrain"),
    Consideration(persistence, ramp(0.3, 1.0), "persistence"),
    Consideration(restlessness, ramp(0.25, 1.0), "restlessness"),
    Consideration(jitter, ramp(0.6, 1.0), "jitter"),
]


class WanderTask(Task):
    name = "wander"

    def step(self, entity, context, delta_time):
        dx = self.data["x"] - entity.position.x
        dy = self.data["y"] - entity.position.y
        distance = math.hypot(dx, dy)

        if distance <= ARRIVAL:
            context.needs.satisfy(entity, "exploration", 0.05)
            return DONE

        if self.elapsed > TIMEOUT:
            return FAILED

        here = context.tile_at(entity.position.x, entity.position.y)
        cost = max(0.1, here.movement_cost) if here else 1.0
        travel = min(distance, entity.movement.max_speed * TILE_UNITS * delta_time / cost)
        max_x = context.world.width * TILE_UNITS - 0.001
        max_y = context.world.height * TILE_UNITS - 0.001
        x = max(0.0, min(max_x, entity.position.x + dx / distance * travel))
        y = max(0.0, min(max_y, entity.position.y + dy / distance * travel))
        target = context.tile_at(x, y)

        if target is None or not target.can_walk_through():
            return FAILED

        entity.position.x, entity.position.y = x, y
        entity.components["heading"] = math.atan2(dy, dx)

        return RUNNING


def register_wander(runner):
    runner.register_action_generator(wander_generator)
    runner.register_task("wander", lambda entity, action, context: WanderTask(**action.data))

    for consideration in CONSIDERATIONS:
        runner.decision_system.register("wander", consideration)
