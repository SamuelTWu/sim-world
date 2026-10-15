"""README 9.3: idle pixels sleep and wake on commands, nearby changes, attacks and their scheduled time.

Part 1 checks entity/system/activity.py alone (falling asleep, the owed time, every kind of wake, the cell index, the switches).
Part 2 runs the real Simulation: an idle pixel sleeps and thinks far less often but keeps ageing and getting its needs' time; a command, a
changing tile, a pixel appearing next to it and its own schedule wake it; nothing is removed or frozen; and the same seed gives the same
world. In part 2 every pixel is made to find nothing to do (get_available_actions returns nothing), so the check does not depend on what
your blueprints decide. Run from the folder that contains game/ and server/.
"""
import random
import types

from game.command import command as commands
from game.entity.system.activity import IDLE_THINKS, SLEEP_SPREAD, SLEEP_TICKS, WAKE_CELL_TILES, Activity, wake
from game.entity.system.counters import Counters
from game.entity.system.simContext import TILE_UNITS
from game.simulation import TICK_DT, Simulation
from game.world.generator import GenerationSettings

checks = 0
CELL = WAKE_CELL_TILES * TILE_UNITS


def ok(condition, label):
    global checks
    assert condition, label
    checks += 1


def near(a, b, tolerance=1e-6):
    return abs(a - b) <= tolerance


def pixel(pixel_id, x, y):
    return types.SimpleNamespace(id=pixel_id, position=types.SimpleNamespace(x=x, y=y))


def tile_xy(tile_x, tile_y):
    return tile_x * TILE_UNITS + 16, tile_y * TILE_UNITS + 16


# ---- part 1: Activity on its own
a = Activity(far_stride=1)          # tiers off: sleeping does not need them
a.counters = Counters()
a.refresh([])
p = pixel(1, *tile_xy(40, 40))

for think in range(IDLE_THINKS - 1):
    a.idle_think(p, think)

