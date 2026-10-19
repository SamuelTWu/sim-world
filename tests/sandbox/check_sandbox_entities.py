import contextlib
import io
import sys
from types import SimpleNamespace

from src.simworld.sim.dev import layout
from src.simworld.sim.dev.catalog import ENTITY, ITEM, STRUCTURE
from src.simworld.sim.dev.layout import build_sandbox_entities
from src.simworld.world.generator import GenerationSettings, WorldGenerator
from src.simworld.world.sandbox import BLOCK, ENTITY_CAPACITY, ENTITY_PITCH, tile_blocks

failures = 0
UNITS = 32


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


class FakeSim:
    def __init__(self):
        self.world = WorldGenerator(GenerationSettings(mode="sandbox", seed=1)).generate()
        self.spawned = []
        self.systems = SimpleNamespace(context="context")

    def spawn_pixel(self, definition, owner, x, y):
        entity = SimpleNamespace(id=len(self.spawned) + 1, definition=definition, owner=owner, position=SimpleNamespace(x=x, y=y))
        self.spawned.append(entity)
        return entity


def quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = function(*args, **kwargs)

    return result, out.getvalue()


def tile_of(entity):
    return int(entity.position.x // UNITS), int(entity.position.y // UNITS)


made = []


def fake_item(sim, name, definition, x, y):
    entity = SimpleNamespace(id=1000 + len(made), definition=definition, owner=None, position=SimpleNamespace(x=x, y=y))
    made.append(entity)
    return entity


entries = [(ENTITY, "pixel", {"name": "Pixel"}), (ENTITY, "tree", {}), (ITEM, "wood", {"resource": "wood", "amount": 1}), (STRUCTURE, "stone", {"resource": "stone"})]

sim = FakeSim()
labels_before = len(sim.world.labels)
gallery, out = quiet(build_sandbox_entities, sim, entries, {ENTITY: layout.create_entity}, UNITS)
check("exactly one entity per entry that can be made", len(gallery.placed) == 2 and len(sim.spawned) == 2)
check("entries that cannot be made yet are skipped with a reason and named", [(k, n) for k, n, _ in gallery.skipped] == [(ITEM, "wood"), (STRUCTURE, "stone")] and "wood" in out and "stone" in out, out)
check("a blueprint gets its file name as name and sprite when it has none", sim.spawned[1].definition["name"] == "tree" and sim.spawned[1].definition["sprite_id"] == "tree" and sim.spawned[0].definition["name"] == "Pixel")
check("the definition from the catalog is not changed", entries[1][2] == {})
check("owned by nobody", all(entity.owner is None for entity in sim.spawned))

sim = FakeSim()
creators = {ENTITY: layout.create_entity, ITEM: lambda s, n, d, x, y: fake_item(s, n, d, x, y), STRUCTURE: lambda s, n, d, x, y: "occupied"}
gallery, out = quiet(build_sandbox_entities, sim, entries, creators, UNITS)
check("an item creator is used for item entries", len(gallery.placed) == 3 and any(kind == ITEM for kind, *_ in gallery.placed) and len(made) == 1)
check("a creator that returns a reason skips that entry and reports the reason", gallery.skipped == [(STRUCTURE, "stone", "occupied")] and "occupied" in out)

def raising(s, n, d, x, y):
    raise RuntimeError("boom")

sim = FakeSim()
gallery, out = quiet(build_sandbox_entities, sim, entries[:2] + [(ENTITY, "bad", {})], {ENTITY: lambda s, n, d, x, y: raising(s, n, d, x, y) if n == "bad" else layout.create_entity(s, n, d, x, y)}, UNITS)
check("an entry that raises is skipped and does not stop the others", len(gallery.placed) == 2 and gallery.skipped[0][1] == "bad" and "boom" in gallery.skipped[0][2])

many = [(ENTITY, f"e{index:03d}", {}) for index in range(ENTITY_CAPACITY + 40)]
sim = FakeSim()
gallery, out = quiet(build_sandbox_entities, sim, many, {ENTITY: layout.create_entity}, UNITS)
check("past the capacity the rest are refused", len(gallery.placed) == ENTITY_CAPACITY and len(gallery.skipped) == 40 and all("full" in reason for _, _, reason in gallery.skipped))

positions = [tile_of(entity) for entity in sim.spawned]
check("all inside the world", all(0 <= x < sim.world.width and 0 <= y < sim.world.height for x, y in positions))
check("none on top of another", len(set(positions)) == len(positions))
check("all at least a pitch apart", all(abs(a[0] - b[0]) >= ENTITY_PITCH or abs(a[1] - b[1]) >= ENTITY_PITCH for i, a in enumerate(positions) for b in positions[i + 1:]))
covered = {(x, y) for _, x0, y0 in tile_blocks() for y in range(y0, y0 + BLOCK) for x in range(x0, x0 + BLOCK)}
check("none on a tile block", not any(position in covered for position in positions))
check("placed in catalog order, row by row", [entity.definition["name"] for entity in sim.spawned] == [name for _, name, _ in many[:ENTITY_CAPACITY]] and positions == sorted(positions, key=lambda p: (p[1], p[0])))
check("centred in their tile", all(entity.position.x % UNITS == UNITS / 2 and entity.position.y % UNITS == UNITS / 2 for entity in sim.spawned))
check("one label per placed entity, with kind and name, at its tile", len(sim.world.labels) == labels_before + ENTITY_CAPACITY and sim.world.labels[labels_before] == (positions[0][0], positions[0][1], "entity e000"))
check("labels are inside the world", all(0 <= x < sim.world.width and 0 <= y < sim.world.height for x, y, _ in sim.world.labels))

first, second = FakeSim(), FakeSim()
quiet(build_sandbox_entities, first, many, {ENTITY: layout.create_entity}, UNITS)
quiet(build_sandbox_entities, second, many, {ENTITY: layout.create_entity}, UNITS)
check("two builds give identical placements", [(e.id, e.position.x, e.position.y) for e in first.spawned] == [(e.id, e.position.x, e.position.y) for e in second.spawned] and first.world.labels == second.world.labels)

creators = layout.resolve_creators()
check("blueprints can always be made", ENTITY in creators)
print(f"INFO item creator {'found' if ITEM in creators else 'not built yet'}, structure creator {'found' if STRUCTURE in creators else 'not built yet'}")

try:
    from src.simworld.sim.simulation import Simulation
except ImportError as problem:
    print(f"SKIP real simulation section: {problem}")
else:
    real = Simulation(GenerationSettings(mode="sandbox", seed=1))
    real.start_new_game(1)
    before = len(real.entity_manager.all())
    gallery, out = quiet(build_sandbox_entities, real)
    after = real.entity_manager.all()
    check("real simulation: entities created equals entries placed", len(after) - before == len(gallery.placed), out)
    check("real simulation: every entry is placed or skipped with a reason", len(gallery.placed) + len(gallery.skipped) == len(layout.gallery_entries()))
    check("real simulation: no entity owned", all(entity.owner is None for entity in after))
    spots = [(int(entity.position.x // UNITS), int(entity.position.y // UNITS)) for entity in after]
    check("real simulation: all inside the world and none on top of another", len(set(spots)) == len(spots) and all(0 <= x < real.world.width and 0 <= y < real.world.height for x, y in spots))
    check("real simulation: the same count of labels as tile blocks plus placed entities", len(real.world.labels) == len(tile_blocks()) + len(gallery.placed))

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)