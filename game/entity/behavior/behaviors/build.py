import random

from ....tile.tile_types import TILE_TYPES
from ..behavior import Behavior, Param
from ...system.decisionSystem import Action
from ...system.considerations import Consideration, quadratic
from ...system.task import Task, RUNNING, DONE, FAILED


def build_generator(entity, context):
    plan = entity.trait("build", "plan")

    return [Action("build", {"plan": plan})] if plan else []

def construction_need(entity, action, context):
    return context.needs.urgency(entity, "construction", 0.5)


class BuildTask(Task):
    name = "build"

    def __init__(self, entity, plan):
        super().__init__()
        self.plan = list(plan)
        self.index = entity.components.get("build_index", 0)
        self.mistakes = 0
        self.timer = 0.0

    def finish(self, entity):
        entity.traits["build"]["plan"] = None
        entity.components.pop("build_index", None)

    def step(self, entity, context, delta_time):
        self.timer += delta_time

        if self.timer < 1.0 / entity.trait("build", "speed", 2.0):
            return RUNNING

        self.timer = 0.0
        x, y, tile_name = self.plan[self.index]
        tile = TILE_TYPES.get(tile_name)
        fail_chance = entity.trait("build", "sloppiness", 0.5) * (1.0 - entity.prop("agility", 0.5))

        if tile is None or random.random() < fail_chance:
            self.mistakes += 1
            context.events.emit("build_failed", entity=entity, x=x, y=y, tile=tile_name)

            if self.mistakes > entity.trait("build", "patience", 3):
                self.finish(entity)
                return FAILED
        else:
            context.world.set_tile(x, y, tile)
            context.events.emit("tile_placed", entity=entity, x=x, y=y, tile=tile_name)

        self.index += 1
        entity.components["build_index"] = self.index

        if self.index >= len(self.plan):
            self.finish(entity)
            context.needs.satisfy(entity, "construction", 0.5)
            return DONE

        return RUNNING

    def cancel(self, entity, context):
        entity.components["build_index"] = self.index


class Build(Behavior):
    name = "build"
    kind = "action"
    tier = 4
    base_cost = 3.0
    description = "Places tiles from a plan, one at a time. It can make mistakes and give up."

    params = {
        "plan": Param(default=None, description="List of [x, y, tile] steps to place"),
        "speed": Param(default=2.0, minimum=0.25, maximum=8.0, weight=0.8, description="Tiles placed per second"),
        "sloppiness": Param(default=0.5, minimum=0.0, maximum=1.0, weight=-2.0, description="Chance of a mistake, before agility"),
        "patience": Param(default=3, minimum=0, maximum=20, weight=0.2, description="Mistakes tolerated before giving up"),
    }

    def remove(self, entity):
        entity.components.pop("build_index", None)

    def register(self, runner):
        self.add_generator(runner, build_generator)
        self.add_task(runner, "build", lambda entity, action, context: BuildTask(entity, action.data["plan"]))
        self.add_consideration(runner, "build", Consideration(construction_need, quadratic, "construction"))