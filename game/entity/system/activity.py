"""Which pixels get the EXPENSIVE simulation every tick, and which get it less often (README 9.2), and which are asleep (README 9.3).

Nothing is unloaded, frozen or hidden. Every pixel stays in the world and these things run for ALL pixels, every tick, wherever they are:
aging and statuses, running the current task (so walking, attacking, picking up and crossing chunk borders are exact), events, removal.
Only the costly parts are tiered: the needs and memory update and the decision to think (see SystemRunner.update):
  ACTIVE  within ACTIVE_CHUNKS chunks (square) of any pixel a player owns, or woken by something that just happened to it: every tick, as before
  FAR     everywhere else: once every FAR_STRIDE ticks (staggered by pixel id so the work is spread out), and the time that passed is handed
          to the needs and memory update in one go (`due_dt`), so a far pixel gets hungry as fast as a near one, just in bigger steps

What counts as "near" uses ONLY authoritative state: the positions of pixels that players own (connected or not). Not the camera, not who is
connected, so the same seed and the same commands always give the same world (the camera is only sent to clients, see replication).
A wake (`wake(ctx, entity)`, called when an attack lands) makes a far pixel ACTIVE for WAKE_TICKS, so a far pixel that gets hit reacts at once.
SLEEP (9.3, independent of the tiers): a pixel that thinks `IDLE_THINKS` times in a row and finds nothing to do (no task, no order) falls asleep.
A sleeping pixel does no thinking and its needs and memory are only updated when it wakes (with all the time that passed, like a far pixel);
it still ages, keeps every bit of its state, and stays in the world. It wakes (and has to find something to do again) when:
  - a command was applied to it (`command.execute` wakes the pixels a command applied to: orders, edits, ...),
  - it is attacked or otherwise `wake()`d,
  - something changes nearby: a pixel appears or enters a neighbouring cell (`moved`, cells of WAKE_CELL_TILES tiles, the 3x3 cells around it),
    or a tile changes there (`tile_changed`, called by World.set_tile),
  - its scheduled time comes (`SLEEP_TICKS`, staggered by id): it looks around again, so a need that has become urgent or a change nothing above
    reported is noticed within about two seconds. `schedule_wake(id, tick)` pulls that time forward for anything that must happen at a known time.
Cheap bookkeeping: sleepers are indexed by cell, and only pixels that have a task (and new pixels) are checked for changing cell.

Anything that MOVES things on its own (a future projectile system) must not ask this module: it steps everything it owns every tick.

Until `refresh()` is first called (Simulation.step does it) everything is ACTIVE, so tools that call SystemRunner.update directly are unchanged.
With far_stride 1 or active_chunks 0 the tiers are off and every pixel is ACTIVE (the behaviour before 9.2).
"""
from ...world.chunks import chunk_of_point
from .simContext import TILE_UNITS

