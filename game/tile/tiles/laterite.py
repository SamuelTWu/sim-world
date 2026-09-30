from ..tile import Tile, State

LATERITE = Tile(
    name="laterite",
    color=[(168, 84, 58), (156, 76, 52), (180, 94, 64)],
    hardness=1.0,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.1,
    fertility=0.4,
    friction=0.9,
    erodibility=0.6,
    moisture=0.5,
    footstep_sound="soft",
    drops={"laterite": 1},
    tags={"natural", "soil", "tropical"},
)