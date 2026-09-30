from ..tile import Tile, State

CLAY = Tile(
    name="clay",
    color=[(160, 120, 100), (150, 112, 94), (170, 128, 106)],
    hardness=0.6,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.2,
    fertility=0.2,
    friction=0.8,
    erodibility=0.5,
    moisture=0.5,
    footstep_sound="soft",
    drops={"clay": 2},
    tags={"natural", "soil", "resource"},
)