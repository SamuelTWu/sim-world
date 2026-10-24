import random
import sys

from src.simworld.sim.core.roster import Roster
from src.simworld.sim.entities.entity import StatusEffect
from src.simworld.sim.entities.entity_manager import EntityManager

SYSTEMS = ("thinkers", "needy", "statused", "snapped", "owned")


class Item:
    def __init__(self, name):
        self.name = name


def expected_reasons(entity):
    snaps = entity.has_prop("snap_to_grid") and entity.prop("snap_to_grid") > 0
    return {"thinkers": bool(entity.traits) or entity.task is not None, "needy": bool(entity.needs), "statused": bool(entity.statuses), "snapped": snaps, "owned": entity.owner is not None}


def rebuilt(manager):
    fresh = Roster()

    for entity_id in sorted(manager.entities):
        entity = manager.entities[entity_id]

        if entity.alive:
            fresh.sync(entity)

    return fresh


def assert_same(manager, roster, label):
    fresh = rebuilt(manager)

    for name in SYSTEMS:
        assert roster.ids(name) == fresh.ids(name), f"{label}: {name} differs: live {roster.ids(name)[:10]} rebuilt {fresh.ids(name)[:10]}"

    assert roster.ids("members") == fresh.ids("members"), f"{label}: members differ"

    for entity_id, entity in ((i, manager.entities[i]) for i in roster.members):
        assert entity.alive, f"{label}: dead entity {entity_id} is in the roster"
        assert any(expected_reasons(entity).values()), f"{label}: entity {entity_id} is in the roster for no reason"

    for entity in manager.all():
        wanted = any(expected_reasons(entity).values())
        assert (entity.id in roster.members) == wanted, f"{label}: entity {entity.id} wanted={wanted} but in roster={entity.id in roster.members}"

    assert set(roster.asleep) <= set(roster.members), f"{label}: a sleeper is not a member"
    awake = [entity.id for entity in roster.active_list()]
    assert awake == sorted(awake), f"{label}: active_list is not by id"
    assert awake == [i for i in sorted(roster.members) if i not in roster.asleep], f"{label}: active_list differs from members minus sleepers"


def random_run(seed, operations=10000):
    rng = random.Random(seed)
    manager = EntityManager()
    roster = manager.roster

    def pick():
        alive = [entity for entity in manager.entities.values() if entity.alive]
        return rng.choice(alive) if alive else None

    from src.simworld.sim.entities.entity import Entity

    for step in range(operations):
        action = rng.choice(("spawn", "spawn", "trait", "untrait", "need", "unneed", "status", "expire", "task", "endtask", "sleep", "wake", "kill", "flush", "snap", "list"))
        entity = pick()

        if action == "spawn" or entity is None:
            owner = rng.choice((None, None, None, 1, 2))
            manager.register(Entity(id=manager.allocate_id(), owner=owner, traits=rng.choice(({}, {}, {"roam": {}})), props={"snap_to_grid": 32.0} if rng.random() < 0.05 else {}))
        elif action == "trait":
            manager.set_trait(entity, rng.choice(("roam", "attack")), {})
        elif action == "untrait":
            for name in list(entity.traits):
                manager.drop_trait(entity, name)
        elif action == "need":
            entity.needs[rng.choice(("hunger", "boredom"))] = Item("n")
            manager.touch(entity)
        elif action == "unneed":
            entity.needs.clear()
            manager.touch(entity)
        elif action == "status":
            manager.add_status(entity, StatusEffect(rng.choice(("burning", "slow")), 1.0))
        elif action == "expire":
            manager.set_statuses(entity, [])
        elif action == "task":
            manager.set_task(entity, Item("task"), 1.0)
        elif action == "endtask":
            manager.set_task(entity, None, 0.0)
        elif action == "sleep":
            roster.sleep(entity)
        elif action == "wake":
            roster.wake(entity)
        elif action == "kill":
            manager.kill(entity.id)
        elif action == "flush":
            manager.flush()
        elif action == "snap":
            entity.props["snap_to_grid"] = rng.choice((0.0, 32.0))
            manager.touch(entity)
        elif action == "list":
            roster.active_list()
            rebuilds = roster.rebuilds
            roster.active_list()
            assert roster.rebuilds == rebuilds, "the list was rebuilt without a change"

        if step % 25 == 0:
            assert_same(manager, roster, f"seed {seed} step {step}")

    assert_same(manager, roster, f"seed {seed} end")


