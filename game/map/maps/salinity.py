from ..map import Map

class SalinityMap(Map):
    MAP_NAME = "salinity"
    tags = {}

    def __init__(self, width, height):
        super().__init__(
            self.MAP_NAME,
            width,
            height,
            parameters={
                "noise_scale": 0.01,
                "noise_offset": 41000,
                "crust_scale": 0.05,
                "crust_offset": 47000,
                "crust_weight": 0.3,
                "threshold": 0.25,
                "softness": 0.35,
            },
        )

    def generate(self, generator):
        noise_scale = self.parameters["noise_scale"]
        noise_offset = self.parameters["noise_offset"]
        crust_scale = self.parameters["crust_scale"]
        crust_offset = self.parameters["crust_offset"]
        crust_weight = self.parameters["crust_weight"]
        threshold = self.parameters["threshold"]
        softness = self.parameters["softness"]

        for y in range(self.height):
            for x in range(self.width):
                broad = generator.noise(x, y, scale=noise_scale, offset=noise_offset)
                crust = 1.0 - abs(generator.noise(x, y, scale=crust_scale, offset=crust_offset))
                t = min(1.0, max(0.0, (broad + crust * crust_weight - threshold) / softness))

                self.set(x, y, self.normalize(t * t * (3 - 2 * t)))