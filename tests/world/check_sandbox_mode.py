from src.simworld.world.tile import Tile
from src.simworld.world import tile_types
from src.simworld.world import sandbox
from src.simworld.world.generator import GenerationSettings, WorldGenerator
from src.simworld.world.sandbox import BLOCK, ENTITY_CAPACITY, ENTITY_PITCH, MIN_SIZE, entity_slots, layout_for, tile_blocks
import os
import subprocess
import sys
from pathlib import Path

failures = 0


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


def make(**changes):
    return WorldGenerator(GenerationSettings(mode="sandbox", seed=5, **changes)).generate()


def cell(world, x, y):
    return world.tiles[y][x]


if "--print-checksum" in sys.argv:
    world = make()
    world.finish_generation()
    print(world.generation_checksum)
    sys.exit(0)

world = make()
blocks = tile_blocks()
names = [tile.name for tile in sandbox.sorted_tiles()]
check("tile names are unique", len(set(names)) == len(names), str(names))
check("one block per tile type", len(blocks) == len(tile_types.TILE_TYPES))
check("blocks are in sorted order", [tile.name for tile, _, _ in blocks] == sorted(names))
check("world is at least the minimum size", world.width >= MIN_SIZE and world.height >= MIN_SIZE)

covered = set()
overlap = False
outside = False
wrong = []

for tile, x0, y0 in blocks:
    for y in range(y0, y0 + BLOCK):
        for x in range(x0, x0 + BLOCK):
            if (x, y) in covered:
                overlap = True

            covered.add((x, y))

            if not (0 <= x < world.width and 0 <= y < world.height):
                outside = True
            elif cell(world, x, y) is not tile:
                wrong.append((tile.name, x, y))

check("no two blocks overlap", not overlap)
check("every block is inside the world", not outside)
check("every cell of every block is its tile", not wrong, str(wrong[:3]))

gap_ok = all(cell(world, x, y) is sandbox.default_tile() for y in range(world.height) for x in range(world.width) if (x, y) not in covered)
check("everything outside the blocks is the default tile", gap_ok)

pitch_ok = all(abs(x1 - x0) >= BLOCK + sandbox.GAP or abs(y1 - y0) >= BLOCK + sandbox.GAP for i, (_, x0, y0) in enumerate(blocks) for _, x1, y1 in blocks[i + 1:])
check("blocks are at least the gap apart", pitch_ok)
check("first block starts 8 tiles from the corner", (blocks[0][1], blocks[0][2]) == (8, 8))

layout = layout_for(len(blocks))
check("tile blocks end above the entity area", max(y for _, _, y in blocks) + BLOCK <= layout.entity_top)

slots = entity_slots()
check("there is room for the entity capacity", len(slots) == ENTITY_CAPACITY)
check("entity slots are inside the world", all(0 <= x < world.width and 0 <= y < world.height for x, y in slots))
check("entity slots are all different and a pitch apart", len(set(slots)) == len(slots) and all(abs(a[0] - b[0]) >= ENTITY_PITCH or abs(a[1] - b[1]) >= ENTITY_PITCH for i, a in enumerate(slots[:60]) for b in slots[i + 1:60]))
check("entity slots are below the tile area", min(y for _, y in slots) > max(y for _, _, y in blocks) + BLOCK)
check("entity slots avoid every tile block", not any((x, y) in covered for x, y in slots))

check("width and height settings are ignored", make(width=10, height=10).checksum() == make(width=500, height=300).checksum())
check("two builds in one process are identical", make().checksum() == make().checksum())

root = Path(__file__).resolve().parents[2]
sums = []

for hashseed in ("1", "424242"):
    run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--print-checksum"], capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": hashseed, "PYTHONPATH": os.pathsep.join(filter(None, [str(root / "src"), str(root), os.environ.get("PYTHONPATH", "")]))})
    sums.append(run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr[-300:])

check("the same checksum with two different PYTHONHASHSEED values", sums[0] == sums[1] and len(sums[0]) == 64, str(sums))
check("the generator uses no random numbers", "random" not in Path(sandbox.__file__).read_text())

before_blocks = [(tile.name, x, y) for tile, x, y in tile_blocks()]
before = [[cell(world, x, y).name for x in range(world.width)] for y in range(world.height)]
extra = Tile(color=(1, 2, 3), name="zzz_added_tile")
tile_types.TILE_TYPES["zzz_added_tile"] = extra

try:
    after_world = make()
    after_blocks = [(tile.name, x, y) for tile, x, y in tile_blocks()]
    changed = [(x, y) for y in range(after_world.height) for x in range(after_world.width) if (y >= len(before) or x >= len(before[0]) or before[y][x] != cell(after_world, x, y).name)]
    new = after_blocks[-1]
    inside_new = all(new[1] <= x < new[1] + BLOCK and new[2] <= y < new[2] + BLOCK for x, y in changed)
    check("adding a tile type adds exactly one block", len(after_blocks) == len(before_blocks) + 1 and after_blocks[:-1] == before_blocks and new[0] == "zzz_added_tile")
    check("adding a tile type changes nothing outside the new block", inside_new and (after_world.width, after_world.height) == (world.width, world.height), f"{len(changed)} cells changed")
finally:
    del tile_types.TILE_TYPES["zzz_added_tile"]

labels = make().labels
blocks_now = tile_blocks()
check("one label per tile block", len(labels) == len(blocks_now), f"{len(labels)} labels, {len(blocks_now)} blocks")
check("each label is (x, y, tile name) at its block corner", labels == [(x, y, tile.name) for tile, x, y in blocks_now])
check("every label text is a tile name and is unique", len({text for _, _, text in labels}) == len(labels) and {text for _, _, text in labels} == {tile.name for tile in tile_types.TILE_TYPES.values()})
check("every label is inside the world", all(0 <= x < world.width and 0 <= y < world.height for x, y, _ in labels))
check("labels are rebuilt identically each time", make().labels == make().labels)
check("labels do not change the world checksum", make().checksum() == make().checksum())
normal = WorldGenerator(GenerationSettings(width=70, height=70, seed=3)).generate()
check("normal worlds have no labels", normal.labels == [])
check("labels are not shared between worlds", normal.labels is not make().labels and make().labels is not make().labels)

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)