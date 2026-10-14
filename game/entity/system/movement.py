"""Walking toward a point, shared by every task that has to get somewhere (move, attack, pickup).

roam.py has its own copy of this because it was written first; it could use step_toward() too.
"""
import math

from .counters import count
from .simContext import TILE_UNITS

ARRIVED, MOVING, BLOCKED = "arrived", "moving", "blocked"


def clamp_to_world(context, x, y):
    return max(0.0, min(context.world.width * TILE_UNITS - 0.001, x)), max(0.0, min(context.world.height * TILE_UNITS - 0.001, y))


def speed_of(entity):
    """World units per second, or 0 if the pixel has no way of moving."""
    return entity.effective("max_speed") * TILE_UNITS if entity.has_prop("max_speed") else 0.0


def step_toward(entity, context, x, y, delta_time, stop_within=4.0):
    """Move one step toward (x, y). Returns ARRIVED (within stop_within), MOVING, or BLOCKED (cannot move or the way is not walkable)."""
    dx, dy = x - entity.position.x, y - entity.position.y
    distance = math.hypot(dx, dy)

    if distance <= stop_within:
        return ARRIVED

    speed = speed_of(entity)

    if speed <= 0.0:
        return BLOCKED

    travel = min(distance - stop_within * 0.5, speed * delta_time)
    nx, ny = clamp_to_world(context, entity.position.x + dx / distance * travel, entity.position.y + dy / distance * travel)
    tile = context.tile_at(nx, ny)
    count(context, "tile_checks")

    if tile is None or not tile.can_walk_through():
        count(context, "blocked_moves")
        return BLOCKED

    entity.position.x, entity.position.y = nx, ny
    entity.components["heading"] = math.atan2(dy, dx)
    return MOVING