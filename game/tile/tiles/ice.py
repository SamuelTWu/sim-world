from ..tile import Tile, State

ICE = Tile(
    name="ice",
    color=[(170, 210, 240), (160, 200, 235), (182, 220, 246)],
    hardness=1.5,
    collision=0.0,
    state=State.SOLID,
    movement_cost=1.0,
    temperature=-10.0,
    transparency=0.4,
    fertility=0.0,
    friction=0.05,
    erodibility=0.3,
    footstep_sound="ice",
    drops={"ice": 1},
    tags={"natural", "cold"},
)