from ..map import Map

class RuinsMap(Map):
    MAP_NAME = "ruins"
    tags = {}

    def __init__(self, width, height):
        super().__init__(
            self.MAP_NAME,
            width,
            height,
            parameters={
                "noise_scale": 0.012,
                "noise_offset": 15000,
                "edge_scale": 0.06,
                "edge_offset": 21000,
                "edge_weight": 0.25,
                "threshold": 0.45,
                "softness": 0.2,
            },
        )

    def generate(self, generator):
        noise_scale = self.parameters["noise_scale"]
        noise_offset = self.parameters["noise_offset"]
        edge_scale = self.parameters["edge_scale"]
        edge_offset = self.parameters["edge_offset"]
        edge_weight = self.parameters["edge_weight"]
        threshold = self.parameters["threshold"]
        softness = self.parameters["softness"]

        for y in range(self.height):
            for x in range(self.width):
                broad = generator.noise(x, y, scale=noise_scale, offset=noise_offset)
                edge = generator.noise(x, y, scale=edge_scale, offset=edge_offset)
                t = min(1.0, max(0.0, (broad + edge * edge_weight - threshold) / softness))

                self.set(x, y, self.normalize(t * t * (3 - 2 * t)))