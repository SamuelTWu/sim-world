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

RATES (9.4): the near/far/sleep rules above are applied PER SYSTEM KEY, and which keys are "noncritical" is a table you edit (`RATES`, or
`activity.set_rate(...)`, or `--rate` on the server, or a pixel's own `"rates"` trait). This module does not decide what is critical:
  - a key that is not in the table is critical: it runs every tick for every pixel (stride 1), whatever the tier, and never sleeps;
  - a key in the table has `near` (stride for ACTIVE pixels), `far` (stride for FAR pixels; None = FAR_STRIDE) and `sleeps` (skipped while the pixel
    sleeps); a stride of N means once in N ticks, staggered by pixel id, handed all the time that passed (so the total time is never lost);
  - no stride can exceed MAX_STRIDE (1 second), so nothing can be starved;
  - a pixel can override any key for itself: blueprint "traits": {"rates": {"needs": {"far": 1}, "think": {"near": 1, "far": 4, "sleeps": false}}}.
Keys used by SystemRunner.update today: per pixel "needs", "memory", "think"; whole-world "relationships", "territory", "stimuli" (`global_due`).
Any system you add can use its own key: `state = activity.state(entity, tick)` once per pixel per tick, then `activity.due("mykey", entity, state, dt, tick)`.
What is NOT tiered, ever: aging and statuses, running a pixel's task (walking, attacking and the terrain/collision tests inside it), events, removal,
orders, projectiles. Those stay exact every tick.

Anything that MOVES things on its own (a future projectile system) must not ask this module: it steps everything it owns every tick.

Until `refresh()` is first called (Simulation.step does it) everything is ACTIVE, so tools that call SystemRunner.update directly are unchanged.
With far_stride 1 or active_chunks 0 the tiers are off and every pixel is ACTIVE (the behaviour before 9.2).
"""
from ...world.chunks import chunk_of_point
from .sim_context import TILE_UNITS

ACTIVE_CHUNKS = 3  # chunks (square) around every anchor chunk that count as near: 3 is 48 tiles, more than a pixel sees or reaches
FAR_STRIDE = 10  # a far pixel runs the expensive systems once in this many ticks (10 = every half second at 20 Hz)
WAKE_TICKS = 40  # how long a hit pixel stays ACTIVE (2 seconds)
IDLE_THINKS = 3  # consecutive thinks that find nothing to do before a pixel falls asleep
SLEEP_TICKS = 40  # a sleeping pixel wakes by itself after this many ticks (2 seconds) to look around again; 0 turns sleeping off
SLEEP_SPREAD = 10  # plus up to this many ticks, by pixel id, so sleepers do not all wake on the same tick
WAKE_CELL_TILES = 4  # a change wakes the sleepers in its cell and the 8 around it (cells are this many tiles wide)
MAX_STRIDE = 20  # no system may go longer than this many ticks (1 second) between runs, whatever the table or a pixel says

# Which systems may run less often, and how. EDIT THIS TABLE to decide what is noncritical; a key that is not here runs every tick.
#   key: (near stride, far stride or None for FAR_STRIDE, sleeps)
RATES = {
    "needs": (1, None, True),
    "memory": (1, None, True),
    "think": (1, None, True),
}


class Rate:
    __slots__ = ("near", "far", "sleeps")

    def __init__(self, near=1, far=None, sleeps=True):
        self.near = max(1, min(MAX_STRIDE, int(near)))
        self.far = None if far is None else max(1, min(MAX_STRIDE, int(far)))
        self.sleeps = bool(sleeps)


CRITICAL = Rate(1, 1, False)

# what state() returns
ACTIVE, FAR, ASLEEP, WAKING, FROZEN = 0, 1, 2, 3, 4


class Activity:
    def __init__(self, active_chunks=ACTIVE_CHUNKS, far_stride=FAR_STRIDE, tile_units=TILE_UNITS):
        self.active_chunks = active_chunks
        self.far_stride = far_stride
        self.tile_units = tile_units
        self.enabled = False  # becomes True at the first refresh()
        self.anchor_chunks = frozenset()
        self.near = set()  # chunk coordinates that are ACTIVE
        self.awake = {}  # pixel id -> tick until which it is ACTIVE
        self.rates = {key: Rate(*spec) for key, spec in RATES.items()}
        self.owed = {}  # system key -> {pixel id: time that passed since that system last ran for the pixel}
        self.global_owed = {}  # whole-world system key -> time that passed since it last ran
        self.ran = {}  # system key -> how many pixel runs this tick / skipped (flushed to the counters by refresh)
        self.skipped = {}
        self.active_now = 0  # pixels that were ACTIVE in the latest tick (set by due_dt)
        self.far_now = 0
        self.last_active = 0  # the totals of the latest finished tick, for the server's log
        self.last_far = 0
        self.sleep_ticks = SLEEP_TICKS
        self.idle_thinks = IDLE_THINKS
        self.sleeping = {}  # pixel id -> tick it wakes by itself
        self.frozen = set()
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
        self.flush_counts()
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

    def state(self, entity, tick):
        """Where this pixel stands this tick: ACTIVE, FAR, ASLEEP or WAKING (its scheduled wake time has just come). Call once per pixel per tick."""
        if entity.id in self.frozen:
            return FROZEN
        until = self.sleeping.get(entity.id)

        if until is not None:
            if tick < until:
                self.asleep_now += 1
                return ASLEEP

            self.remove_sleeper(entity.id)  # its scheduled time: it wakes by itself and looks around
            self.count("wakes")
            self.idle[entity.id] = self.idle_thinks - 1  # one more think that finds nothing and it goes back to sleep
            self.active_now += 1
            return WAKING

        if self.is_active(entity, tick):
            self.active_now += 1
            return ACTIVE

        self.far_now += 1
        return FAR

    def rate_of(self, key, entity=None):
        """The Rate for a system key (CRITICAL if it is not in the table), with the pixel's own "rates" trait applied."""
        rate = self.rates.get(key, CRITICAL)
        traits = getattr(entity, "traits", None)
        mine = traits.get("rates") if traits else None
        override = mine.get(key) if isinstance(mine, dict) else None

        if isinstance(override, dict):
            return Rate(override.get("near", rate.near), override.get("far", rate.far), override.get("sleeps", rate.sleeps))

        return rate

    def due(self, key, entity, state, delta_time, tick):
        """The time system `key` should advance by for this pixel this tick, or None to skip it this tick.

        Stride 1 (the default for any key that is not in RATES) always returns `delta_time` (plus any time still owed). A larger stride collects
        the time and hands it all over on the pixel's turn (once in `stride` ticks, staggered by id), so the total time is never lost.
        A sleeping pixel is skipped by every key that `sleeps`; a pixel that just woke is handed everything at once.
        """
        if state == FROZEN:
            self.skipped[key] = self.skipped.get(key, 0) + 1
            return None
        if not self.enabled:
            return delta_time

        rate = self.rate_of(key, entity)
        bucket = self.owed.get(key)

        if bucket is None:
            bucket = self.owed[key] = {}

        if state == WAKING:
            owed = bucket.pop(entity.id, 0.0)
            self.ran[key] = self.ran.get(key, 0) + 1
            return delta_time + owed if owed else delta_time

        if state == ASLEEP:
            if rate.sleeps:
                bucket[entity.id] = bucket.get(entity.id, 0.0) + delta_time
                self.skipped[key] = self.skipped.get(key, 0) + 1
                return None

            far = not self.is_active(entity, tick)  # a system that does not sleep keeps its normal rate
        else:
            far = state == FAR

        stride = (rate.far if rate.far is not None else self.far_stride) if far else rate.near
        stride = max(1, min(MAX_STRIDE, stride))

        if stride == 1 or (tick + entity.id) % stride == 0:
            owed = bucket.pop(entity.id, 0.0) if bucket else 0.0
            self.ran[key] = self.ran.get(key, 0) + 1
            return delta_time + owed if owed else delta_time

        bucket[entity.id] = bucket.get(entity.id, 0.0) + delta_time
        self.skipped[key] = self.skipped.get(key, 0) + 1
        return None

    def due_dt(self, entity, tick, delta_time):
        """state() and due() in one call, for the "think" key (what 9.2 and 9.3 were written against)."""
        return self.due("think", entity, self.state(entity, tick), delta_time, tick)

    def global_due(self, key, tick, delta_time):
        """For a system that works on the whole world (relationships, territory, stimuli): the time to advance it by, or None to skip this tick.

        Only `near` counts (a whole-world system has no far); a key that is not in RATES runs every tick.
        """
        rate = self.rates.get(key)

        if rate is None or rate.near <= 1 or not self.enabled:
            return delta_time

        owed = self.global_owed.get(key, 0.0) + delta_time

        if tick % rate.near == 0:
            self.global_owed.pop(key, None)
            return owed

        self.global_owed[key] = owed
        return None

    def set_rate(self, key, near=None, far=None, sleeps=None):
        """Decide how a system runs (see the table RATES). Leave an argument None to keep the current value; a new key starts from near 1, far FAR_STRIDE, sleeps."""
        current = self.rates.get(key) or Rate()
        self.rates[key] = Rate(current.near if near is None else near, current.far if far is None else far, current.sleeps if sleeps is None else sleeps)

    def defer(self, key, entity, step):
        if self.enabled:
            bucket = self.owed.setdefault(key, {})
            bucket[entity.id] = bucket.get(entity.id, 0.0) + step

    def critical(self, key):
        """Make a system run every tick for every pixel again."""
        self.rates.pop(key, None)

    def owed_for(self, pixel_id):
        """The time still owed to a pixel by all systems together (0.0 when nothing is held back)."""
        return sum(bucket.get(pixel_id, 0.0) for bucket in self.owed.values())

    def flush_counts(self):
        counters = self.counters

        if counters is not None:
            for key, amount in self.ran.items():
                counters.add(f"{key}_runs", amount)

            for key, amount in self.skipped.items():
                counters.add(f"{key}_skips", amount)

        self.ran.clear()
        self.skipped.clear()

    def wake(self, entity, tick, ticks=WAKE_TICKS):
        """Something happened to this pixel: wake it if it sleeps, and keep it ACTIVE for `ticks` even if it is far."""
        self.wake_sleeper(entity.id)
        self.idle.pop(entity.id, None)

        if self.tiers_on:
            self.awake[entity.id] = max(self.awake.get(entity.id, 0), tick + ticks)

    def freeze(self, entity_id):
        self.frozen.add(entity_id)
        self.wake_sleeper(entity_id)
        self.idle.pop(entity_id, None)
        self.awake.pop(entity_id, None)

        for bucket in self.owed.values():
            bucket.pop(entity_id, None)

    def unfreeze(self, entity_id):
        if entity_id not in self.frozen:
            return False

        self.frozen.discard(entity_id)
        self.idle.pop(entity_id, None)
        self.cell_of.pop(entity_id, None)
        self.count("unfreezes")
        return True

    def is_frozen(self, entity_id):
        return entity_id in self.frozen

    def forget(self, entity_id):
        self.frozen.discard(entity_id)
        self.awake.pop(entity_id, None)

        for bucket in self.owed.values():
            bucket.pop(entity_id, None)

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