ACTIVE_CHUNKS = 3  # chunks (square) around every anchor chunk that count as near: 3 is 48 tiles, more than a pixel sees or reaches
FAR_STRIDE = 10  # a far pixel runs the expensive systems once in this many ticks (10 = every half second at 20 Hz)
WAKE_TICKS = 40  # how long a hit pixel stays ACTIVE (2 seconds)
IDLE_THINKS = 3  # consecutive thinks that find nothing to do before a pixel falls asleep
SLEEP_TICKS = 40  # a sleeping pixel wakes by itself after this many ticks (2 seconds) to look around again; 0 turns sleeping off
SLEEP_SPREAD = 10  # plus up to this many ticks, by pixel id, so sleepers do not all wake on the same tick
WAKE_CELL_TILES = 4  # a change wakes the sleepers in its cell and the 8 around it (cells are this many tiles wide)


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
        self.sleep_ticks = SLEEP_TICKS
        self.idle_thinks = IDLE_THINKS
        self.sleeping = {}  # pixel id -> tick it wakes by itself
        self.idle = {}  # pixel id -> consecutive thinks that found nothing to do
        self.cell_of = {}  # pixel id -> the wake cell it was last seen in
        self.sleepers = {}  # wake cell -> ids of the pixels asleep in it
        self.sleep_cell = {}  # sleeping pixel id -> its cell
        self.asleep_now = 0
        self.last_asleep = 0
        self.counters = None  # Counters (counters.py), set by SystemRunner: "sleeps" and "wakes" are counted

    def configure(self, active_chunks=None, far_stride=None, sleep_ticks=None, idle_thinks=None):
        if active_chunks is not None:
            self.active_chunks = max(0, int(active_chunks))
            self.anchor_chunks = frozenset()  # rebuild the near set at the next refresh

        if far_stride is not None:
            self.far_stride = max(1, int(far_stride))

        if idle_thinks is not None:
            self.idle_thinks = max(1, int(idle_thinks))

        if sleep_ticks is not None:
            self.sleep_ticks = max(0, int(sleep_ticks))

            if self.sleep_ticks == 0:
                for pixel_id in list(self.sleeping):
                    self.remove_sleeper(pixel_id)

                self.idle.clear()

    @property
    def tiers_on(self):
        return self.enabled and self.far_stride > 1 and self.active_chunks > 0

    def refresh(self, anchors):
        """Call once per tick before the pixels are updated. `anchors` are (x, y) world positions of the pixels that make their surroundings relevant."""
        self.enabled = True
        self.last_active, self.last_far, self.last_asleep = self.active_now, self.far_now, self.asleep_now
        self.active_now = self.far_now = self.asleep_now = 0
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
        until = self.sleeping.get(entity.id)

        if until is not None:
            if tick < until:
                self.asleep_now += 1
                self.owed[entity.id] = self.owed.get(entity.id, 0.0) + delta_time
                return None

            self.remove_sleeper(entity.id)  # its scheduled time: it wakes by itself and looks around
            self.count("wakes")
            self.idle[entity.id] = self.idle_thinks - 1  # one more think that finds nothing and it goes back to sleep
            return self.owed.pop(entity.id, 0.0) + delta_time

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
        """Something happened to this pixel: wake it if it sleeps, and keep it ACTIVE for `ticks` even if it is far."""
        self.wake_sleeper(entity.id)
        self.idle.pop(entity.id, None)

        if self.tiers_on:
            self.awake[entity.id] = max(self.awake.get(entity.id, 0), tick + ticks)

    def forget(self, entity_id):
        self.awake.pop(entity_id, None)
        self.owed.pop(entity_id, None)
        self.idle.pop(entity_id, None)
        self.cell_of.pop(entity_id, None)

        if entity_id in self.sleeping:
            self.remove_sleeper(entity_id)

    # ---- sleeping (9.3)

    def count(self, name):
        if self.counters is not None:
            self.counters.add(name)

    def wake_cell(self, entity):
        return int(entity.position.x // self.tile_units) // WAKE_CELL_TILES, int(entity.position.y // self.tile_units) // WAKE_CELL_TILES

    def idle_think(self, entity, tick):
        """The pixel just thought and found nothing to do. After IDLE_THINKS of those in a row it falls asleep."""
        if self.sleep_ticks <= 0:
            return

        streak = self.idle.get(entity.id, 0) + 1

        if streak < self.idle_thinks:
            self.idle[entity.id] = streak
            return

        self.idle.pop(entity.id, None)
        cell = self.wake_cell(entity)
        self.sleeping[entity.id] = tick + self.sleep_ticks + entity.id % SLEEP_SPREAD
        self.sleep_cell[entity.id] = cell
        self.sleepers.setdefault(cell, set()).add(entity.id)
        self.count("sleeps")

    def busy_think(self, entity):
        if entity.id in self.idle:
            del self.idle[entity.id]

    def remove_sleeper(self, pixel_id):
        self.sleeping.pop(pixel_id, None)
        cell = self.sleep_cell.pop(pixel_id, None)
        members = self.sleepers.get(cell)

        if members is not None:
            members.discard(pixel_id)

            if not members:
                del self.sleepers[cell]

    def wake_sleeper(self, pixel_id):
        if pixel_id in self.sleeping:
            self.remove_sleeper(pixel_id)
            self.count("wakes")

    def schedule_wake(self, pixel_id, tick):
        """A sleeping pixel must wake no later than `tick` (never later than it would have anyway)."""
        if pixel_id in self.sleeping:
            self.sleeping[pixel_id] = min(self.sleeping[pixel_id], tick)

    def wake_near(self, cell):
        """Wake every sleeper in this wake cell and the 8 around it."""
        if not self.sleepers:
            return

        cx, cy = cell

        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                members = self.sleepers.get((cx + dx, cy + dy))

                if members:
                    for pixel_id in list(members):
                        self.wake_sleeper(pixel_id)

    def moved(self, entity):
        """Call for a pixel that has a task (it may move) and for every new pixel: if it is in a new wake cell, sleepers around it wake."""
        cell = self.wake_cell(entity)

        if self.cell_of.get(entity.id) != cell:
            self.cell_of[entity.id] = cell
            self.wake_near(cell)

    def tile_changed(self, tile_x, tile_y):
        """A tile changed (World.set_tile calls this): sleepers around it wake."""
        self.wake_near((tile_x // WAKE_CELL_TILES, tile_y // WAKE_CELL_TILES))


def wake(ctx, entity, ticks=WAKE_TICKS):
    """Make a pixel ACTIVE for a while because something just happened to it (it was attacked, touched by a projectile...). No-op without activity."""
    activity = getattr(ctx, "activity", None)

    if activity is not None and entity is not None:
        activity.wake(entity, ctx.tick, ticks)