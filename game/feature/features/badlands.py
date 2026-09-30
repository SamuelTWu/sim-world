from ..feature import Feature

class BadlandsFeature(Feature):
    name = "badlands"
    blend_width = 0.1

    maps = {"temperature", "wetness", "height", "erosion"}
    tiles = {"sandstone", "clay", "laterite", "sand", "gravel"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.65, 0.35)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.15, 0.35)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.55, 0.45)
        erosion = self.smooth_influence(context.maps["erosion"].get(x, y), 0.80, 0.50)

        return temperature * wetness * height * erosion

    def generate_tile(self, context, x, y):
        height = context.maps["height"].get(x, y)
        erosion = context.maps["erosion"].get(x, y)

        if erosion > 0.85:
            return context.tiles["gravel"] if context.random.random() < 0.5 else context.tiles["sand"]

        layers = ("sandstone", "clay", "laterite", "sandstone", "sand")

        return context.tiles[layers[int(height * 60) % len(layers)]]