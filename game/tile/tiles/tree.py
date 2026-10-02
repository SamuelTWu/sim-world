from ..tile import Tile

GRASS = Tile(
    name="tree",
    color=(18, 74, 2),
    hardness=1.0,
    collision=0.9,
    movement_cost=0.9,
    fertility=0.6,
    passable=True,
)