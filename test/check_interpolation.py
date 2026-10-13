"""README 8.1: pixels are drawn one tick behind the newest data, blended between the last two positions, so movement is smooth.

Pure logic (no network, no pygame): a pretend server sends positions at 20 Hz with network jitter, a pretend 60 fps client draws.
"""
import random

from server.protocol import POSITION_SCALE as SCALE
from server.replica import INTERPOLATION_DELAY_TICKS, SNAP_DISTANCE, ReplicatedEntity, ServerClock, add_sample, apply_tick_update, smooth

TICK = 0.05
checks = 0


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def entity(x=0.0, y=0.0):
    e = ReplicatedEntity(1)
    return e


def run(positions, jitter, frames=60, seed=1, delay=INTERPOLATION_DELAY_TICKS):
    """positions: {tick: (x, y)} the server sends (only on change). Returns the drawn x at every frame, with the frame's client time."""
    rng = random.Random(seed)
    clock = ServerClock(TICK, delay)
    entities, drawn = {}, []
    arrivals = sorted((tick * TICK + 0.01 + rng.uniform(0, jitter), tick) for tick in positions)
    now, end = 0.0, max(positions) * TICK + 0.6
    i = 0

    while now < end:
        while i < len(arrivals) and arrivals[i][0] <= now:
            arrived, tick = arrivals[i]
            clock.observe(tick * TICK, arrived)
            x, y = positions[tick]
            x, y = round(x * SCALE), round(y * SCALE)     # on the wire positions are whole numbers of 1/SCALE units
            message = {"enter": [{"id": 1, "x": x, "y": y}]} if 1 not in entities else {"update": [{"id": 1, "x": x, "y": y}]}
            apply_tick_update(entities, message, tick * TICK, TICK)
            i += 1

        t = clock.render_time(now)

        if t is not None and entities:
            smooth(entities.values(), t)
            drawn.append((now, entities[1].position.x, entities[1].position.y))

        now += 1 / 60

    return drawn, entities


# ---- steady walk: 10 units a tick to the right, no jitter
walk = {tick: (tick * 10.0, 5.0) for tick in range(1, 41)}
drawn, _ = run(walk, jitter=0.0)
steps = [b[1] - a[1] for a, b in zip(drawn, drawn[1:])]
ok(all(step >= -1e-9 for step in steps), "the drawn position never goes backwards")
ok(max(steps) < 10 * (1 / 60) / TICK * 1.5, "no frame moves more than 1.5x the walking speed per frame (10 units per 0.05 s = 3.3 per frame)")
settled = [s for (t, _, _), s in zip(drawn[1:], steps) if 0.3 < t < 1.8]
ok(len(settled) > 60 and max(settled) - min(settled) < 0.01, "in the middle of the walk every frame moves by the same amount (no stutter)")
ok(all(y == 5.0 for _, _, y in drawn), "y is untouched")

# drawn one tick behind: with data arriving 10 ms after it is made, at client time t the pixel is drawn where the server had it at t - 0.01 - 1 tick
errors = []
for t, x, _ in drawn:
    if 0.5 < t < 1.8:
        errors.append(abs(x - 10.0 * (t - 0.01 - TICK * INTERPOLATION_DELAY_TICKS) / TICK))

ok(max(errors) < 0.5, f"the pixel is drawn exactly one tick behind the data (worst error {max(errors):.3f} units)")

# ---- jitter: updates arrive up to 30 ms late and bunched; the drawing stays smooth and never goes backwards
drawn, _ = run(walk, jitter=0.03, seed=3)
steps = [b[1] - a[1] for a, b in zip(drawn, drawn[1:])]
ok(all(step >= -1e-9 for step in steps), "with jitter: still never backwards")
ok(max(steps) < 10 / TICK / 60 * 4, "with jitter: no frame jumps more than 4 frames' worth")
raw_jump = 10.0
ok(max(steps) < raw_jump, "and far smoother than drawing the raw positions (which jump a whole tick = 10 units)")

# ---- stop: holds the last position
stop = {tick: (tick * 10.0, 0.0) for tick in range(1, 11)}
stop[60] = (100.0, 0.0)
drawn, _ = run(stop, jitter=0.0)
at_rest = [x for t, x, _ in drawn if 0.8 < t < 2.5]
ok(max(at_rest) - min(at_rest) < 1e-9 and abs(at_rest[0] - 100.0) < 1e-9, "a pixel that stops is drawn still at its last position")

