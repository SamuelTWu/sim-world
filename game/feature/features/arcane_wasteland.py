from ..feature import Feature

class ArcaneWastelandFeature(Feature):
    name = "arcane_wasteland"

    maps = {"magic", "fertility", "wetness", "temperature", "height"}
    tiles = {"void_stone", "cursed_earth", "blessed_earth", "emberstone", "stone"}

    def get_influence(self, context, x, y):
        magic = context.maps["magic"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        temperature = context.maps["temperature"].get(x, y)
        height = context.maps["height"].get(x, y)

        return self.smooth_influence(magic, 0.45, 0.90) * self.smooth_influence(fertility, 0.45, 0.10) * self.smooth_influence(wetness, 0.55, 0.10) * self.smooth_influence(temperature, 0.20, 0.80) * self.smooth_influence(height, 0.40, 0.75)

    def generate_tile(self, context, x, y):
        magic = context.maps["magic"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        temperature = context.maps["temperature"].get(x, y)

        void_influence = self.smooth_influence(magic, 0.65, 1.0) * self.smooth_influence(fertility, 0.35, 0.0)
        curse_influence = self.smooth_influence(magic, 0.50, 0.85) * self.smooth_influence(fertility, 0.45, 0.05) * self.smooth_influence(wetness, 0.50, 0.10)
        blessing_influence = self.smooth_influence(magic, 0.55, 0.90) * self.smooth_influence(fertility, 0.10, 0.60) * self.smooth_influence(wetness, 0.10, 0.50)
        emberstone_influence = self.smooth_influence(magic, 0.55, 0.80) * self.smooth_influence(temperature, 0.45, 0.90)

        if void_influence > 0.70:
            return context.tiles["void_stone"]

        if curse_influence > 0.65:
            return context.tiles["cursed_earth"]

        if blessing_influence > 0.70:
            return context.tiles["blessed_earth"]

        if emberstone_influence > 0.60:
            return context.tiles["emberstone"]

        return context.tiles["stone"]