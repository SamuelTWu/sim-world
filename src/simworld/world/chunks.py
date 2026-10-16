"""The one chunk size for the whole project.

Phase 6 (tile deltas) and Phase 7 (the interest grid) BOTH import from here, so a
chunk means the same square everywhere. Change CHUNK_SIZE here and nowhere else.

A chunk is CHUNK_SIZE x CHUNK_SIZE tiles. Chunk (cx, cy) covers tiles
[cx*CHUNK_SIZE, (cx+1)*CHUNK_SIZE) in x and likewise in y. Edge chunks of a world whose
size is not a multiple of CHUNK_SIZE are simply smaller. This module has no imports so
the server, the client and tests can all use it.

Why 16: a 500x500 world is 32x32 = 1024 chunks. At TILE_UNITS 32 a chunk is 512 world
units, about one screen, so "the chunks around a player" is a 3x3 block (9 chunks, 2304
tiles) rather than the whole map. Smaller chunks mean more bookkeeping; larger ones send
tiles nobody can see.
"""

CHUNK_SIZE = 16


def chunk_of_tile(x, y):
    """Chunk coordinates (cx, cy) holding tile (x, y). Works for negative tiles too."""
    return int(x) // CHUNK_SIZE, int(y) // CHUNK_SIZE


def chunk_of_point(x, y, tile_units):
    """Chunk coordinates for a position in world units (tile_units = world units per tile)."""
    return int(x // tile_units) // CHUNK_SIZE, int(y // tile_units) // CHUNK_SIZE


def chunk_bounds(cx, cy, width=None, height=None):
    """(x0, y0, x1, y1) tile bounds of a chunk, x1/y1 exclusive, clipped to a world if given."""
    x0, y0 = cx * CHUNK_SIZE, cy * CHUNK_SIZE
    x1, y1 = x0 + CHUNK_SIZE, y0 + CHUNK_SIZE
    if width is not None:
        x1 = min(x1, width)
    if height is not None:
        y1 = min(y1, height)
    return x0, y0, x1, y1


def chunk_grid_size(width, height):
    """How many chunks span a world: (columns, rows), rounding up."""
    return -(-width // CHUNK_SIZE), -(-height // CHUNK_SIZE)


def chunks_near(cx, cy, radius, width=None, height=None):
    """Chunk coordinates within `radius` chunks of (cx, cy), square, clipped to the world."""
    cols = rows = None
    if width is not None:
        cols, rows = chunk_grid_size(width, height)
    out = []
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if x < 0 or y < 0:
                continue
            if cols is not None and (x >= cols or y >= rows):
                continue
            out.append((x, y))
    return out