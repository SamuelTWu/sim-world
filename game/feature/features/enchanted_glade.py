from ..feature import Feature

class EnchantedGladeFeature(Feature):
    name = "enchanted_glade"
    blend_width = 0.4

    maps = {"magic", "fertility", "wetness", "temperature", "height"}
    tiles = {"grass", "flower", "tree", "moss", "blessed_earth"}

    def get_influence(self, context, x, y):
        magic = self.smooth_influence(context.maps["magic"].get(x, y), 0.60, 0.35)

        return magic

    def generate_tile(self, context, x, y):
        magic = context.maps["magic"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)

        blessed_influence = self.smooth_influence(magic, 0.75, 0.30) * self.smooth_influence(fertility, 0.80, 0.30)
        flower_influence = self.smooth_influence(fertility, 0.75, 0.35) * self.smooth_influence(wetness, 0.55, 0.35)
        tree_influence = self.smooth_influence(wetness, 0.55, 0.40) * self.smooth_influence(fertility, 0.65, 0.40)
        moss_influence = self.smooth_influence(wetness, 0.70, 0.30)

        if blessed_influence > 0.3:
            return context.tiles["blessed_earth"]

        if flower_influence > 0.45 and context.random.random() < flower_influence * 0.35:
            return context.tiles["flower"]

        if tree_influence > 0.40 and context.random.random() < tree_influence * 0.25:
            return context.tiles["tree"]

        if moss_influence > 0.50 and context.random.random() < moss_influence * 0.3:
            return context.tiles["moss"]

        return context.tiles["grass"]