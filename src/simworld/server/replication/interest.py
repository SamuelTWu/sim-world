"""Spatial hash grid of pixels (README 7.1). No networking and no game imports, so it can be tested on its own.

The world is cut into square cells and each pixel is filed under the cell it stands in, so "which pixels are near
this point / in this area" looks at a handful of cells instead of every pixel. A cell is exactly one chunk by
default (CHUNK_SIZE tiles, world/chunks.py), so a chunk's pixels are one dictionary lookup and the grid lines up with
the terrain deltas. Pass a smaller cell_size (a divisor of the chunk size) for denser worlds.

Keep it current with `sync(pixels)` once per tick (the server does this right after the simulation step), or
call `update(id, x, y)` / `remove(id)` yourself. A pixel that stays in its cell costs one comparison.
"""
import math

from src.simworld.world.chunks import CHUNK_SIZE

# A client sees pixels in the cells within this many cells of each of its own pixels (1 = the 3x3 block of cells
# around it, i.e. one chunk in every direction), plus everything inside its camera view.
INTEREST_CELLS = 1

# Camera rectangles are cut down to at most this many tiles on a side, so a client cannot ask for the whole map.
MAX_VIEW_TILES = 160


class SpatialGrid:
    def __init__(self, tile_units, cell_tiles=CHUNK_SIZE):
        if tile_units <= 0 or cell_tiles <= 0:
            raise ValueError("tile_units and cell_tiles must be positive")

        if CHUNK_SIZE % cell_tiles:
            raise ValueError(f"cell_tiles must divide the chunk size ({CHUNK_SIZE}) so cells never straddle chunks")

        self.cell_size = float(tile_units * cell_tiles)
        # (cx, cy) -> {pixel id: (x, y)}
        self.cells = {}
        # pixel id -> (cx, cy)
        self.where = {}

    def cell_of(self, x, y):
        """Cell coordinates holding the world position (x, y)."""
        return math.floor(x / self.cell_size), math.floor(y / self.cell_size)

    def update(self, pixel_id, x, y):
        """Insert a pixel or move it. Returns True if it entered a new cell (or was new)."""
        cell = self.cell_of(x, y)
        old = self.where.get(pixel_id)

        if old == cell:
            self.cells[cell][pixel_id] = (x, y)
            return False

        if old is not None:
            self.drop_from(old, pixel_id)

        self.cells.setdefault(cell, {})[pixel_id] = (x, y)
        self.where[pixel_id] = cell
        return True

    def remove(self, pixel_id):
        """Forget a pixel. Returns True if it was in the grid."""
        cell = self.where.pop(pixel_id, None)

        if cell is None:
            return False

        self.drop_from(cell, pixel_id)
        return True

    def drop_from(self, cell, pixel_id):
        members = self.cells[cell]
        del members[pixel_id]

        if not members:
            del self.cells[cell]

    def sync(self, pixels):
        """Bring the grid in line with an iterable of living pixels (objects with .id and .position.x / .y).

        Moves the ones that moved, adds new ones, and removes pixels that are gone. Returns (added, removed).
        """
        seen = set()
        added = 0

        for pixel in pixels:
            seen.add(pixel.id)

            if pixel.id not in self.where:
                added += 1

            self.update(pixel.id, pixel.position.x, pixel.position.y)

        gone = [pixel_id for pixel_id in self.where if pixel_id not in seen]

        for pixel_id in gone:
            self.remove(pixel_id)

        return added, len(gone)

    def in_cells(self, cells):
        """Ids of the pixels in the given cell coordinates (one chunk's pixels when cell size = chunk size)."""
        found = []

        for cell in cells:
            found.extend(self.cells.get(cell, ()))

        return found

    def in_rect(self, x0, y0, x1, y1):
        """Ids of pixels whose position is inside the rectangle (corners in any order, edges included)."""
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        (cx0, cy0), (cx1, cy1) = self.cell_of(x0, y0), self.cell_of(x1, y1)
        found = []

        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                for pixel_id, (x, y) in self.cells.get((cx, cy), {}).items():
                    if x0 <= x <= x1 and y0 <= y <= y1:
                        found.append(pixel_id)

        return found

    def near(self, x, y, radius):
        """Ids of pixels within `radius` world units of (x, y), nearest first."""
        close = []
        limit = radius * radius

        for pixel_id in self.in_rect(x - radius, y - radius, x + radius, y + radius):
            px, py = self.cells[self.where[pixel_id]][pixel_id]
            distance = (px - x) ** 2 + (py - y) ** 2

            if distance <= limit:
                close.append((distance, pixel_id))

        return [pixel_id for _, pixel_id in sorted(close)]

    def position(self, pixel_id):
        """Where the grid thinks a pixel is, or None."""
        cell = self.where.get(pixel_id)
        return None if cell is None else self.cells[cell][pixel_id]

    def __len__(self):
        return len(self.where)

    def __contains__(self, pixel_id):
        return pixel_id in self.where


