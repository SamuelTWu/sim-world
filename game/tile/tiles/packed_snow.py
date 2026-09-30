from ..tile import Tile, State
PACKED_SNOW = Tile(
    name="packed_snow",
    color=[(226, 232, 240), (218, 226, 236), (234, 238, 244)],
    hardness=0.5,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.3,
    temperature=-5.0,
    fertility=0.0,
    friction=0.6,
    erodibility=0.4,
    moisture=0.3,
    footstep_sound="snow",
    drops={"snow": 2},
    tags={"natural", "cold"},
)