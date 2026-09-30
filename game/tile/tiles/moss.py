from ..tile import Tile, State

MOSS = Tile(
    name="moss",
    color=[(74, 112, 58), (62, 98, 48), (86, 124, 66)],
    hardness=0.2,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.1,
    transparency=0.0,
    fertility=0.7,
    flammability=0.3,
    friction=0.9,
    erodibility=0.5,
    moisture=0.6,
    buildable=True,
    burns_into="ash",
    footstep_sound="soft",
    drops={"moss": 1},
    tags={"natural", "plant", "damp"},
)