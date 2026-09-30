from ..feature import Feature
from .ocean import OceanFeature

class CoralReefFeature(Feature):
    name = "coral_reef"
    priority = 3
    blend_width = 0.0
    depth = 0.1
    min_temperature = 0.55
    shallows = 0.03

    maps = {"height", "temperature"}
    tiles = { "sand", "water"}

    def get_influence(self, context, x, y):
        height = context.maps["height"].get(x, y)

        if height > OceanFeature.sea_level or height < OceanFeature.sea_level - self.depth:
            return 0.0

        return 1.0 if context.maps["temperature"].get(x, y) >= self.min_temperature else 0.0

    def generate_tile(self, context, x, y):
        height = context.maps["height"].get(x, y)
        warmth = self.smooth_influence(context.maps["temperature"].get(x, y), 1.0, 1.0 - self.min_temperature)
        depth = (OceanFeature.sea_level - height) / self.depth
        density = warmth * self.smooth_influence(depth, 0.5, 0.5)

        if height > OceanFeature.sea_level - self.shallows and context.random.random() < 0.3:
            return context.tiles["sand"]

        return context.tiles["water"]