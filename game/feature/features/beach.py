from ..feature import Feature
from .ocean import OceanFeature

class BeachFeature(Feature):
    name = "beach"
    blend_width = 0.01
    band = 0.0005
    fade = 0.007
    cold_temperature = 0.25
    

    maps = {"height", "temperature"}
    tiles = {"sand", "gravel"}

    def get_influence(self, context, x, y):
        height = context.maps["height"].get(x, y)

        if height <= OceanFeature.sea_level:
            return 0.0

        return min(1.0, max(0.0, (OceanFeature.sea_level + self.band + self.fade - height) / self.fade))

    def generate_tile(self, context, x, y):
        if context.maps["temperature"].get(x, y) < self.cold_temperature:
            return context.tiles["gravel"]

        return context.tiles["sand"]