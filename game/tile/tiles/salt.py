from ..tile import Tile, State

SALT = Tile(
    name="salt",
    color=[(232, 232, 226), (220, 222, 218), (240, 238, 232)],
    hardness=1.0,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.2,
    transparency=0.0,
    fertility=0.0,
    friction=0.7,
    salinity=1.0,
    erodibility=0.6,
    moisture=0.0,
    buildable=True,
    footstep_sound="crunch",
    drops={"salt": 2},
    tags={"natural", "mineral", "salty"},
)