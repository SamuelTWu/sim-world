"""What the client knows about the game, in the form the renderer reads.

Everything here comes from the client's own generated world or from messages the server sent.
Terrain deltas from the server are applied to its world here too (apply_world_delta). The renderer is only ever given a View, never a Simulation. This file imports nothing from game/.

Smooth movement (README 8.1): the server only sends positions 20 times a second, so drawing them as they arrive would look
jerky. Each pixel remembers its last few server positions with the server time they belong to (`samples`), and every frame
`smooth()` sets `position` to where the pixel was a little while ago (INTERPOLATION_DELAY_TICKS, one tick), blended between the two
samples around that moment. `ServerClock` converts the client's clock to server time. `position` is therefore what is DRAWN (and
what clicks pick); the newest server position is `samples[-1]`.
"""
import math

from src.simworld.shared.protocol import POSITION_SCALE, from_wire
from dataclasses import dataclass, field


@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0


@dataclass
class ReplicatedEntity:
    """A pixel as the client sees it. Phase 7 fills these in from enter / update / leave messages."""

    id: int
    sprite_id: str = "pixel"
    owner: int | None = None
    name: str = ""
    position: Position = field(default_factory=Position)
    samples: list = field(default_factory=list, repr=False)   # [(server time, x, y), ...] oldest first, at most MAX_SAMPLES


# Draw pixels this many server ticks behind the newest data, so there are almost always two positions to blend between.
# 1 is enough on a good connection; raise it (2 or 3) for the internet, where updates arrive unevenly. Costs that much extra lag.
INTERPOLATION_DELAY_TICKS = 1.0

# A pixel that moved farther than this (world units) between two samples was teleported, not walking: snap instead of blending.
SNAP_DISTANCE = 256.0

MAX_SAMPLES = 4


def add_sample(entity, stamp, x, y, tick_dt):
    """Record that `entity` was at (x, y) at server time `stamp`.

    Positions are only sent when they change, so if the pixel has been still for a while, first note that it was still until
    one tick ago. Otherwise it would seem to start sliding at its old spot the moment it moved.
    """
    samples = entity.samples

    if samples and stamp <= samples[-1][0]:
        samples[-1] = (samples[-1][0], x, y)
        return

    if samples and stamp - samples[-1][0] > tick_dt * 1.5:
        samples.append((stamp - tick_dt, samples[-1][1], samples[-1][2]))

    samples.append((stamp, x, y))
    del samples[:-MAX_SAMPLES]


def smooth(entities, render_time, snap=SNAP_DISTANCE):
    """Set each pixel's `position` to where it was at server time `render_time`, blended between its two samples around it.

    Before its first sample it stays at that sample; after its newest it stays at the newest (it has stopped, or the update is late).
    Jumps larger than `snap` are not blended. Pixels with no samples (never given a stamp) keep their position.
    """
    for entity in entities:
        samples = entity.samples

        if not samples:
            continue

        if render_time <= samples[0][0]:
            _, x, y = samples[0]
        elif render_time >= samples[-1][0]:
            _, x, y = samples[-1]
        else:
            x = y = None

            for (t0, x0, y0), (t1, x1, y1) in zip(samples, samples[1:]):
                if t0 <= render_time <= t1:
                    if math.hypot(x1 - x0, y1 - y0) > snap:
                        x, y = (x1, y1) if render_time >= (t0 + t1) / 2 else (x0, y0)
                    else:
                        along = (render_time - t0) / (t1 - t0) if t1 > t0 else 1.0
                        x, y = x0 + (x1 - x0) * along, y0 + (y1 - y0) * along

                    break

        entity.position = Position(x, y)


class ServerClock:
    """Turns the client's clock into server time, so pixels can be drawn `delay_ticks` behind the newest data.

    Every tick_update says which server tick it is for. The difference between when it arrived (client clock) and that tick's server
    time is the offset; messages that arrive late make it look bigger, so the clock follows the SMALLEST recent offset (the fastest
    delivery) and only creeps toward later ones. No real time is used here: callers pass `now`, so it can be tested.
    """

    CREEP = 0.02

    def __init__(self, tick_dt, delay_ticks=INTERPOLATION_DELAY_TICKS):
        self.tick_dt = tick_dt
        self.delay = delay_ticks * tick_dt
        self.offset = None
        self.last = None

    def observe(self, server_time, now):
        """A tick_update for server time `server_time` arrived at client time `now`."""
        candidate = now - server_time

        if self.offset is None or candidate < self.offset:
            self.offset = candidate
        else:
            self.offset += (candidate - self.offset) * self.CREEP

    def render_time(self, now):
        """The server time to draw at client time `now`, or None before anything has arrived. Never goes backwards."""
        if self.offset is None:
            return None

        t = now - self.offset - self.delay
        self.last = t if self.last is None else max(self.last, t)
        return self.last


@dataclass(frozen=True)
class View:
    """A snapshot for one frame: the client's world, its map and feature data, and the entities it knows about."""

    world: object
    maps: object
    features: object
    entities: list
    player_id: int | None = None


