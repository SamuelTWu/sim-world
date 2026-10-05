import math

from ..behavior import Behavior, Param
from ...system.decisionSystem import Action
from ...system.considerations import Consideration, ramp
from ...system.task import Task, RUNNING, DONE, FAILED
from ...system.simContext import TILE_UNITS

SAMPLE = 8.0
ARRIVAL = 4.0
TIMEOUT = 10.0


def clamp_to_world(context, x, y):
    return max(0.0, min(context.world.width * TILE_UNITS - 0.001, x)), max(0.0, min(context.world.height * TILE_UNITS - 0.001, y))


def path_cost(context, x, y, target_x, target_y):
    target_x, target_y = clamp_to_world(context, target_x, target_y)
    steps = max(1, int(math.hypot(target_x - x, target_y - y) // SAMPLE))
    total = 0.0

    for i in range(1, steps + 1):
        t = i / steps
        tile = context.tile_at(*clamp_to_world(context, x + (target_x - x) * t, y + (target_y - y) * t))

        if tile is None or not tile.can_walk_through():
            return None

        total += max(0.1, tile.movement_cost)

    return total / steps


def roam_generator(entity, context):
    reach = entity.trait("roam", "reach", 160.0)
    actions = []

    for _ in range(entity.trait("roam", "candidates", 6)):
        angle = context.rng.uniform(0, math.tau)
        distance = context.rng.uniform(reach * 0.3, reach)
        x, y = clamp_to_world(context, entity.position.x + math.cos(angle) * distance, entity.position.y + math.sin(angle) * distance)
        actions.append(Action("roam", {"x": x, "y": y, "angle": angle, "cost": path_cost(context, entity.position.x, entity.position.y, x, y)}))

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
    return context.rng.random()


class RoamTask(Task):
    name = "roam"

    def step(self, entity, context, delta_time):
        dx = self.data["x"] - entity.position.x
        dy = self.data["y"] - entity.position.y
        distance = math.hypot(dx, dy)

        if distance <= ARRIVAL:
            context.needs.satisfy(entity, "exploration", 0.05)
            return DONE

        if self.elapsed > TIMEOUT:
            return FAILED

        travel = min(distance, entity.effective("max_speed") * TILE_UNITS * delta_time)
        x, y = clamp_to_world(context, entity.position.x + dx / distance * travel, entity.position.y + dy / distance * travel)
        target = context.tile_at(x, y)

        if target is None or not target.can_walk_through():
            return FAILED

        entity.position.x, entity.position.y = x, y
        entity.components["heading"] = math.atan2(dy, dx)

        return RUNNING


class Roam(Behavior):
    name = "roam"
    kind = "action"
    tier = 0
    base_cost = 1.0
    description = "Wanders to nearby spots, preferring to keep its heading and avoid obstacles."

    params = {
        "speed": Param(default=1.0, minimum=0.1, maximum=4.0, weight=1.5, description="Tiles per second"),
        "reach": Param(default=160.0, minimum=32.0, maximum=640.0, weight=0.01, description="How far each trip can go"),
        "candidates": Param(default=6, minimum=1, maximum=12, weight=0.1, description="How many destinations it considers"),
    }

    def apply(self, entity, values):
        entity.props["max_speed"] = values["speed"]

    def remove(self, entity):
        entity.components.pop("heading", None)

    def register(self, runner):
        self.add_generator(runner, roam_generator)
        self.add_task(runner, "roam", lambda entity, action, context: RoamTask(**action.data))
        self.add_consideration(runner, "roam", Consideration(terrain, name="terrain"))
        self.add_consideration(runner, "roam", Consideration(persistence, ramp(0.3, 1.0), "persistence"))
        self.add_consideration(runner, "roam", Consideration(restlessness, ramp(0.25, 1.0), "restlessness"))
        self.add_consideration(runner, "roam", Consideration(jitter, ramp(0.6, 1.0), "jitter"))