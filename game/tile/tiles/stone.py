from ..tile import Tile

STONE = Tile(
    name="stone",
    color=(100, 100, 105),
    hardness=5.0,
    collision=0.9,
    movement_cost=1.0,
    breakable=True,
    passable=True,
)