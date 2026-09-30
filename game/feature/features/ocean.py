from ..feature import Feature

class OceanFeature(Feature):
    name = "ocean"
    priority = 2
    blend_width = 0.0
    sea_level = 0.3

    maps = {"height"}
    tiles = {"water"}

    def get_influence(self, context, x, y):
        return 1.0 if context.maps["height"].get(x, y) <= self.sea_level else 0.0

    def generate_tile(self, context, x, y):
        return context.tiles["water"]