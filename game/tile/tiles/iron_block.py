from ..tile import Tile, State

IRON_BLOCK = Tile(
    name="iron_block",
    color=[(196, 198, 204), (184, 188, 196), (206, 208, 214)],
    hardness=7.0,
    collision=1.0,
    state=State.SOLID,
    movement_cost=1.0,
    passable=False,
    friction=0.6,
    erodibility=0.0,
    footstep_sound="metal",
    drops={"iron_ingot": 4},
    tags={"built", "wall", "metal"},
)