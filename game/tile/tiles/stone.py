from ..tile import Tile

STONE = Tile(
    name="stone",
    color=(100, 100, 105),
    hardness=5.0,
    collision=1.0,
    movement_cost=999.0,
    breakable=True,
    passable=False,
)