# ---- still for a long time, then moves: it does NOT slide from its old spot over the whole gap
gap = {1: (0.0, 0.0), 2: (10.0, 0.0), 100: (20.0, 0.0), 101: (30.0, 0.0)}
drawn, _ = run(gap, jitter=0.0)
during = [x for t, x, _ in drawn if 0.3 < t < 4.5]          # the long still period (server time 0.1..4.9)
ok(max(during) <= 10.0 + 1e-6, "after a long still period the pixel stayed at its spot until the tick it moved")

# ---- teleport: a jump bigger than SNAP_DISTANCE is not blended
jump = {1: (0.0, 0.0), 2: (5.0, 0.0), 3: (5.0 + SNAP_DISTANCE * 3, 0.0), 4: (5.0 + SNAP_DISTANCE * 3 + 5, 0.0)}
drawn, _ = run(jump, jitter=0.0)
xs = [x for _, x, _ in drawn]
ok(not any(10.0 < x < SNAP_DISTANCE * 3 - 10 for x in xs), "a teleport is snapped, never drawn sliding across the map")

# ---- entering: a new pixel appears where it is, with no slide in from the origin
drawn, _ = run({10: (500.0, 300.0), 11: (505.0, 300.0)}, jitter=0.0)
ok(all(x >= 500.0 for _, x, _ in drawn) and drawn[0][1] == 500.0, "a pixel that enters is drawn at its position from its first frame")

# ---- the clock
c = ServerClock(TICK)
ok(c.render_time(1.0) is None, "no render time before anything arrived")
c.observe(1.0, 5.0)
t0 = c.render_time(5.0)
ok(abs(t0 - (1.0 - TICK * INTERPOLATION_DELAY_TICKS)) < 1e-9, "render time = newest server time minus the delay")
c.observe(2.0, 7.5)     # arrived 0.5 s late
ok(abs(c.offset - 4.0) < 0.05, "a late message barely moves the clock (it follows the fastest delivery)")
c.observe(3.0, 7.0)     # fastest delivery so far
ok(abs(c.offset - 4.0) < 1e-9, "a faster delivery pulls it down at once")
last = c.render_time(8.0)
ok(c.render_time(7.0) >= last, "render time never goes backwards")

# ---- samples and apply: no stamp = old behaviour; stamped = recorded and trimmed
e = {}
apply_tick_update(e, {"enter": [{"id": 1, "x": 1 * SCALE, "y": 2 * SCALE}]})
ok(e[1].samples == [] and (e[1].position.x, e[1].position.y) == (1.0, 2.0), "without a stamp nothing is recorded and position is the newest (as before)")
smooth(e.values(), 99.0)
ok((e[1].position.x, e[1].position.y) == (1.0, 2.0), "smooth leaves a pixel with no samples alone")
q = ReplicatedEntity(2)
for k in range(10):
    add_sample(q, k * TICK, float(k), 0.0, TICK)

ok(len(q.samples) <= 4 and q.samples[-1] == (9 * TICK, 9.0, 0.0), "only the last few samples are kept")
add_sample(q, 9 * TICK, 99.0, 0.0, TICK)
ok(q.samples[-1][1] == 99.0 and len(q.samples) <= 4, "a second update for the same tick replaces the sample")

# ---- an update that carries only x keeps the NEWEST y, not the smoothed, drawn one (8.2 sends only changed fields)
m = {}
apply_tick_update(m, {"enter": [{"id": 1, "x": 0, "y": 400}]}, 0.0, TICK)
apply_tick_update(m, {"update": [{"id": 1, "y": 800}]}, TICK, TICK)
smooth(m.values(), 0.0)                       # drawn at the old spot: y = 100
ok(m[1].position.y == 100.0, "drawn at the older sample")
apply_tick_update(m, {"update": [{"id": 1, "x": 40}]}, 2 * TICK, TICK)
ok(m[1].samples[-1] == (2 * TICK, 10.0, 200.0), "an x-only update keeps the newest y (200), not the drawn one")

print(f"all {checks} checks passed")