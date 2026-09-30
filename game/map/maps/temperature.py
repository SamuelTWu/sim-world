from ..map import Map

class TemperatureMap(Map):
    MAP_NAME = "temperature"
    tags = {"climate"}


    def __init__(self, width, height):
        super().__init__(
            self.MAP_NAME,
            width,
            height,
            parameters={
                "gradient": 1.0,
                "variation": 0.25,
                "average": 0.5,
                "noise_scale": 0.03,
                "noise_offset": 2000,
            },
        )

    def generate(self, generator):
        gradient = self.parameters["gradient"]
        variation = self.parameters["variation"]
        average = self.parameters["average"]
        noise_scale = self.parameters["noise_scale"]
        noise_offset = self.parameters["noise_offset"]

        for y in range(self.height):
            latitude = y / max(1, self.height - 1)
            temperature_gradient = (latitude - 0.5) * gradient

            for x in range(self.width):
                noise = generator.noise(x, y, scale=noise_scale, offset=noise_offset)
                value = average + temperature_gradient + noise * variation
                self.set(x, y, self.normalize(value))