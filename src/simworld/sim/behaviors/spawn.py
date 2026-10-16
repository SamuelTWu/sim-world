import math

from .behavior import Behavior, Param
from ..ai.considerations import Consideration
from ..ai.decision_system import Action
from ..core.sim_context import TILE_UNITS
from ..navigation.movement import clamp_to_world
from ..ai.task import Task, RUNNING, DONE, FAILED
from ..core.limits import LimitReached

READY_KEY = "spawn_ready_tick"
PATIENCE = 30.0


def gate_spawnable(ctx, parent, blueprint_id, definition):
    """A blueprint can opt out with "spawnable": false."""
    return None if definition.get("spawnable", True) is not False else "that blueprint cannot be spawned"


# Checks on the blueprint: functions (ctx, parent, blueprint_id, definition) that return a reason to refuse, or None.
# Both the `spawn` command (parent=None, once per command) and the behavior (parent=the pixel) use them.
SPAWN_GATES = [gate_spawnable]


def refusal(ctx, parent, blueprint_id, definition):
    for gate in SPAWN_GATES:
        reason = gate(ctx, parent, blueprint_id, definition)

        if reason:
            return reason

    return None


def pay_spawn_cost(context, parent, definition):
    """Charge the parent for creating a pixel from this definition. Returns False if it cannot afford it.

    The cost itself is still undecided, so spawning is free for now. This is the one place to add it (energy, a need,
    ...). It is never paid from the inventory: spawning creates a NEW pixel, it does not move an existing thing.
    """
    return True


def ready(entity, tick):
    return tick >= entity.components.get(READY_KEY, 0)


def spawn_generator(entity, context):
    blueprint_id = entity.trait("spawn", "blueprint", "")

    if not blueprint_id or not ready(entity, context.tick):
        return []

    definition = context.load_blueprint(blueprint_id)

    if definition is None or refusal(context, entity, blueprint_id, definition):
        return []

    return [Action("spawn", {"blueprint": blueprint_id})]


def reproduction(entity, action, context):
    return context.needs.urgency(entity, "reproduction", 0.0)


class SpawnTask(Task):
    """Create one pixel from a blueprint, at (x, y) or next to the parent. Waits out the parent's cooldown first."""

    name = "spawn"

    def step(self, entity, context, delta_time):
        if not ready(entity, context.tick):
            return FAILED if self.elapsed > PATIENCE else RUNNING

        blueprint_id = self.data["blueprint"]
        definition = context.load_blueprint(blueprint_id)

        if definition is None or refusal(context, entity, blueprint_id, definition) or not pay_spawn_cost(context, entity, definition):
            return FAILED

        if "x" in self.data and "y" in self.data:
            x, y = self.data["x"], self.data["y"]
        else:
            angle = context.rng.uniform(0, math.tau)
            x, y = clamp_to_world(context, entity.position.x + math.cos(angle) * TILE_UNITS, entity.position.y + math.sin(angle) * TILE_UNITS)

        try:
            context.spawn(definition, entity.owner, x, y)
        except LimitReached:
            return FAILED
        entity.components[READY_KEY] = context.tick + int(entity.trait("spawn", "cooldown_ticks", 0))
        return DONE


class Spawn(Behavior):
    name = "spawn"
    kind = "action"
    tier = 1
    base_cost = 3.0
    description = "Creates another pixel (a new one, for a cost; not a move of something that exists). On its own it only does so when it wants to reproduce."

    params = {
        "blueprint": Param(default="", description="What it makes on its own (blank = nothing; orders can name any spawnable blueprint)"),
        "cooldown_ticks": Param(default=200, minimum=0, maximum=100000, description="Ticks between spawns"),
    }

    def register(self, runner):
        self.add_generator(runner, spawn_generator)
        self.add_task(runner, "spawn", lambda entity, action, context: SpawnTask(**action.data))
        self.add_consideration(runner, "spawn", Consideration(reproduction, name="reproduction"))