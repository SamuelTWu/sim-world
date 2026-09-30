from ..tile import Tile, State

SANDSTONE = Tile(
    name="sandstone",
    color=[(206, 174, 120), (196, 164, 112), (216, 184, 130)],
    hardness=2.0,
    collision=1.0,
    state=State.SOLID,
    movement_cost=1.0,
    fertility=0.0,
    passable=False,
    friction=0.9,
    erodibility=0.45,
    footstep_sound="stone",
    drops={"sandstone": 1},
    tags={"natural", "mineral", "rock"},
)