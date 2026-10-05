from dataclasses import dataclass, field

from ..tile.tile import Tile


@dataclass
class World:
    """
    The complete state of the game world.

    World owns the tiles and is responsible for changing world state.
    Rendering code should read from World, but should not modify it.
    All tile changes must go through set_tile().
    """

    width: int
    height: int
    default_tile: Tile

    # The actual world data.
    # tiles[y][x] -> Tile
    tiles: list[list[Tile]] = field(init=False)

    # Number of simulation updates that have occurred.
    tick: int = field(default=0, init=False)

    # Change log for multiplayer. Clients regenerate the terrain from the seed,
    # so only changes made AFTER generation are recorded (Simulation turns recording on).
    # changes: (x, y) -> tile name, latest value only
    # dirty: positions changed since the last take_dirty() call
    recording: bool = field(default=False, init=False)
    changes: dict[tuple[int, int], str] = field(default_factory=dict, init=False, repr=False)
    dirty: set[tuple[int, int]] = field(default_factory=set, init=False, repr=False)

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

    def set_tile(self, x: int, y: int, tile: Tile) -> bool:
        """
        Replace the tile at a world coordinate.

        This is the only way tiles should change. Returns True if the tile was replaced.
        """

        self._validate_coordinates(x, y)
        current = self.tiles[y][x]

        if current is tile:
            return False

        self.tiles[y][x] = tile

        if self.recording and current.name != tile.name:
            self.changes[(x, y)] = tile.name
            self.dirty.add((x, y))

        return True

    def take_dirty(self) -> list[tuple[int, int, str]]:
        """Return (x, y, tile_name) for every tile changed since the last call, then clear."""

        changed = [(x, y, self.tiles[y][x].name) for x, y in sorted(self.dirty)]
        self.dirty.clear()
        return changed

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
        Any tile change made here must also go through set_tile().
        """

        pass


    # Utilities
    def fill(self, tile: Tile) -> None:
        """Fill the entire world with one tile type. Generation only."""

        if self.recording:
            raise RuntimeError("fill() bypasses the change log; use set_tile() once the game has started.")

        for y in range(self.height):
            for x in range(self.width):
                self.tiles[y][x] = tile

    def _validate_coordinates(self, x: int, y: int) -> None:
        if not self.is_inside(x, y):
            raise IndexError(
                f"World coordinate ({x}, {y}) is outside "
                f"the {self.width}x{self.height} world."
            )