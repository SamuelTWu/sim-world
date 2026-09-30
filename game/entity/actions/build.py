import random

from ...tile.tile_types import TILE_TYPES
from ..entity_systems.decisionSystem import Action
from ..entity_systems.considerations import Consideration, quadratic
from ..entity_systems.task import Task, RUNNING, DONE, FAILED

PLACE_TIME = 0.5
MAX_MISTAKES = 3
FAILURE_RATE = 0.5


def build_generator(entity, context):
    blueprint = entity.components.get("blueprint")

    return [Action("build", {"blueprint": blueprint})] if blueprint else []

def construction_need(entity, action, context):
    return context.needs.urgency(entity, "construction")


class BuildTask(Task):
    name = "build"

    def __init__(self, blueprint):
        super().__init__()
        self.blueprint = list(blueprint)
        self.index = 0
        self.mistakes = 0
        self.timer = 0.0

    def step(self, entity, context, delta_time):
        self.timer += delta_time

        if self.timer < PLACE_TIME:
            return RUNNING

        self.timer = 0.0
        x, y, tile_name = self.blueprint[self.index]

        if random.random() < FAILURE_RATE * (1.0 - entity.attributes.get("agility", 0.5)):
            self.mistakes += 1
            context.events.emit("build_failed", entity=entity, x=x, y=y, tile=tile_name)

            if self.mistakes > MAX_MISTAKES:
                entity.components.pop("blueprint", None)
                return FAILED
        else:
            context.world.set_tile(x, y, TILE_TYPES[tile_name])
            context.events.emit("tile_placed", entity=entity, x=x, y=y, tile=tile_name)

        self.index += 1

        if self.index >= len(self.blueprint):
            entity.components.pop("blueprint", None)
            context.needs.satisfy(entity, "construction", 0.5)
            return DONE

        return RUNNING


def register_build(runner):
    runner.register_action_generator(build_generator)
    runner.register_task("build", lambda entity, action, context: BuildTask(action.data["blueprint"]))
    runner.decision_system.register("build", Consideration(construction_need, quadratic, "construction"))