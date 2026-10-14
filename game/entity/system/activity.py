"""Which pixels get the EXPENSIVE simulation every tick, and which get it less often (README 9.2).

Nothing is unloaded, frozen or hidden. Every pixel stays in the world and these things run for ALL pixels, every tick, wherever they are:
aging and statuses, running the current task (so walking, attacking, picking up and crossing chunk borders are exact), events, removal.
Only the costly parts are tiered: the needs and memory update and the decision to think (see SystemRunner.update):
  ACTIVE  within ACTIVE_CHUNKS chunks (square) of any pixel a player owns, or woken by something that just happened to it: every tick, as before
  FAR     everywhere else: once every FAR_STRIDE ticks (staggered by pixel id so the work is spread out), and the time that passed is handed
          to the needs and memory update in one go (`due_dt`), so a far pixel gets hungry as fast as a near one, just in bigger steps

What counts as "near" uses ONLY authoritative state: the positions of pixels that players own (connected or not). Not the camera, not who is
connected, so the same seed and the same commands always give the same world (the camera is only sent to clients, see replication).
A wake (`wake(ctx, entity)`, called when an attack lands) makes a far pixel ACTIVE for WAKE_TICKS, so a far pixel that gets hit reacts at once.
Anything that MOVES things on its own (a future projectile system) must not ask this module: it steps everything it owns every tick.

Until `refresh()` is first called (Simulation.step does it) everything is ACTIVE, so tools that call SystemRunner.update directly are unchanged.
With far_stride 1 or active_chunks 0 the tiers are off and every pixel is ACTIVE (the behaviour before 9.2).
"""
from ...world.chunks import chunk_of_point
from .simContext import TILE_UNITS

ACTIVE_CHUNKS = 3  # chunks (square) around every anchor chunk that count as near: 3 is 48 tiles, more than a pixel sees or reaches
FAR_STRIDE = 10  # a far pixel runs the expensive systems once in this many ticks (10 = every half second at 20 Hz)
WAKE_TICKS = 40  # how long a hit pixel stays ACTIVE (2 seconds)


class Activity:
    def __init__(self, active_chunks=ACTIVE_CHUNKS, far_stride=FAR_STRIDE, tile_units=TILE_UNITS):
        self.active_chunks = active_chunks
        self.far_stride = far_stride
        self.tile_units = tile_units
        self.enabled = False  # becomes True at the first refresh()
        self.anchor_chunks = frozenset()
        self.near = set()  # chunk coordinates that are ACTIVE
        self.awake = {}  # pixel id -> tick until which it is ACTIVE
        self.owed = {}  # far pixel id -> time that passed since its expensive systems last ran
        self.active_now = 0  # pixels that were ACTIVE in the latest tick (set by due_dt)
        self.far_now = 0
        self.last_active = 0  # the totals of the latest finished tick, for the server's log
        self.last_far = 0

    def configure(self, active_chunks=None, far_stride=None):
        if active_chunks is not None:
            self.active_chunks = max(0, int(active_chunks))
            self.anchor_chunks = frozenset()  # rebuild the near set at the next refresh

        if far_stride is not None:
            self.far_stride = max(1, int(far_stride))

    @property
    def tiers_on(self):
        return self.enabled and self.far_stride > 1 and self.active_chunks > 0

    def refresh(self, anchors):
        """Call once per tick before the pixels are updated. `anchors` are (x, y) world positions of the pixels that make their surroundings relevant."""
        self.enabled = True
        self.last_active, self.last_far = self.active_now, self.far_now
        self.active_now = self.far_now = 0
        chunks = frozenset(chunk_of_point(x, y, self.tile_units) for x, y in anchors)

        if chunks == self.anchor_chunks:
            return

        self.anchor_chunks = chunks
        radius = self.active_chunks
        self.near = {(cx + dx, cy + dy) for cx, cy in chunks for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)}

    def is_active(self, entity, tick):
        if not self.tiers_on:
            return True

        until = self.awake.get(entity.id)

        if until is not None:
            if until > tick:
                return True

            del self.awake[entity.id]

        return chunk_of_point(entity.position.x, entity.position.y, self.tile_units) in self.near

    def due_dt(self, entity, tick, delta_time):
        """The time the expensive systems should advance by for this pixel this tick, or None to skip them this tick (a far pixel between its turns).

        An ACTIVE pixel gets exactly `delta_time` (plus anything it still owed from when it was far). A far pixel collects the time and gets it all
        at once on its turn, so the total time its needs and memory see is the same as if it had run every tick.
        """
        if self.is_active(entity, tick):
            self.active_now += 1
            owed = self.owed.pop(entity.id, 0.0)
            return delta_time + owed if owed else delta_time

        self.far_now += 1
        owed = self.owed.get(entity.id, 0.0) + delta_time

        if (tick + entity.id) % self.far_stride == 0:
            self.owed.pop(entity.id, None)
            return owed

        self.owed[entity.id] = owed
        return None

    def wake(self, entity, tick, ticks=WAKE_TICKS):
        if self.tiers_on:
            self.awake[entity.id] = max(self.awake.get(entity.id, 0), tick + ticks)

    def forget(self, entity_id):
        self.awake.pop(entity_id, None)
        self.owed.pop(entity_id, None)


def wake(ctx, entity, ticks=WAKE_TICKS):
    """Make a pixel ACTIVE for a while because something just happened to it (it was attacked, touched by a projectile...). No-op without activity."""
    activity = getattr(ctx, "activity", None)

    if activity is not None and entity is not None:
        activity.wake(entity, ctx.tick, ticks)