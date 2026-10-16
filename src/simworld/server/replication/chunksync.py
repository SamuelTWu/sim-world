"""Which tile changes each client has been sent (README 6.3). No networking, so it can be tested on its own.

A client is interested in the chunks within NEAR_CHUNKS of any pixel it owns. The first time a chunk becomes
interesting (on join, or when a pixel moves or is placed near it) the client gets that chunk's whole change log
(world/deltas.py). A chunk that stops being interesting is forgotten, so if it comes back the client gets the log
again, which also covers anything that changed while it was away. While a chunk stays interesting the client
gets each new change to it once (6.4): `ChunkSync.chunks` remembers, per chunk, the log sequence number the client
is up to date with, and every update sends only entries newer than that. Chunks the client cannot see are never
looked at, so a change far away costs this client nothing.

Chunk size comes from world/chunks.py, the same one the interest grid will use.
"""
from src.simworld.world.chunks import chunk_of_point, chunks_near

# Square radius, in chunks, around each pixel. 2 = a 5x5 block (80x80 tiles) centred on the pixel's chunk.
NEAR_CHUNKS = 2

# Tiles per world_delta message, to stay far below the protocol's size limit.
MAX_TILES_PER_MESSAGE = 2000


def wanted_chunks(points, tile_units, width, height, radius=NEAR_CHUNKS):
    """The set of chunks near a list of (x, y) world positions, clipped to the world."""
    wanted = set()

    for x, y in points:
        cx, cy = chunk_of_point(x, y, tile_units)
        wanted.update(chunks_near(cx, cy, radius, width, height))

    return wanted


class ChunkSync:
    """One client's record of which chunks it has been sent."""

    def __init__(self):
        # chunk -> log sequence number the client is up to date with (6.3 sets it, 6.4 advances it)
        self.chunks = {}

    def update(self, wanted, log):
        """Move to a new set of wanted chunks. Returns [(x, y, tile_name), ...] the client does not have yet:
        the whole log of newly near chunks, and anything new in chunks it already had."""
        for chunk in [chunk for chunk in self.chunks if chunk not in wanted]:
            del self.chunks[chunk]

        tiles = []

        for chunk, seen in self.chunks.items():
            if log.last(chunk) > seen:
                tiles.extend(log.entries(chunk, seen))
                self.chunks[chunk] = log.seq

        for chunk in sorted(wanted - self.chunks.keys()):
            tiles.extend(log.entries(chunk))
            self.chunks[chunk] = log.seq

        return tiles


def batches(tiles, size=MAX_TILES_PER_MESSAGE):
    """Split a list of tiles into lists of at most `size`."""
    for start in range(0, len(tiles), size):
        yield tiles[start:start + size]