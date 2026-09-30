from ..map import Map

class FertilityMap(Map):
    MAP_NAME = "fertility"
    tags = {}

    def __init__(self, width, height):
        super().__init__("fertility", width, height)

    def generate(self, generator):
        for y in range(self.height):
            for x in range(self.width):
                value = generator.noise(x, y, scale=0.018, offset=7000)
                value = (value + 1.0) / 2.0
                self.set(x, y, self.normalize(value))