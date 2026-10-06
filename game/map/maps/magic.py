import math

from ..map import Map

def deterministic_exp(x: float) -> float:
    if x <= -16.0:
        return 0.0

    if x >= 0.0:
        return 1.0

    k = int(x / 0.6931471805599453)
    r = x - k * 0.6931471805599453
    result = (
        1.0
        + r
        + r * r * 0.5
        + r * r * r / 6.0
        + r * r * r * r / 24.0
        + r * r * r * r * r / 120.0
    )
    if k >= 0:
        return result * (2.0 ** k)
    return result / (2.0 ** (-k))


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
                value = deterministic_exp( -(distance ** 2) / (2.0 * size ** 2))
                self.set(x, y, self.normalize(value))