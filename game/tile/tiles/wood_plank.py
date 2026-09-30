from ..tile import Tile, State

WOOD_PLANKS = Tile(
    name="wood_planks",
    color=[(168, 128, 78), (158, 118, 70), (178, 138, 88)],
    hardness=1.5,
    collision=0.0,
    state=State.SOLID,
    movement_cost=0.9,
    flammability=0.8,
    friction=0.9,
    erodibility=0.0,
    burns_into="ash",
    footstep_sound="wood",
    drops={"wood_planks": 1},
    tags={"built", "wood", "floor"},
)