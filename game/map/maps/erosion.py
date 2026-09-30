from ..map import Map

class ErosionMap(Map):
    MAP_NAME = "erosion"
    tags = {"terrain"}

    def __init__(self, width, height):
        super().__init__(
            self.MAP_NAME,
            width,
            height,
            parameters={
                "noise_scale": 0.02,
                "noise_offset": 7000,
                "detail_scale": 0.08,
                "detail_offset": 12000,
                "detail_weight": 0.35,
                "sharpness": 2.0,
            },
        )

    def generate(self, generator):
        noise_scale = self.parameters["noise_scale"]
        noise_offset = self.parameters["noise_offset"]
        detail_scale = self.parameters["detail_scale"]
        detail_offset = self.parameters["detail_offset"]
        detail_weight = self.parameters["detail_weight"]
        sharpness = self.parameters["sharpness"]

        for y in range(self.height):
            for x in range(self.width):
                broad = 1.0 - abs(generator.noise(x, y, scale=noise_scale, offset=noise_offset))
                fine = 1.0 - abs(generator.noise(x, y, scale=detail_scale, offset=detail_offset))
                value = (broad * (1 - detail_weight) + fine * detail_weight) ** sharpness

                self.set(x, y, self.normalize(value))