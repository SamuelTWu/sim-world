from ..tile import Tile, State

GLASS = Tile(
    name="glass",
    color=[(190, 225, 235), (180, 218, 230), (200, 232, 240)],
    hardness=0.5,
    collision=1.0,
    state=State.SOLID,
    movement_cost=1.0,
    transparency=0.85,
    passable=False,
    friction=0.5,
    erodibility=0.0,
    footstep_sound="glass",
    tags={"built", "wall", "modern"},
)