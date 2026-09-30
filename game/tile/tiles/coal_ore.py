from ..tile import Tile, State

COAL_ORE = Tile(
    name="coal_ore", 
    color=[(48, 48, 52), (38, 38, 42), (58, 56, 60)], 
    hardness=3.0, collision=1.0, state=State.SOLID, 
    movement_cost=1.0, 
    fertility=0.0, 
    flammability=0.1, 
    passable=False, 
    friction=0.9, 
    erodibility=0.2, 
    footstep_sound="stone", 
    drops={"coal": 2}, 
    tags={"natural", "mineral", "ore", "resource", "fuel"}
)
