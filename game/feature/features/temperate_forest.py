from ..feature import Feature

class TemperateForestFeature(Feature):
    name = "temperate_forest"
    blend_width = 0.1

    maps = {"temperature", "wetness", "fertility", "height"}
    tiles = {"grass", "tree", "flower", "mud", "stone"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.25, 0.4)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.35, 0.4)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.40, 0.8)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.20, 0.4)

        return temperature * wetness * fertility * height

    def generate_tile(self, context, x, y):
        wetness = context.maps["wetness"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        height = context.maps["height"].get(x, y)

        tree_influence = self.smooth_influence(wetness, 0.35, 0.75) * self.smooth_influence(fertility, 0.40, 0.85)
        flower_influence = self.smooth_influence(wetness, 0.35, 0.70) * self.smooth_influence(fertility, 0.55, 0.90)
        mud_influence = self.smooth_influence(wetness, 0.55, 0.90) * self.smooth_influence(fertility, 0.30, 0.70)
        stone_influence = self.smooth_influence(height, 0.70, 0.95) * self.smooth_influence(fertility, 0.40, 0.05)

        if tree_influence > 0.55:
            return context.tiles["tree"]

        if flower_influence > 0.70 and context.random.random() < flower_influence * 0.65:
            return context.tiles["flower"]

        if mud_influence > 0.60:
            return context.tiles["mud"]

        if stone_influence > 0.80 and context.random.random() < 0.15:
            return context.tiles["stone"]

        return context.tiles["grass"]