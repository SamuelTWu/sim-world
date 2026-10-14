from ..tile import Tile

GRASS = Tile(
    name="grass",
    sprite_id="grass.png",
    color=(80, 170, 70),
    hardness=1.0,
    collision=0.0,
    movement_cost=1.0,
    fertility=0.8,
)