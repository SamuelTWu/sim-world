import contextlib
import io
import sys
import traceback
from types import SimpleNamespace

from src.simworld.sim.core import activity as activity_module
from src.simworld.sim.core.activity import ACTIVE, ASLEEP, FAR, FROZEN, Activity, wake

failures = 0


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


def pixel(number, x=10.0, y=10.0):
    return SimpleNamespace(id=number, position=SimpleNamespace(x=x, y=y), traits={})


def quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


KEYS = ("needs", "memory", "think", "some_new_critical_key")
activity = Activity()
a, b = pixel(5), pixel(6)
check("a pixel is not frozen to begin with", activity.state(a, 0) != FROZEN and not activity.is_frozen(5))
activity.freeze(5)
check("a frozen pixel reports FROZEN", activity.state(a, 1) == FROZEN and activity.is_frozen(5))
check("freezing one pixel does not freeze another", activity.state(b, 1) != FROZEN)
check("a frozen pixel is skipped by every key, including keys that are not in the rate table", all(activity.due(key, a, FROZEN, 0.05, 1) is None for key in KEYS))
check("another pixel still runs every key", all(activity.due(key, b, activity.state(b, 1), 0.05, 1) == 0.05 for key in KEYS))
activity.refresh([])
check("it stays frozen once the activity system is running", activity.state(a, 2) == FROZEN and all(activity.due(key, a, FROZEN, 0.05, 2) is None for key in KEYS))
check("freezing is not the same as the far tier or sleeping", FROZEN not in (ACTIVE, FAR, ASLEEP))

for tick in range(3, 60):
    activity.due("needs", pixel(7), activity.state(pixel(7), tick), 0.05, tick)

check("a far pixel holds back time (the setup for the next check)", activity.owed_for(7) > 0)
activity.freeze(7)
check("freezing clears time owed, so it does not catch up when released", activity.owed_for(7) == 0.0)

for tick in range(60, 80):
    activity.state(pixel(7), tick)
    activity.due("needs", pixel(7), activity.state(pixel(7), tick), 0.05, tick)

check("a frozen pixel never builds up owed time", activity.owed_for(7) == 0.0)

activity.wake(a, 100)
check("wake() does not unfreeze", activity.is_frozen(5) and activity.state(a, 101) == FROZEN)
activity.wake_near(activity.wake_cell(a))
activity.tile_changed(0, 0)
activity.moved(a)
check("a nearby change or a moving neighbour does not unfreeze", activity.is_frozen(5))
check("the module-level wake(ctx, entity) used by attacks does not unfreeze", (wake(SimpleNamespace(activity=activity, tick=102), a), activity.is_frozen(5))[1])

sleeper = pixel(8)
activity.sleeping[8] = 500
activity.sleep_cell[8] = (0, 0)
activity.sleepers[(0, 0)] = {8}
activity.freeze(8)
check("freezing a sleeping pixel takes it out of the sleepers", 8 not in activity.sleeping and 8 not in activity.sleep_cell and not activity.sleepers)

check("unfreeze returns True once", activity.unfreeze(5) is True and activity.unfreeze(5) is False)
check("an unfrozen pixel runs its systems again", activity.state(a, 110) != FROZEN and activity.due("think", a, activity.state(a, 111), 0.05, 111) is not None)
check("it has no idle streak left over", 5 not in activity.idle)

activity.freeze(9)
activity.forget(9)
check("forget removes a frozen pixel", not activity.is_frozen(9))

try:
    from src.simworld.sim.simulation import Simulation
    from src.simworld.sim.dev import layout
    from src.simworld.sim.dev.catalog import ENTITY, gallery_entries
    from src.simworld.sim.dev.layout import build_sandbox_entities
    from src.simworld.world.generator import GenerationSettings
except ImportError:
    traceback.print_exc()
    check("the real simulation can be imported", False, "see the traceback above")
else:
    real = Simulation(GenerationSettings(mode="sandbox", seed=1))
    real.start_new_game(1)
    gallery = quiet(build_sandbox_entities, real)
    gallery_pixels = [entity for kind, _, entity, _, _ in gallery.placed if kind == ENTITY]
    frozen_ids = real.systems.activity.frozen
    check("real: every placed gallery entity is frozen", len(gallery_pixels) > 0 and all(entity.id in frozen_ids for entity in gallery_pixels))

    templates = [(name, definition) for kind, name, definition in gallery_entries() if kind == ENTITY]
    control = quiet(layout.create_entity, real, templates[0][0], templates[0][1], 3.5 * 32, 3.5 * 32) if templates else None
    check("real: a control entity made the same way is not frozen", control is not None and control.id not in frozen_ids)

    thoughts = []
    original = real.systems.think
    real.systems.think = lambda entity: (thoughts.append(entity.id), original(entity))[1]
    value = lambda need: getattr(need, "value", None)
    before = {entity.id: (entity.position.x, entity.position.y, {name: value(need) for name, need in entity.needs.items()}) for entity in gallery_pixels}

    for _ in range(200):
        real.step()

    check("real: after 200 ticks every gallery entity is exactly where it was", all((entity.position.x, entity.position.y) == before[entity.id][:2] for entity in gallery_pixels))
    check("real: none of them has a task", all(entity.task is None for entity in gallery_pixels))
    check("real: none of them ever decided", not any(entity.id in thoughts for entity in gallery_pixels))
    check("real: their needs did not change", all({name: value(need) for name, need in entity.needs.items()} == before[entity.id][2] for entity in gallery_pixels))
    check("real: the control entity did decide, so the sandbox itself is not what stops them", control is not None and control.id in thoughts)

    chosen = next((entity for entity in gallery_pixels if entity.traits), gallery_pixels[0])
    thoughts.clear()
    check("real: unfreeze reports it worked", real.systems.activity.unfreeze(chosen.id) is True)

    for _ in range(60):
        real.step()

        if chosen.id in thoughts:
            break

    check("real: a released entity starts deciding", chosen.id in thoughts)
    check("real: the others are still frozen and still not deciding", all(entity.id in real.systems.activity.frozen and entity.id not in thoughts for entity in gallery_pixels if entity is not chosen))
    print(f"INFO released '{chosen.name}': task {'started: ' + str(getattr(chosen.task, 'name', chosen.task)) if chosen.task is not None else 'none yet'}")

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)