ok(p.id not in a.sleeping, f"a pixel that has found nothing to do {IDLE_THINKS - 1} times in a row is still awake")
a.busy_think(p)
a.idle_think(p, 5)
ok(p.id not in a.sleeping and a.idle.get(p.id) == 1, "finding something to do starts the count again")
a.idle_think(p, 6)
a.idle_think(p, 7)
ok(p.id in a.sleeping, f"{IDLE_THINKS} idle thinks in a row: asleep")
ok(a.sleeping[p.id] == 7 + SLEEP_TICKS + p.id % SLEEP_SPREAD, "it is due to wake SLEEP_TICKS later, staggered by id")
ok(a.sleep_cell[p.id] == (40 // WAKE_CELL_TILES, 40 // WAKE_CELL_TILES) and p.id in a.sleepers[a.sleep_cell[p.id]], "sleepers are indexed by cell")
ok(a.counters.values.get("sleeps") == 1, "a sleep is counted")

# asleep: nothing is due, time is owed, the wake hands it over
wake_at = a.sleeping[p.id]
got = [a.due_dt(p, tick, TICK_DT) for tick in range(8, wake_at)]
ok(all(step is None for step in got) and a.asleep_now == len(got), "while asleep the expensive systems are skipped")
step = a.due_dt(p, wake_at, TICK_DT)
ok(near(step, (wake_at - 8 + 1) * TICK_DT, 1e-9) and p.id not in a.sleeping and p.id not in a.sleepers and a.owed_for(p.id) == 0.0, "at its scheduled time it wakes and is handed all the time that passed")
ok(a.counters.values.get("wakes") == 1, "a wake is counted")
ok(a.idle[p.id] == IDLE_THINKS - 1, "after its scheduled wake one more think that finds nothing sends it back to sleep")
ok(a.due_dt(p, wake_at + 1, TICK_DT) == TICK_DT, "and until then it is an ordinary pixel")


def asleep(pixel_id, x, y, tick=0):
    sleeper = pixel(pixel_id, x, y)

    for _ in range(IDLE_THINKS):
        a.idle_think(sleeper, tick)

    return sleeper


a = Activity(far_stride=1)
a.refresh([])
s1 = asleep(1, *tile_xy(40, 40))
s2 = asleep(2, *tile_xy(40, 40 + WAKE_CELL_TILES))        # the cell below s1's
s3 = asleep(3, *tile_xy(40, 40 + 3 * WAKE_CELL_TILES))    # three cells away
ok(set(a.sleeping) == {1, 2, 3}, "three sleepers")

# commands and attacks: wake()
ctx = types.SimpleNamespace(activity=a, tick=10)
wake(ctx, s3)
ok(3 not in a.sleeping and 3 not in a.sleepers, "wake() wakes a sleeper")
wake(ctx, s3)       # waking an awake pixel is harmless
a.idle_think(s3, 11)
wake(ctx, s3)
ok(a.idle.get(3) is None, "and forgets how many idle thinks it had")
s3 = asleep(3, *tile_xy(40, 40 + 3 * WAKE_CELL_TILES))

# something arrives next to them
mover = pixel(9, *tile_xy(40 - 1, 40))
a.moved(mover)      # a new pixel: noted once, wakes the sleepers in its cell and the 8 around it
ok(1 not in a.sleeping and 2 not in a.sleeping and 3 in a.sleeping, "a pixel appearing next to sleepers wakes them (3x3 cells), not those farther away")
s1 = asleep(1, *tile_xy(40, 40))
a.moved(mover)
ok(1 in a.sleeping, "a pixel that has not changed cell wakes nobody")
mover.position.x, mover.position.y = tile_xy(40 + 1, 40)
a.moved(mover)
ok(1 not in a.sleeping, "a pixel stepping into another cell next to a sleeper wakes it")
s1 = asleep(1, *tile_xy(40, 40))
mover.position.x, mover.position.y = tile_xy(40 + 3 * WAKE_CELL_TILES, 40)
a.moved(mover)
ok(1 in a.sleeping, "a pixel moving about far away does not")

# a tile changes
a.tile_changed(40 + WAKE_CELL_TILES, 40)
ok(1 not in a.sleeping, "a changing tile in the next cell wakes a sleeper")
a.tile_changed(10, 10)
ok(3 in a.sleeping, "a tile changing far away does not")

# scheduled wake
s1 = asleep(1, *tile_xy(40, 40), tick=100)
later = a.sleeping[1]
a.schedule_wake(1, later + 50)
ok(a.sleeping[1] == later, "a scheduled wake never makes a pixel sleep longer")
a.schedule_wake(1, 105)
ok(a.sleeping[1] == 105 and a.due_dt(s1, 104, TICK_DT) is None and a.due_dt(s1, 105, TICK_DT) is not None, "schedule_wake pulls the wake time forward")
a.schedule_wake(77, 5)      # not sleeping: nothing happens

# forget
a.forget(3)
ok(3 not in a.sleeping and 3 not in a.sleepers and 3 not in a.sleep_cell and 3 not in a.cell_of, "forget removes every trace of a pixel")

# works together with the tiers: a sleeping far pixel is not handed the time every stride
b = Activity(far_stride=10)
b.refresh([(0.0, 0.0)])
far_sleeper = pixel(4, TILE_UNITS * 100 * 10, TILE_UNITS * 100 * 10)
for _ in range(IDLE_THINKS):
    b.idle_think(far_sleeper, 0)

turns = [t for t in range(1, 30) if b.due_dt(far_sleeper, t, TICK_DT) is not None]
ok(not turns, "a far pixel that sleeps is not even given its far turns")

# switches
c = Activity()
c.configure(sleep_ticks=0)
c.refresh([])
for _ in range(10):
    c.idle_think(pixel(1, 0.0, 0.0), 0)

ok(not c.sleeping, "sleep_ticks 0 turns sleeping off")
c.configure(sleep_ticks=SLEEP_TICKS, idle_thinks=1)
c.idle_think(pixel(2, 0.0, 0.0), 0)
ok(2 in c.sleeping, "idle_thinks sets how many idle thinks it takes")
c.configure(sleep_ticks=0)
ok(not c.sleeping and not c.sleepers, "turning sleeping off wakes everybody")

# ---- part 2: the real simulation
SEED = 5
TICKS = 200


def make_sim(sleep=True, tiers=False, count=1, at=((30, 30),)):
    """A 120x120 world with one nobody-owned pixel per position in `at`; every pixel finds nothing to do."""
    sim = Simulation(GenerationSettings(width=120, height=120, seed=SEED))
    sim.start_new_game(SEED)
    sim.systems.activity.configure(active_chunks=3 if tiers else 0, far_stride=10 if tiers else 1, sleep_ticks=SLEEP_TICKS if sleep else 0)
    sim.think_calls = {}
    original = sim.systems.get_available_actions

    def nothing(entity):
        sim.think_calls[entity.id] = sim.think_calls.get(entity.id, 0) + 1
        return []

    sim.systems.get_available_actions = nothing
    factory = sim.entity_manager.entity_factory
    definition = None

    for name in ("runner", "commander", "swimmer", "pixel_runner"):
        try:
            definition = factory.load_definition(name)
            break
        except (OSError, ValueError):
            continue

    sim.definition = definition
    sim.pixels = [sim.spawn_pixel(definition, None, *tile_xy(*position)) for position in at]
    return sim


def signature(sim):
    return sorted((p.id, round(p.position.x, 3), round(p.position.y, 3), round(p.health, 6)) for p in sim.entity_manager.all())


sim = make_sim()
a_pixel = sim.pixels[0]
activity = sim.systems.activity
sim.step()
ok(a_pixel.id not in activity.sleeping, "a new pixel is awake")

for _ in range(IDLE_THINKS + 2):
    sim.step()

ok(a_pixel.id in activity.sleeping, f"a pixel that finds nothing to do falls asleep ({sim.think_calls[a_pixel.id]} thinks)")
ok(sim.think_calls[a_pixel.id] <= IDLE_THINKS + 2, "and stopped thinking")

# needs time and age while asleep
need_time = [0.0]
original_update = sim.systems.need_system.update


def spy(entity, step):
    if entity.id == a_pixel.id:
        need_time[0] += step

    return original_update(entity, step)


sim.systems.need_system.update = spy
age0, tick0, thinks0, position0 = a_pixel.age, sim.tick, sim.think_calls[a_pixel.id], (a_pixel.position.x, a_pixel.position.y)

for _ in range(TICKS):
    sim.step()

ok(near(a_pixel.age - age0, TICKS * TICK_DT, 1e-6), "a sleeping pixel still ages every tick")
ok(abs(need_time[0] - TICKS * TICK_DT) <= (SLEEP_TICKS + SLEEP_SPREAD) * TICK_DT + 1e-9, "its needs and memory get all the time that passed (in a few big steps)")
ok(2 <= sim.think_calls[a_pixel.id] - thinks0 <= 2 + TICKS // SLEEP_TICKS, f"it only looks around on its schedule: {sim.think_calls[a_pixel.id] - thinks0} thinks in {TICKS} ticks")
ok((a_pixel.position.x, a_pixel.position.y) == position0 and a_pixel.alive and a_pixel in sim.entity_manager.all(), "nothing about it was frozen or removed")

# command: any command that was applied to it
@commands.command
class PokeForTest(commands.Command):
    name = "poke_for_test"
    selects = False

    def run(self, ctx, player_id, args):
        if "id" not in args:
            raise commands.Rejected("give an id")

        return commands.Outcome(True, applied=[args["id"]])


def wait_asleep(sim, pixel_):
    for _ in range(IDLE_THINKS + SLEEP_TICKS + SLEEP_SPREAD + 2):
        if pixel_.id in sim.systems.activity.sleeping:
            return

        sim.step()


wait_asleep(sim, a_pixel)
ok(a_pixel.id in activity.sleeping, "asleep before the command")
context = commands.CommandContext(sim)
outcome = commands.execute(context, 1, "poke_for_test", {"id": a_pixel.id})
ok(outcome.ok and a_pixel.id not in activity.sleeping, "a command applied to a sleeping pixel wakes it at once")
refused = commands.execute(context, 1, "poke_for_test", {})
ok(not refused.ok, "a refused command wakes nobody (and still does not raise)")

# a changing tile
wait_asleep(sim, a_pixel)
ok(a_pixel.id in activity.sleeping, "asleep before the tile change")
far_tile = sim.world.get_tile(100, 100)
other = next(tile for row in sim.world.tiles for tile in row if tile.name != far_tile.name)
sim.world.set_tile(100, 100, other)
ok(a_pixel.id in activity.sleeping, "a tile changing far away does not wake it")
here = sim.world.get_tile(31, 30)
other_here = next(tile for row in sim.world.tiles for tile in row if tile.name != here.name)
sim.world.set_tile(31, 30, other_here)
ok(a_pixel.id not in activity.sleeping, "a tile changing next to it wakes it")

# a pixel appearing next to it
wait_asleep(sim, a_pixel)
ok(a_pixel.id in activity.sleeping, "asleep before a neighbour appears")
sim.spawn_pixel(sim.definition, None, *tile_xy(100, 100))
sim.step()
ok(a_pixel.id in activity.sleeping, "a pixel appearing far away does not wake it")
sim.spawn_pixel(sim.definition, None, *tile_xy(31, 31))
sim.step()
ok(a_pixel.id not in activity.sleeping, "a pixel appearing next to it wakes it")

# its own schedule, and it sleeps again afterwards
wait_asleep(sim, a_pixel)
before = sim.think_calls[a_pixel.id]
woke_by_itself = False

for _ in range(SLEEP_TICKS + SLEEP_SPREAD + 2):
    sim.step()

    if sim.think_calls[a_pixel.id] > before:
        woke_by_itself = True
        break

ok(woke_by_itself, "a sleeping pixel wakes on its own and looks around")

# fewer decisions overall, and the same world every time
many = tuple((10 + i % 20, 10 + i // 20) for i in range(100))
awake_sim, sleepy_sim = make_sim(sleep=False, at=many), make_sim(sleep=True, at=many)

for _ in range(TICKS):
    awake_sim.step()
    sleepy_sim.step()

awake_thinks, sleepy_thinks = sum(awake_sim.think_calls.values()), sum(sleepy_sim.think_calls.values())
ok(sleepy_thinks < awake_thinks * 0.3, f"100 idle pixels: {sleepy_thinks} decisions instead of {awake_thinks}")
ok(len(sleepy_sim.entity_manager.all()) == len(awake_sim.entity_manager.all()) == 100, "no pixel was removed")
ok(sum(1 for p in sleepy_sim.pixels if p.id in sleepy_sim.systems.activity.sleeping) > 50, "most of them are asleep")
second = make_sim(sleep=True, at=many)

for _ in range(TICKS):
    second.step()

third = make_sim(sleep=True, at=many)

for _ in range(TICKS):
    third.step()

ok(signature(second) == signature(third), "the same seed and pixels give the same world with sleeping on")
never = make_sim(sleep=True, at=many)
never.systems.activity.configure(idle_thinks=10 ** 9)
off = make_sim(sleep=False, at=many)

for _ in range(TICKS):
    never.step()
    off.step()

ok(signature(never) == signature(off), "an enormous idle_thinks gives exactly the world sleep_ticks 0 gives")

# with the 9.2 tiers on as well
tiered = make_sim(sleep=True, tiers=True, at=many)
tiered_second = make_sim(sleep=True, tiers=True, at=many)

for _ in range(TICKS):
    tiered.step()
    tiered_second.step()

ok(signature(tiered) == signature(tiered_second), "sleeping together with the near/far tiers is also repeatable")
ok(sum(tiered.think_calls.values()) <= sleepy_thinks, "and decides no more often")

print(f"all {checks} checks passed")