def clean_view(rect, width, height, max_size):
    """Make a rectangle sent by a client safe to use: [x0, y0, x1, y1] in world units, corners in any order.

    `width` / `height` are the world's size in world units and `max_size` the largest side allowed. Returns a tuple
    (x0, y0, x1, y1) clipped to the world, shrunk around its centre if too big, or None if it is not four finite numbers.
    """
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        return None

    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in rect):
        return None

    x0, x1 = sorted((float(rect[0]), float(rect[2])))
    y0, y1 = sorted((float(rect[1]), float(rect[3])))

    if x1 - x0 > max_size:
        middle = (x0 + x1) / 2
        x0, x1 = middle - max_size / 2, middle + max_size / 2

    if y1 - y0 > max_size:
        middle = (y0 + y1) / 2
        y0, y1 = middle - max_size / 2, middle + max_size / 2

    x0, x1 = max(0.0, x0), min(float(width), x1)
    y0, y1 = max(0.0, y0), min(float(height), y1)

    if x0 > x1 or y0 > y1:
        return None

    return x0, y0, x1, y1


def in_area(grid, own_pixels, view, x, y, cells_around=INTEREST_CELLS, margin=0.0):
    """True if the world point (x, y) is where a client looks: in the cells around one of its own pixels, or in its camera rectangle (widened by margin).

    The same area visible_ids() uses for pixels, for things that have a place but no id (transient events).
    """
    cx, cy = grid.cell_of(x, y)

    for _, ox, oy in own_pixels:
        ocx, ocy = grid.cell_of(ox, oy)

        if abs(cx - ocx) <= cells_around and abs(cy - ocy) <= cells_around:
            return True

    if view is not None:
        x0, y0, x1, y1 = view
        return x0 - margin <= x <= x1 + margin and y0 - margin <= y <= y1 + margin

    return False


def visible_ids(grid, own_pixels, view=None, cells_around=INTEREST_CELLS, margin=0.0, extra=0.0):
    """The ids of every pixel a client may be told about this tick (README 7.2), as a set.

    own_pixels: [(id, x, y), ...] the client's own pixels. They are always visible, and so is everything in the
    cells within `cells_around` of any of them. `view` is the camera rectangle from clean_view (or None); pixels
    inside it, widened by `margin` world units, are visible too.

    `extra` (world units, default 0) widens every one of those areas on all sides. A client is sent a pixel when it is in
    the set with extra=0 (the ENTER set) and keeps it until it leaves the set with extra>0 (the LEAVE set), so a pixel
    standing on the edge does not flicker in and out (7.4). Visibility rules (invisible pixels, spies) come in 7.5.
    """
    visible = set()
    cells = set()

    for pixel_id, x, y in own_pixels:
        visible.add(pixel_id)
        cx, cy = grid.cell_of(x, y)
        cells.update((cx + dx, cy + dy) for dx in range(-cells_around, cells_around + 1) for dy in range(-cells_around, cells_around + 1))

    visible.update(grid.in_cells(cells))

    if extra > 0:
        size = grid.cell_size

        for cx, cy in {grid.cell_of(x, y) for _, x, y in own_pixels}:
            visible.update(grid.in_rect((cx - cells_around) * size - extra, (cy - cells_around) * size - extra, (cx + cells_around + 1) * size + extra, (cy + cells_around + 1) * size + extra))

    if view is not None:
        x0, y0, x1, y1 = view
        visible.update(grid.in_rect(x0 - margin - extra, y0 - margin - extra, x1 + margin + extra, y1 + margin + extra))

    return visible