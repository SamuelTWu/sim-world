from ..tile import Tile, State

WATER = Tile(
    name="water",
    color=(50, 100, 210),
    hardness=0.0,
    collision=0.2,
    state=State.LIQUID,
    movement_cost=3.0,
    transparency=0.3,
    is_water=True,
)