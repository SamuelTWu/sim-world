from ..map import Map

class HeightMap(Map):
    MAP_NAME = "height"
    tags = {"terrain"}

    def __init__(self, width, height):
        super().__init__(
            self.MAP_NAME,
            width,
            height,
            parameters={
                "continent_size": 0.9,
                "land_amount": 0.9,
                "coastline_roughness": 0.5,
                "noise_scale": 0.015,
                "detail_scale": 4.0,
                "edge_falloff": 0.35,
                "detail_weight": 0.25,
            },
        )
        self.land_threshold = 0.5

    def generate(self, generator):
        continent_size = max(0.05, self.parameters["continent_size"])
        land_amount = self.normalize(self.parameters["land_amount"])
        coastline_roughness = self.normalize(self.parameters["coastline_roughness"])
        noise_scale = self.parameters["noise_scale"]
        detail_scale = self.parameters["detail_scale"]
        edge_falloff = self.parameters["edge_falloff"]
        detail_weight = self.parameters["detail_weight"]

        self.land_threshold = 0.5 + (0.5 - land_amount) * 0.5
        scale = noise_scale / continent_size

        for y in range(self.height):
            for x in range(self.width):
                elevation = (generator.noise(x, y, scale=scale, offset=0) + 1.0) / 2.0
                detail = (generator.noise(x, y, scale=scale * detail_scale, offset=5000) + 1.0) / 2.0

                elevation = elevation * (1.0 - coastline_roughness * detail_weight) + detail * (coastline_roughness * detail_weight)

                normalized_x = x / max(1, self.width - 1)
                normalized_y = y / max(1, self.height - 1)
                edge_distance = max(abs(normalized_x - 0.5), abs(normalized_y - 0.5)) * 2.0

                elevation -= edge_distance ** 2 * edge_falloff
                self.set(x, y, self.normalize(elevation))

    def is_land(self, x, y):
        return self.get(x, y) >= self.land_threshold