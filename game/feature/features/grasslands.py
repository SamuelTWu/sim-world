from ..feature import Feature

class GrasslandFeature(Feature):
    name = "grassland"
    blend_width = 0.2

    maps = {"temperature", "wetness", "height", "fertility"}
    tiles = {"grass", "tree", "flower", "mud"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.50, 0.60)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.20, 0.60)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.30, 0.70)

        return temperature * wetness * height

    def generate_tile(self, context, x, y):
        wetness = context.maps["wetness"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        height = context.maps["height"].get(x, y)

        flower_influence = self.smooth_influence(fertility, 0.7, 0.80) * self.smooth_influence(wetness, 0.25, 0.65)
        tree_influence = self.smooth_influence(wetness, 0.35, 0.70) * self.smooth_influence(fertility, 0.30, 0.75) * self.smooth_influence(height, 0.20, 0.80)

        if flower_influence > 0.65 and context.random.random() < flower_influence:
            return context.tiles["flower"]

        if tree_influence > 0.50 and context.random.random() < tree_influence * 0.4:
            return context.tiles["tree"]

        if abs(wetness-.5) < .011 and context.random.random()<(wetness-.1):
                    return context.tiles["mud"]

        return context.tiles["grass"]