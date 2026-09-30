from ..feature import Feature

class VolcanicWastelandFeature(Feature):
    name = "volcanic_wasteland"
    blend_width = 0
    priority = 3


    maps = {"temperature", "height", "wetness", "fertility", "magic"}
    tiles = {"lava", "ash", "emberstone", "stone", "gravel"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.55, 0.85)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.45, 0.75)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.25, 0.3)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.35, 0.3)
        magic = self.smooth_influence(context.maps["magic"].get(x, y), 0.30, 0.45)

        return temperature * height * wetness * fertility * magic

    def generate_tile(self, context, x, y):
        temperature = context.maps["temperature"].get(x, y)
        height = context.maps["height"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)

        lava_influence = self.smooth_influence(temperature, 0.65, 0.4) * self.smooth_influence(height, 0.50, 0.85) 
        ember_influence = self.smooth_influence(temperature, 0.60, 0.4) * self.smooth_influence(height, 0.35, 0.70)
        ash_influence = self.smooth_influence(temperature, 0.55, 0.45) * self.smooth_influence(fertility, 0.25, 0.02)
        gravel_influence = self.smooth_influence(height, 0.45, 0.30)

        if lava_influence > 0.30:
            return context.tiles["lava"]

        if ember_influence > 0.55:
            return context.tiles["emberstone"]

        if ash_influence > 0.15:
            return context.tiles["ash"]

        if gravel_influence > 0.20:
            return context.tiles["gravel"]

        return context.tiles["stone"]