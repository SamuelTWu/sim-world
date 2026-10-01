from ..tile import Tile, State

BRICK = Tile(
    name="brick",
    color=(189, 105, 66),
    hardness=3.0,
    collision=1.0,
    state=State.SOLID,
    movement_cost=1.0,
    passable=False,
    friction=0.9,
    erodibility=0.05,
    footstep_sound="stone",
    drops={"brick": 1},
    tags={"built", "wall", "masonry"},
)