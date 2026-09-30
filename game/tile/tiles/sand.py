from ..tile import Tile

GRASS = Tile(
    name="sand",
    color=(250, 227, 157),
    hardness=.8,
    collision=0.1,
    movement_cost=3.0,
    fertility=0.3,
)