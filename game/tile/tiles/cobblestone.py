from ..tile import Tile, State

COBBLESTONE = Tile(
    name="cobblestone",
    color=[(112, 112, 114), (100, 100, 104), (124, 122, 124)],
    hardness=2.5,
    collision=0.0,
    state=State.SOLID,
    movement_cost=0.9,
    friction=0.9,
    erodibility=0.1,
    footstep_sound="stone",
    drops={"cobblestone": 1},
    tags={"built", "floor", "masonry"},
)