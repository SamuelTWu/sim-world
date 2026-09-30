from ..tile import Tile, State

PERMAFROST = Tile(
    name="permafrost",
    color=[(96, 92, 90), (86, 84, 84), (106, 100, 96)],
    hardness=2.0,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.1,
    temperature=-8.0,
    fertility=0.05,
    friction=0.8,
    erodibility=0.2,
    moisture=0.3,
    footstep_sound="gravel",
    drops={"frozen_soil": 1},
    tags={"natural", "cold", "soil"},
)