from ..feature import Feature

class JungleFeature(Feature):
    name = "jungle"
    blend_width = 0.15

    maps = {"temperature", "wetness", "fertility", "height"}
    tiles = {"tree", "grass", "moss", "mud", "clay", "laterite"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.80, 0.35)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.80, 0.40)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.65, 0.50)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.40, 0.50)

        return temperature * wetness * fertility * height

    def generate_tile(self, context, x, y):
        wetness = context.maps["wetness"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        height = context.maps["height"].get(x, y)

        tree_influence = self.smooth_influence(wetness, 0.75, 0.50) * self.smooth_influence(fertility, 0.65, 0.50)
        moss_influence = self.smooth_influence(wetness, 0.90, 0.30) * self.smooth_influence(height, 0.45, 0.40)
        mud_influence = self.smooth_influence(wetness, 0.95, 0.20) * self.smooth_influence(height, 0.30, 0.25)
        clay_influence = self.smooth_influence(wetness, 0.70, 0.25) * self.smooth_influence(height, 0.32, 0.12)
        laterite_influence = self.smooth_influence(fertility, 0.25, 0.25) * self.smooth_influence(wetness, 0.60, 0.40)

        if tree_influence > 0.35 and context.random.random() < tree_influence * 0.75:
            return context.tiles["tree"]

        if mud_influence > 0.60:
            return context.tiles["mud"]

        if clay_influence > 0.55:
            return context.tiles["clay"]

        if moss_influence > 0.50 and context.random.random() < moss_influence * 0.6:
            return context.tiles["moss"]

        if laterite_influence > 0.45:
            return context.tiles["laterite"]

        return context.tiles["grass"]