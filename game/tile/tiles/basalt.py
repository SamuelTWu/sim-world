from ..tile import Tile, State

BASALT = Tile(
    name="basalt",
    color=[(58, 60, 66), (50, 52, 58), (68, 70, 76)],
    hardness=4.0,
    collision=1.0,
    state=State.SOLID,
    movement_cost=1.0,
    fertility=0.0,
    passable=False,
    friction=0.9,
    erodibility=0.1,
    footstep_sound="stone",
    drops={"basalt": 1},
    tags={"natural", "mineral", "rock", "volcanic"},
)