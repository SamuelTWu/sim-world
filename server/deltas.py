"""World change log, grouped by chunk (README 6.2).

World.set_tile() calls DeltaLog.record() for every real tile change made after generation.
Each change is stored as (x, y, tile_name) in the log of the chunk that holds the tile
(chunk size: world/chunks.py), together with a global sequence number, so later steps can
ask for "everything in this chunk" (6.3, join / moving), "what is new this tick" (6.4,
broadcast) and, after compaction (6.6), a smaller equivalent log.

No imports besides chunks.py, so the client can use it too.
"""
from game.world.chunks import chunk_of_tile


class DeltaLog:
    def __init__(self):
        # (cx, cy) -> [(seq, x, y, tile_name), ...] in the order the changes happened
        self.chunks = {}
        # Sequence number of the latest recorded change (0 = nothing recorded yet).
        self.seq = 0
        # Chunks touched since the last take_new() call, with the first new seq in each.
        self._fresh = {}

    def record(self, x, y, tile_name):
        """Append (x, y, tile_name) to the log of the chunk holding tile (x, y). Returns its seq."""
        chunk = chunk_of_tile(x, y)
        self.seq += 1
        self.chunks.setdefault(chunk, []).append((self.seq, x, y, tile_name))
        self._fresh.setdefault(chunk, self.seq)
        return self.seq

    def entries(self, chunk, since=0):
        """[(x, y, tile_name), ...] for one chunk, oldest first, only changes with seq > since."""
        log = self.chunks.get(chunk)
        if not log:
            return []
        return [(x, y, name) for seq, x, y, name in log if seq > since]

    def last(self, chunk):
        """Sequence number of the newest change in a chunk (0 if it has none)."""
        log = self.chunks.get(chunk)
        return log[-1][0] if log else 0

    def take_new(self):
        """{chunk: [(x, y, tile_name), ...]} of changes recorded since the last call, then forget them."""
        fresh, self._fresh = self._fresh, {}
        return {chunk: self.entries(chunk, first - 1) for chunk, first in fresh.items()}

    def size(self):
        """Total number of logged changes."""
        return sum(len(log) for log in self.chunks.values())

    def clear(self):
        self.chunks.clear()
        self._fresh.clear()
        self.seq = 0