from ..tile import Tile, State

IRON_ORE = Tile(
    name="iron_ore", 
    color=[(140, 100, 82), (128, 90, 74), (152, 110, 90)], 
    hardness=4.0, 
    collision=1.0, 
    state=State.SOLID,
    movement_cost=1.0, 
    fertility=0.0, 
    passable=False, 
    friction=0.9, 
    erodibility=0.15, 
    footstep_sound="stone", 
    drops={"iron_ore": 1}, 
    tags={"natural", "mineral", "ore", "resource", "metal"})