from ..tile import Tile, State

CONCRETE = Tile(
    name="concrete",
    color=[(150, 150, 152), (142, 142, 146), (158, 158, 160)],
    hardness=4.5,
    collision=1.0,
    state=State.SOLID,
    movement_cost=1.0,
    passable=False,
    friction=0.9,
    erodibility=0.02,
    footstep_sound="stone",
    drops={"concrete": 1},
    tags={"built", "wall", "modern"},
)