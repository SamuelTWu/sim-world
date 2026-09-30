from ..tile import Tile, State

ASPHALT = Tile(
    name="asphalt",
    color=[(52, 54, 58), (44, 46, 50), (60, 62, 66)],
    hardness=2.0,
    collision=0.0,
    state=State.SOLID,
    movement_cost=0.8,
    friction=1.0,
    erodibility=0.02,
    footstep_sound="stone",
    drops={"asphalt": 1},
    tags={"built", "floor", "road", "modern"},
)