from ..tile import Tile, State

GOLD_ORE = Tile(
    name="gold_ore", 
    color=[(196, 164, 70), (210, 178, 84), (182, 150, 60)], 
    hardness=5.0, 
    collision=1.0, 
    state=State.SOLID, 
    movement_cost=1.0, 
    fertility=0.0, 
    light_emission=0.05, 
    passable=False, 
    friction=0.9, 
    erodibility=0.1, 
    footstep_sound="stone", 
    drops={"gold_ore": 1}, 
    tags={"natural", "mineral", "ore", "resource", "metal", "precious"})