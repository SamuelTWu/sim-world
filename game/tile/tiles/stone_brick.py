from ..tile import Tile, State

STONE_BRICK = Tile(
    name="stone_brick",
    color=(110, 89, 80),
    hardness=3.5,
    collision=1.0,
    state=State.SOLID,
    movement_cost=1.0,
    passable=False,
    friction=0.9,
    erodibility=0.05,
    footstep_sound="stone",
    drops={"stone_brick": 1},
    tags={"built", "wall", "masonry"},
)