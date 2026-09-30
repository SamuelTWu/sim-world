from ..feature import Feature

class DesertFeature(Feature):
    name = "desert"
    blend_width = 0.1

    maps = {"temperature", "wetness", "height"}
    tiles = {"sand", "gravel", "mud", "ash"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.60, 0.8)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.10, 0.6)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.55, 0.6)

        return temperature * wetness * height

    def generate_tile(self, context, x, y):
        temperature = context.maps["temperature"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        height = context.maps["height"].get(x, y)

        if wetness > 0.6:
            return context.tiles["mud"]

        if temperature > 0.80 and wetness < 0.10:
            return context.tiles["ash"]

        if height > 0.65:
            return context.tiles["gravel"]

        return context.tiles["sand"]