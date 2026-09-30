import math

from ..map import Map

class MagicMap(Map):
    MAP_NAME = "magic"
    tags = {}

    def __init__(self, width, height):
        super().__init__("magic", width, height)

    def generate(self, generator):
        center_x = generator.random.uniform(0, self.width)
        center_y = generator.random.uniform(0, self.height)
        size = max(1.0, self.width * 0.08)

        for y in range(self.height):
            for x in range(self.width):
                distance = math.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
                value = math.exp(-(distance ** 2) / (2.0 * size ** 2))
                self.set(x, y, self.normalize(value))