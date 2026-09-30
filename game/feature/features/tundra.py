from ..feature import Feature

class TundraFeature(Feature):
    name = "tundra"
    blend_width = 0.1

    maps = {"temperature", "wetness", "height", "fertility"}
    tiles = {"snow", "stone", "gravel", "mud"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.25, 0.3)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.25, 0.65)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.20, 0.75)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.30, 0.5)

        return temperature * wetness * height * fertility

    def generate_tile(self, context, x, y):
        temperature = context.maps["temperature"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        height = context.maps["height"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)

        snow_influence = self.smooth_influence(temperature, 0.25, 0.02) * self.smooth_influence(height, 0.25, 0.85)
        gravel_influence = self.smooth_influence(temperature, 0.35, 0.05) * self.smooth_influence(height, 0.45, 0.85)
        mud_influence = self.smooth_influence(wetness, 0.45, 0.80) * self.smooth_influence(fertility, 0.15, 0.45)

        if snow_influence > 0.55:
            return context.tiles["snow"]

        if gravel_influence > 0.70:
            return context.tiles["gravel"]

        if mud_influence > 0.65:
            return context.tiles["mud"]

        return context.tiles["stone"]