def snapshot_is_stable():
    from src.simworld.sim.entities.entity import Entity
    manager = EntityManager()
    first = manager.register(Entity(id=1, traits={"roam": {}}))
    listed = manager.roster.active_list()
    manager.register(Entity(id=2, traits={"roam": {}}))
    assert [entity.id for entity in listed] == [1], "a list handed out must not change while it is iterated"
    assert [entity.id for entity in manager.roster.active_list()] == [1, 2]
    manager.roster.sleep(first)
    assert [entity.id for entity in manager.roster.active_list()] == [2]
    manager.roster.wake(first)
    assert [entity.id for entity in manager.roster.active_list()] == [1, 2]
    manager.kill(1)
    assert [entity.id for entity in manager.roster.active_list()] == [2]
    manager.touch(first)
    assert [entity.id for entity in manager.roster.active_list()] == [2], "a dead entity must not come back through sync"
    inert = manager.register(Entity(id=3))
    assert 3 not in manager.roster.members and not manager.roster.visits(inert)
    manager.set_trait(inert, "roam", {})
    assert manager.roster.visits(inert)
    manager.drop_trait(inert, "roam")
    assert not manager.roster.visits(inert)


def real_tree():
    from src.simworld.sim.simulation import Simulation
    from src.simworld.world.generator import GenerationSettings
    from src.simworld.sim.core.sim_context import TILE_UNITS

    sim = Simulation(GenerationSettings(width=40, height=40, seed=5))
    sim.start_new_game(5)
    manager = sim.entity_manager
    factory = manager.entity_factory
    runner = None

    for name in ("runner", "pixel_runner"):
        try:
            runner = factory.load_definition(name)
            break
        except (OSError, ValueError):
            continue

    assert runner is not None, "no runner blueprint found"
    inert = {"name": "static", "kind": "static", "sprite_id": "pixel", "tags": ["static"]}
    rng = random.Random(3)
    statics, movers = [], []

    for index in range(60):
        x, y = rng.randint(3, 36) * TILE_UNITS + 16, rng.randint(3, 36) * TILE_UNITS + 16
        (statics if index % 3 else movers).append(sim.spawn_pixel(inert if index % 3 else runner, None, x, y))

    mine = sim.spawn_pixel(runner, 1, 20 * TILE_UNITS, 20 * TILE_UNITS)
    placed_inert = sim.spawn_pixel(inert, 1, 21 * TILE_UNITS, 21 * TILE_UNITS)
    assert manager.roster.visits(placed_inert), "an owned entity is always visited"
    assert all(not manager.roster.visits(entity) for entity in statics), "inert unowned entities must not be in the roster"
    assert all(manager.roster.visits(entity) for entity in movers + [mine])

    for tick in range(80):
        sim.step()

        if tick % 10 == 0:
            assert_same(manager, manager.roster, f"real tree tick {tick}")

            old_loop = [entity.id for entity in manager.all() if any(expected_reasons(entity).values())]
            assert [entity.id for entity in manager.roster.active_list()] == old_loop, "the roster must visit exactly what the old loop needed, in id order"

    assert all(entity.age == 0.0 for entity in statics), "inert entities must not be aged"
    assert all(entity.age > 0.0 for entity in movers + [mine]), "visited entities are still aged every tick"

    from src.simworld.sim.entities.entity import StatusEffect as Effect
    victim = next(entity for entity in statics if entity.alive)
    manager.add_status(victim, Effect("burning", 0.2))
    assert manager.roster.visits(victim)

    for _ in range(10):
        sim.step()

    assert not manager.roster.visits(victim), "an expired status takes the entity out of the roster again"
    assert_same(manager, manager.roster, "real tree end")


def main():
    snapshot_is_stable()

    for seed in (1, 2, 3):
        random_run(seed)

    print("roster: pure part passed (3 seeds x 10000 operations)")

    try:
        real_tree()
    except ImportError as problem:
        print(f"roster: REAL TREE PART COULD NOT RUN ({problem}); run it in your tree", file=sys.stderr)
        raise

    print("roster: real tree part passed")


if __name__ == "__main__":
    main()