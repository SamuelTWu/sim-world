from ..tile import Tile, State

LAVA = Tile(
name="lava",
color=(230, 70, 20),
hardness=2.0,
collision=1.0,
state=State.LIQUID,
movement_cost=10.0,
temperature=1200.0,
fertility=0.0,
flammability=0.0,
transparency=0.0,
breakable=False,
passable=False,
is_water=False,
)