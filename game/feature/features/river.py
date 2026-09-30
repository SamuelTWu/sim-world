from ..feature import Feature
from .desert import DesertFeature

class RiverFeature(Feature):
    name = "river"
    priority = 1
    blend_width = 0.0
    center = 0.5
    half_width = 0.009
    desert_cutoff = 0.2

    maps = {"height", "wetness"}
    tiles = {"water"}

    def __init__(self):
        super().__init__()
        self.desert = DesertFeature()

    def get_influence(self, context, x, y):
        if abs(context.maps["wetness"].get(x, y) - self.center) > self.half_width:
            return 0.0

        return 0.0 if self.desert.get_influence(context, x, y) > self.desert_cutoff else 1.0

    def generate_tile(self, context, x, y):
        return context.tiles["water"]