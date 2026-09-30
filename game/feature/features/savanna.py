from ..feature import Feature

class SavannaFeature(Feature):
    name = "savanna"
    blend_width = 0.1


    maps = {"temperature", "wetness", "fertility", "height"}
    tiles = {"grass", "tree", "mud", "sand", "flower"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.55, 0.85)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.15, 0.50)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.25, 0.70)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.10, 0.70)

        return temperature * wetness * fertility * height

    def generate_tile(self, context, x, y):
        wetness = context.maps["wetness"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        height = context.maps["height"].get(x, y)

        tree_influence = self.smooth_influence(wetness, 0.25, 0.65) * self.smooth_influence(fertility, 0.35, 0.80) * self.smooth_influence(height, 0.20, 0.75)
        mud_influence = self.smooth_influence(wetness, 0.55, 0.90) * self.smooth_influence(fertility, 0.30, 0.70)
        sand_influence = self.smooth_influence(wetness, 0.30, 0.05) * self.smooth_influence(fertility, 0.35, 0.05)
        flower_influence = self.smooth_influence(fertility, 0.55, 0.85) * self.smooth_influence(wetness, 0.25, 0.65)

        if tree_influence > 0.65 and context.random.random() < tree_influence * 0.45:
            return context.tiles["tree"]

        if mud_influence > 0.65 and context.random.random() < mud_influence:
            return context.tiles["mud"]

        if sand_influence > 0.65 and context.random.random() < sand_influence * 0.3:
            return context.tiles["sand"]

        if flower_influence > 0.75 and context.random.random() < flower_influence * 0.25:
            return context.tiles["flower"]

        return context.tiles["grass"]