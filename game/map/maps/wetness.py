from ..map import Map

class WetnessMap(Map):
    MAP_NAME = "wetness"
    tags = {"climate"}

    def __init__(self, width, height):
        super().__init__(
            self.MAP_NAME,
            width,
            height,
            parameters={
                "noise_scale": 0.025,
                "noise_offset": 4000,
                "average": 0.5,
                "variation": 0.5,
                "dry_scale": 0.006,
                "dry_offset": 9000,
                "dry_threshold": 0.35,
                "dry_softness": 0.15,
                "dry_strength": 0.9,
            },
        )

    def generate(self, generator):
        noise_scale = self.parameters["noise_scale"]
        noise_offset = self.parameters["noise_offset"]
        average = self.parameters["average"]
        variation = self.parameters["variation"]
        dry_scale = self.parameters["dry_scale"]
        dry_offset = self.parameters["dry_offset"]
        dry_threshold = self.parameters["dry_threshold"]
        dry_softness = self.parameters["dry_softness"]
        dry_strength = self.parameters["dry_strength"]

        for y in range(self.height):
            for x in range(self.width):
                noise = generator.noise(x, y, scale=noise_scale, offset=noise_offset)
                value = average + noise * variation

                dry_noise = generator.noise(x, y, scale=dry_scale, offset=dry_offset)
                t = min(1.0, max(0.0, (dry_noise - dry_threshold) / dry_softness))
                dryness = t * t * (3 - 2 * t)

                self.set(x, y, self.normalize(value * (1 - dry_strength * dryness)))