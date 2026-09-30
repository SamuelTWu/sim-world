class Map:
    tags = frozenset()
    
    def __init__(self, name: str, width: int, height: int, parameters=None):
        self.name = name
        self.width = width
        self.height = height
        self.parameters = parameters or {}
        self.values = [[0.0 for _ in range(width)] for _ in range(height)]

    def get(self, x: int, y: int) -> float:
        return self.values[y][x]

    def set(self, x: int, y: int, value: float):
        self.values[y][x] = value

    def normalize(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def generate(self, generator):
        raise NotImplementedError
