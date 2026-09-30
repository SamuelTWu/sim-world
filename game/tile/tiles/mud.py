from ..tile import Tile

MUD = Tile(
name="mud",
color=(95, 70, 45),
hardness=0.2,
collision=0.1,
movement_cost=2.0,
temperature=15.0,
fertility=0.7,
flammability=0.0,
transparency=0.0,
breakable=True,
passable=True,
is_water=False,
)