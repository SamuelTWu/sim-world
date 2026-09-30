from ..feature import Feature

class StoneyPeaksFeature(Feature):
    name = "stoney_peaks"
    blend_width = 0.1


    maps = {"height", "temperature", "wetness", "fertility"}
    tiles = {"stone", "gravel", "snow", "ash"}

    def get_influence(self, context, x, y):
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.60, 0.95)
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.55, 0.20)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.65, 0.20)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.40, 0.05)

        return height * temperature * wetness * fertility

    def generate_tile(self, context, x, y):
        height = context.maps["height"].get(x, y)
        temperature = context.maps["temperature"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)

        snow_influence = self.smooth_influence(height, 0.70, 0.95) * self.smooth_influence(temperature, 0.45, 0.10)
        gravel_influence = self.smooth_influence(height, 0.55, 0.85) * self.smooth_influence(temperature, 0.60, 0.20)
        ash_influence = self.smooth_influence(height, 0.40, 0.15) * self.smooth_influence(temperature, 0.35, 0.05) * self.smooth_influence(wetness, 0.50, 0.05)

        if snow_influence > 0.65:
            return context.tiles["snow"]

        if ash_influence > 0.70:
            return context.tiles["ash"]

        if gravel_influence > 0.50:
            return context.tiles["gravel"]

        return context.tiles["stone"]