from ..behavior import Behavior, Param
from ...system.decisionSystem import Action
from ...system.movement import ARRIVED, BLOCKED, step_toward
from ...system.task import Task, RUNNING, DONE, FAILED

ARRIVAL = 4.0


class MoveTask(Task):
    """Walk to (x, y). Done when it gets there, failed if the way is blocked or the pixel cannot move at all."""

    name = "move"

    def step(self, entity, context, delta_time):
        result = step_toward(entity, context, self.data["x"], self.data["y"], delta_time, ARRIVAL)

        if result == ARRIVED:
            return DONE

        return FAILED if result == BLOCKED else RUNNING


class Move(Behavior):
    name = "move"
    kind = "action"
    tier = 0
    base_cost = 1.0
    description = "Goes to a given spot. The pixel never picks a spot by itself (that is roam); only orders and other behaviors use it."

    params = {
        "speed": Param(default=1.0, minimum=0.1, maximum=4.0, weight=1.5, description="Tiles per second"),
    }

    def apply(self, entity, values):
        entity.props["max_speed"] = max(entity.props.get("max_speed", 0.0), values["speed"])

    def remove(self, entity):
        entity.props.pop("max_speed", None)

    def register(self, runner):
        self.add_task(runner, "move", lambda entity, action, context: MoveTask(x=float(action.data["x"]), y=float(action.data["y"])))