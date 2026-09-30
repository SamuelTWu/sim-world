from ..feature import Feature

class SwampFeature(Feature):
    name = "swamp"
    blend_width = 0.1


    maps = {"wetness", "temperature", "height", "fertility"}
    tiles = {"mud", "grass", "water", "tree", "flower"}

    def get_influence(self, context, x, y):
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.55, 0.95)
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.35, 0.75)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.50, 0.05)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.35, 0.85)

        return wetness * temperature * height * fertility

    def generate_tile(self, context, x, y):
        wetness = context.maps["wetness"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        height = context.maps["height"].get(x, y)

        water_influence = self.smooth_influence(wetness, 0.65, 0.95) * self.smooth_influence(height, 0.35, 0.05)
        tree_influence = self.smooth_influence(wetness, 0.45, 0.80) * self.smooth_influence(fertility, 0.45, 0.85)
        flower_influence = self.smooth_influence(wetness, 0.40, 0.75) * self.smooth_influence(fertility, 0.50, 0.90)
        grass_influence = self.smooth_influence(wetness, 0.30, 0.60) * self.smooth_influence(fertility, 0.30, 0.80)

        if water_influence > 0.65:
            return context.tiles["water"]

        if tree_influence > 0.65 and context.random.random() < tree_influence * 0.35:
            return context.tiles["tree"]

        if flower_influence > 0.65 and context.random.random() < flower_influence * 0.55:
            return context.tiles["flower"]

        if grass_influence > 0.45:
            return context.tiles["grass"]

        return context.tiles["mud"]