class Stats(dict):
    """Counts of what apply_tick_update did, for tests and debugging: entered, updated, left, skipped (malformed entries), unknown (an
    update or leave for a pixel the client does not have, which means it missed an enter: the server does not repeat itself)."""

    def __init__(self):
        super().__init__(entered=0, updated=0, left=0, skipped=0, unknown=0)

    def add(self, other):
        for key, value in other.items():
            self[key] += value


def is_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def apply_tick_update(entities, message, stamp=None, tick_dt=0.05):
    """Apply a tick_update to the client's dict of known pixels (id -> ReplicatedEntity), in the order enter, update, leave.

    enter adds a pixel with its full state (or replaces one the client already had), update patches only the fields it carries,
    leave removes. Malformed entries are skipped and never half-applied. Returns a Stats with what happened.

    `stamp` is the server time of this message (tick / tick rate). When given, each position is also recorded for smoothing (see smooth()).
    """
    stats = Stats()

    for state in message.get("enter", ()):
        try:
            entity_id, x, y = state["id"], state["x"], state["y"]
            sprite_id, owner, name = state.get("sprite_id", "pixel"), state.get("owner"), state.get("name") or ""

            if not (is_id(entity_id) and is_id(x) and is_id(y) and isinstance(sprite_id, str) and (owner is None or is_id(owner)) and isinstance(name, str)):
                raise ValueError("bad enter")

            x, y = from_wire(x), from_wire(y)
            entity = ReplicatedEntity(entity_id, sprite_id, owner, name, Position(x, y))

            if stamp is not None:
                entity.samples.append((stamp, x, y))

            entities[entity_id] = entity
            stats["entered"] += 1
        except (KeyError, TypeError, ValueError, AttributeError):
            stats["skipped"] += 1

    for state in message.get("update", ()):
        try:
            entity = entities.get(state["id"])

            if entity is None:
                stats["unknown"] += 1
                continue

            # a field the update leaves out keeps its NEWEST server value (not the smoothed, drawn one)
            newest_x, newest_y = (entity.samples[-1][1], entity.samples[-1][2]) if entity.samples else (entity.position.x, entity.position.y)
            x, y = state.get("x"), state.get("y")
            sprite_id, owner, name = state.get("sprite_id", entity.sprite_id), state.get("owner", entity.owner), state.get("name", entity.name)

            if not ((x is None or is_id(x)) and (y is None or is_id(y)) and isinstance(sprite_id, str) and (owner is None or is_id(owner)) and isinstance(name, str)):
                raise ValueError("bad update")

            x = newest_x if x is None else from_wire(x)
            y = newest_y if y is None else from_wire(y)
            moved = (x, y) != (newest_x, newest_y)
            entity.sprite_id, entity.owner, entity.name = sprite_id, owner, name

            if stamp is None:
                entity.position = Position(x, y)
            elif moved:
                add_sample(entity, stamp, x, y, tick_dt)

            stats["updated"] += 1
        except (KeyError, TypeError, ValueError, AttributeError):
            stats["skipped"] += 1

    for entity_id in message.get("leave", ()):
        try:
            if entities.pop(entity_id, None) is None:
                stats["unknown"] += 1
            else:
                stats["left"] += 1
        except TypeError:
            stats["skipped"] += 1

    return stats


MAX_TRANSIENT_EVENTS = 256


def decode_transient_events(message, stamp=None):
    """The transient events in a tick_update's `events`, as [{"kind", "type", "from": (x, y), "to": (x, y), "at": server time}] in world units.

    Entries that are not what protocol.transient event() builds (wrong types, floats where ints belong) are skipped, and so are all but the
    first MAX_TRANSIENT_EVENTS. A kind the renderer does not know is kept here: it is the renderer that ignores it.
    """
    events = []

    for entry in list(message.get("events", ()))[:MAX_TRANSIENT_EVENTS]:
        try:
            kind, type_, start, end = entry["kind"], entry.get("type", ""), entry["from"], entry["to"]

            if not (isinstance(kind, str) and isinstance(type_, str) and len(start) == 2 and len(end) == 2 and all(is_id(v) for v in (*start, *end))):
                continue

            events.append({"kind": kind, "type": type_, "from": (from_wire(start[0]), from_wire(start[1])), "to": (from_wire(end[0]), from_wire(end[1])), "at": stamp})
        except (KeyError, TypeError, AttributeError):
            continue

    return events


def apply_world_delta(world, message, tiles_by_name):
    """Apply a world_delta's [x, y, tile_name] entries on top of the locally generated world, in order.

    `tiles_by_name` maps a tile name to the Tile object. Entries that are malformed, outside the world, or name a
    tile this client does not know are skipped. Returns (changed, skipped): the (x, y) of every tile that really
    changed (for the renderer to redraw), and how many entries were skipped. Applying the same entry twice is harmless.
    """
    changed, skipped = [], 0

    for entry in message.get("tiles", ()):
        try:
            x, y, name = entry
            tile = tiles_by_name.get(name)

            if tile is None or isinstance(x, bool) or isinstance(y, bool) or not world.is_inside(x, y):
                skipped += 1
            elif world.set_tile(x, y, tile):
                changed.append((x, y))
        except (TypeError, ValueError):
            skipped += 1

    return changed, skipped