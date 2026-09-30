from ..tile import Tile, State

DIRT = Tile(
    name="dirt",
    color=[(118, 86, 58), (108, 78, 52), (128, 94, 64)],
    hardness=0.3,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.0,
    fertility=0.5,
    friction=1.0,
    erodibility=0.7,
    moisture=0.2,
    footstep_sound="soft",
    drops={"dirt": 1},
    tags={"natural", "soil"},
)