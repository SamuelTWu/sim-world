"""Who is near a point, without looking at every pixel (README 9.7, found by profile_sim.py: attack_generator compared every pixel with every other).

    context.proximity.near(x, y, radius, tick)    # the living pixels that may be within `radius` of (x, y): a short list, not the world

The answer is a SHORT-LIST: every pixel within `radius` is in it, plus some that are a little farther (whole cells, and the margin below), so the
caller still does its own exact test (distance, hostile, can_see) on the few it gets. Nothing about what the caller decides changes, only how
many pixels it has to look at, so the same seed and commands give the same world as the scan of everything.

How it stays cheap and correct:
  - it is built lazily, at most once per tick: the first `near` of a tick buckets every living pixel by its cell (one pass over the pixels), and
    ticks where nobody asks cost nothing. `invalidate()` forces a rebuild at the next `near` (Simulation.spawn_pixel calls it, and so can anything
    that teleports pixels outside a tick);
  - pixels keep moving during a tick (they take their steps one after another), so a bucket can be a step out of date: the query adds
    DRIFT_UNITS to the radius. A pixel never moves more than a few units in a tick (speed times 0.05 s); DRIFT_UNITS is far more than that. A pixel
    that is moved a long way mid-tick (a teleport) is found again from the next tick;
  - a pixel spawned during the tick is not in the buckets until the next tick (spawn_pixel invalidates, so it is in them from the next query).
Anything that must see EVERY pixel (removal, replication, the checks) uses the entity manager, not this.
"""
import math

CELL_UNITS = 128.0  # 4 tiles: a pixel's sight (160) spans about 3 cells across
DRIFT_UNITS = 64.0  # how far a pixel may have moved since the buckets were built and still be found (2 tiles; real steps are a few units)


class ProximityIndex:
    def __init__(self, entities, cell_units=CELL_UNITS, drift_units=DRIFT_UNITS):
        self.entities = entities
        self.cell_units = float(cell_units)
        self.drift_units = float(drift_units)
        self.cells = {}  # (cx, cy) -> [pixels that were there when the buckets were built]
        self.built_tick = None
        self.rebuilds = 0

    def invalidate(self):
        self.built_tick = None

    def rebuild(self, tick):
        cell = self.cell_units
        cells = {}

        for entity in self.entities.all():
            if entity.alive:
                key = (math.floor(entity.position.x / cell), math.floor(entity.position.y / cell))
                bucket = cells.get(key)

                if bucket is None:
                    cells[key] = [entity]
                else:
                    bucket.append(entity)

        self.cells = cells
        self.built_tick = tick
        self.rebuilds += 1

    def near(self, x, y, radius, tick):
        """The living pixels that may be within `radius` of (x, y) (at least all of those that are), as a list. Order is not meaningful."""
        if self.built_tick != tick:
            self.rebuild(tick)

        reach = radius + self.drift_units
        cell = self.cell_units
        cx0, cx1 = math.floor((x - reach) / cell), math.floor((x + reach) / cell)
        cy0, cy1 = math.floor((y - reach) / cell), math.floor((y + reach) / cell)
        found = []
        cells = self.cells

        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                bucket = cells.get((cx, cy))

                if bucket:
                    found.extend(bucket)

        return found