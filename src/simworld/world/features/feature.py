class Feature:
    name = "feature"
    maps = set()
    tiles = set()
    entities = set()

    blend_width = 0.1
    blend_overrides = {}
    priority = 0

    def __init__(self):
        self.debug_data = []

    def generate(self, context):
        pass

    def get_influence(self, context, x, y):
        return 0.0

    def generate_tile(self, context, x, y):
        return None

    def generate_entities(self, context, x, y):
        return []

    def border_width(self, other):
        return self.blend_overrides.get(other.name, self.blend_width)

    def get_debug_data(self):
        return self.debug_data

    def initialize_debug_data(self, world):
        self.debug_data = [[0.0 for _ in range(world.width)] for _ in range(world.height)]

    def record_debug_data(self, x, y, value):
        if not self.debug_data:
            return

        self.debug_data[y][x] = value

    def initialize_generation(self, context):
        self.initialize_debug_data(context.world)

    @staticmethod
    def smooth_influence(value, center, width):
        if width <= 0:
            return 1.0 if value >= center else 0.0

        return max(0.0, 1.0 - abs(value - center) / width)