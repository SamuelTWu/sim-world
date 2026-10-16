"""World change log, grouped by chunk (README 6.2, compacted in 6.6).

World.set_tile() calls DeltaLog.record() for every real tile change made after generation.
Each chunk keeps ONE entry per tile: the latest value, with the sequence number of the change
that produced it. So a tile changed a thousand times costs one entry, a chunk's log never
holds more than CHUNK_SIZE * CHUNK_SIZE entries, and a joining client is sent at most that many.

Why a client never misses anything: a client remembers the sequence number it is up to date with
(server/chunksync.py) and asks for entries newer than that. An older value that was replaced is gone, but
the entry that replaced it has a higher sequence number, so it is sent (or the client already has it).

No imports besides chunks.py, so the client can use it too.
"""
from src.simworld.world.chunks import chunk_of_tile


class DeltaLog:
    def __init__(self):
        # (cx, cy) -> {(x, y): (seq, tile_name)}. Re-recording a tile moves it to the end, so every
        # chunk's dict stays ordered oldest change first.
        self.chunks = {}
        # (cx, cy) -> seq of the newest change in that chunk
        self.newest = {}
        # Sequence number of the latest recorded change (0 = nothing recorded yet).
        self.seq = 0
        # Chunks touched since the last take_new() call, with the first new seq in each.
        self._fresh = {}

    def record(self, x, y, tile_name):
        """Set the latest value of tile (x, y) in its chunk's log, dropping any older value. Returns its seq."""
        chunk = chunk_of_tile(x, y)
        log = self.chunks.setdefault(chunk, {})
        self.seq += 1
        log.pop((x, y), None)
        log[(x, y)] = (self.seq, tile_name)
        self.newest[chunk] = self.seq
        self._fresh.setdefault(chunk, self.seq)
        return self.seq

    def entries(self, chunk, since=0):
        """[(x, y, tile_name), ...] for one chunk, oldest change first, only entries with seq > since."""
        log = self.chunks.get(chunk)
        if not log:
            return []
        return [(x, y, name) for (x, y), (seq, name) in log.items() if seq > since]

    def last(self, chunk):
        """Sequence number of the newest change in a chunk (0 if it has none)."""
        return self.newest.get(chunk, 0)

    def take_new(self):
        """{chunk: [(x, y, tile_name), ...]} of changes recorded since the last call, then forget them."""
        fresh, self._fresh = self._fresh, {}
        return {chunk: self.entries(chunk, first - 1) for chunk, first in fresh.items()}

    def size(self):
        """Number of entries held (one per changed tile)."""
        return sum(len(log) for log in self.chunks.values())

    def clear(self):
        self.chunks.clear()
        self.newest.clear()
        self._fresh.clear()
        self.seq = 0