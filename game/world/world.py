from dataclasses import dataclass, field

from ..tile.tile import Tile


@dataclass
class World:
    """
    The complete state of the game world.

    World owns the tiles and is responsible for changing world state.
    Rendering code should read from World, but should not modify it.
    """

    width: int
    height: int
    default_tile: Tile

    # The actual world data.
    # tiles[y][x] -> Tile
    tiles: list[list[Tile]] = field(init=False)

    # Number of simulation updates that have occurred.
    tick: int = field(default=0, init=False)

    def __post_init__(self):
        if self.width <= 0:
            raise ValueError("World width must be greater than 0.")

        if self.height <= 0:
            raise ValueError("World height must be greater than 0.")

        self.tiles = [
            [self.default_tile for _ in range(self.width)]
            for _ in range(self.height)
        ]

    # Tile access
    def get_tile(self, x: int, y: int) -> Tile:
        """Return the tile at a world coordinate."""

        self._validate_coordinates(x, y)
        return self.tiles[y][x]

    def set_tile(self, x: int, y: int, tile: Tile) -> None:
        """Replace the tile at a world coordinate."""

        self._validate_coordinates(x, y)
        self.tiles[y][x] = tile

    def is_inside(self, x: int, y: int) -> bool:
        """Return True if the coordinate is inside the world."""

        return (
            0 <= x < self.width
            and 0 <= y < self.height
        )


    # World updates
    def update(self, delta_time: float) -> None:
        """
        Advance the simulation.

        This is where world systems can eventually be updated:
        - water movement
        - fire
        - plant growth
        - temperature
        - weather
        - erosion
        - NPCs
        """

        self.tick += 1

        self._update_tiles(delta_time)

    def _update_tiles(self, delta_time: float) -> None:
        """
        Update tile-based simulation.

        Currently empty, but this is where simulation logic can be added.
        """

        pass


    # Utilities
    def fill(self, tile: Tile) -> None:
        """Fill the entire world with one tile type."""

        for y in range(self.height):
            for x in range(self.width):
                self.tiles[y][x] = tile

    def _validate_coordinates(self, x: int, y: int) -> None:
        if not self.is_inside(x, y):
            raise IndexError(
                f"World coordinate ({x}, {y}) is outside "
                f"the {self.width}x{self.height} world."
            )
