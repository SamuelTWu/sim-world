from ..feature import Feature

class ArcticFeature(Feature):
    name = "arctic"
    blend_width = 0.15

    maps = {"temperature", "wetness", "height", "fertility"}
    tiles = {"snow", "packed_snow", "ice", "permafrost", "stone", "gravel"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.1, 0.35)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.40, 0.70)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.45, 0.60)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.15, 0.60)

        return temperature * wetness * height * fertility

    def generate_tile(self, context, x, y):
        temperature = context.maps["temperature"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        height = context.maps["height"].get(x, y)

        ice_influence = self.smooth_influence(temperature, 0.0, 0.15) * self.smooth_influence(wetness, 0.65, 0.35) * self.smooth_influence(height, 0.32, 0.12)
        permafrost_influence = self.smooth_influence(temperature, 0.12, 0.15) * self.smooth_influence(wetness, 0.20, 0.30)
        stone_influence = self.smooth_influence(height, 0.80, 0.25)
        gravel_influence = self.smooth_influence(height, 0.65, 0.20) * self.smooth_influence(temperature, 0.20, 0.25)
        packed_influence = self.smooth_influence(temperature, 0.08, 0.20) * self.smooth_influence(height, 0.55, 0.30)

        if ice_influence > 0.50:
            return context.tiles["ice"]

        if stone_influence > 0.55 and context.random.random() < stone_influence * 0.5:
            return context.tiles["stone"]

        if gravel_influence > 0.55 and context.random.random() < gravel_influence * 0.4:
            return context.tiles["gravel"]

        if permafrost_influence > 0.55 and context.random.random() < permafrost_influence * 0.5:
            return context.tiles["permafrost"]

        if packed_influence > 0.50 and context.random.random() < packed_influence * 0.5:
            return context.tiles["packed_snow"]

        return context.tiles["snow"]
        