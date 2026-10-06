from ..feature import Feature

def deterministic_sin(x: float) -> float:
    x = (x + 3.141592653589793) % 6.283185307179586 - 3.141592653589793
    return 1.2732395447351627 * x - 0.4052847345693511 * x * abs(x)

class DunesFeature(Feature):
    name = "dunes"
    blend_width = 0.1
    wave_x = 0.32
    wave_y = 0.18
    wind_warp = 14.0
    favor_strength = 0.8
    favor_scale = 0.012

    maps = {"temperature", "wetness", "height", "wind"}
    tiles = {"sand", "sandstone", "gravel"}

    def get_influence(self, context, x, y):
        temperature = self.smooth_influence(context.maps["temperature"].get(x, y), 0.70, 0.35)
        wetness = self.smooth_influence(context.maps["wetness"].get(x, y), 0.10, 0.50)
        height = self.smooth_influence(context.maps["height"].get(x, y), 0.35, 0.35)
        wind = self.smooth_influence(context.maps["wind"].get(x, y), 0.75, 0.50)
        return temperature * wetness * height * wind

    def generate_tile(self, context, x, y):
        wind = context.maps["wind"].get(x, y)
        wetness = context.maps["wetness"].get(x, y)
        ridge = deterministic_sin(x * self.wave_x + y * self.wave_y + wind * self.wind_warp)

        if ridge > -0.6:
            return context.tiles["sand"]

        if wetness < 0.08 and context.random.random() < 0.6:
            return context.tiles["sandstone"]

        return context.tiles["gravel"] if context.random.random() < 0.3 else context.tiles["sand"]
