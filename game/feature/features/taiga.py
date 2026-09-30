from ..feature import Feature

class TaigaFeature(Feature):
    name = "taiga"
    blend_width = 0.15

    maps = {"temperature", "wetness", "fertility", "height"}
    tiles = {"tree", "grass", "dirt", "snow", "packed_snow", "permafrost", "stone"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.22, 0.12)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.50, 0.8)
        fertility = self.smooth_influence(context.maps["fertility"].get(x, y), 0.40, 0.12)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.45, 0.12)

        return temperature * wetness * fertility * height

    def generate_tile(self, context, x, y):
        temperature = context.maps["temperature"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        fertility = context.maps["fertility"].get(x, y)
        height = context.maps["height"].get(x, y)

        tree_influence = self.smooth_influence(wetness, 0.50, 0.45) * self.smooth_influence(fertility, 0.40, 0.45)
        snow_influence = self.smooth_influence(temperature, 0.10, 0.20)
        frozen_influence = self.smooth_influence(temperature, 0.15, 0.15) * self.smooth_influence(wetness, 0.25, 0.30)
        stone_influence = self.smooth_influence(height, 0.85, 0.25)

        if tree_influence > 0.30 and context.random.random() < tree_influence * 0.7:
            return context.tiles["tree"]

        if stone_influence > 0.55 and context.random.random() < stone_influence * 0.4:
            return context.tiles["stone"]

        if snow_influence > 0.45 and context.random.random() < snow_influence * 0.6:
            return context.tiles["snow"] if context.random.random() < 0.6 else context.tiles["packed_snow"]

        if frozen_influence > 0.50 and context.random.random() < frozen_influence * 0.4:
            return context.tiles["permafrost"]

        return context.tiles["dirt"] if context.random.random() < 0.5 else context.tiles["grass"]