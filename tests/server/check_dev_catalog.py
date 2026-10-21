import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.simworld.server import dev_commands as dev
from src.simworld.server.dev_time import init_time
from src.simworld.sim.dev import catalog, tools

failures = []


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Tile:
    def __init__(self, name):
        self.name = name


root = Path(tempfile.mkdtemp())
entities, resources = root / "entities", root / "resources"
entities.mkdir()
resources.mkdir()

for name, data in (("wolf", {}), ("deer", {"name": "Deer"}), ("tree", {"gallery": False}), ("zebra", {})):
    (entities / f"{name}.json").write_text(json.dumps(data))

(entities / "broken.json").write_text("{nope")
(entities / "list.json").write_text("[1]")
(entities / "_hidden.json").write_text("{}")
(entities / "notes.txt").write_text("hello")
(resources / "wood.json").write_text(json.dumps({"id": "wood", "item": {}, "structure": {}}))
(resources / "ore_file.json").write_text(json.dumps({"id": "ore", "item": {}}))
(resources / "gas.json").write_text(json.dumps({"structure": {}}))
(resources / "secret.json").write_text(json.dumps({"id": "secret", "item": {}, "gallery": False}))
(resources / "plain.json").write_text(json.dumps({"id": "plain"}))
(resources / "bad.json").write_text("[1]")
TILES = {3: Tile("stone"), 1: Tile("grass"), 7: Tile("water"), 9: Tile("grass")}

found = catalog.catalog_names(entities, resources, TILES)
check("the result has exactly the planned keys", sorted(found) == ["blueprints", "items", "resources", "structures", "tiles"], str(sorted(found)))
check("blueprints are the gallery blueprints, sorted", found["blueprints"] == ["deer", "wolf", "zebra"], str(found["blueprints"]))
check("hidden, broken, underscore and non-json files are left out", not {"tree", "broken", "list", "_hidden", "notes"} & set(found["blueprints"]))
check("tiles are the registry's names, sorted, without duplicates", found["tiles"] == ["grass", "stone", "water"], str(found["tiles"]))
check("resources are sorted, without duplicates, and only those with an item or structure form", found["resources"] == ["gas", "ore", "wood"], str(found["resources"]))
check("a resource id comes from the file's id, not its name", "ore" in found["resources"] and "ore_file" not in found["resources"])
check("items and structures say which forms exist", found["items"] == ["ore", "wood"] and found["structures"] == ["gas", "wood"], f"{found['items']} {found['structures']}")
check("every list is sorted and free of duplicates", all(values == sorted(set(values)) for values in found.values()))
check("every value is plain text", all(isinstance(name, str) for values in found.values() for name in values))
check("the lists are new each time", catalog.catalog_names(entities, resources, TILES)["tiles"] is not found["tiles"])
empty = catalog.catalog_names(root / "missing", root / "missing", {})
check("missing folders and no tiles give empty lists, not an error", all(values == [] for values in empty.values()) and len(empty) == 5, str(empty))

text = tools.catalog_text(found)
check("the text gives each list with its count", text == "blueprints (3): deer, wolf, zebra\ntiles (3): grass, stone, water\nresources (3): gas, ore, wood", text)
crowd = {"blueprints": [f"b{i:02d}" for i in range(30)], "tiles": [], "resources": []}
check("a long list is cut with a count and an empty one says none", "(+24 more)" in tools.catalog_text(crowd) and "tiles (0): none" in tools.catalog_text(crowd), tools.catalog_text(crowd))


def server_for(flag=True):
    server = SimpleNamespace(sim=SimpleNamespace(sandbox=flag, tick=0, systems=SimpleNamespace(counters=SimpleNamespace(values={}, add=lambda name, amount=1: None))))
    init_time(server)
    return server


def ask(server):
    return dev.run_dev(server, SimpleNamespace(player_id=3), "catalog", {})


original = dev.catalog_names
dev.catalog_names = lambda: catalog.catalog_names(entities, resources, TILES)

try:
    result = ask(server_for())
    check("dev catalog returns the lists as data and a summary as text", result.ok and result.data == found and result.text == text, str(result))
    check("dev catalog takes no arguments", dev.run_dev(server_for(), None, "catalog", {"x": 1}).ok is False and dev.run_dev(server_for(), None, "catalog", None).ok is False)
    normal = server_for(False)
    result = ask(normal)
    check("a normal server refuses it and returns no data", result == dev.DevResult(False, "not available") and result.data is None)
finally:
    dev.catalog_names = original

from src.simworld.world.tile_types import TILE_TYPES

PART = ("item", "structure")


def disk_blueprints(folder):
    names = []

    for path in sorted(folder.glob("*.json")):
        if path.name.startswith(("_", ".")):
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue

        if isinstance(data, dict) and data.get("gallery") is not False and isinstance(data.get("name", ""), str):
            names.append(path.stem)

    return names


def disk_resources(folder, part=None):
    names = set()

    for path in sorted(folder.glob("*.json")):
        if path.name.startswith(("_", ".")):
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue

        if not isinstance(data, dict) or data.get("gallery") is False or not all(isinstance(data[key], dict) for key in PART if key in data):
            continue

        resource = data.get("id", path.stem)

        if isinstance(resource, str) and resource and any(key in data for key in (PART if part is None else (part,))):
            names.add(resource)

    return sorted(names)


real = catalog.catalog_names()
check("the real blueprints match the files on disk", real["blueprints"] == sorted(disk_blueprints(catalog.ENTITY_DIR)), f"{real['blueprints']} vs {disk_blueprints(catalog.ENTITY_DIR)}")
check("the real resources match the files on disk", real["resources"] == disk_resources(catalog.RESOURCE_DIR) and real["items"] == disk_resources(catalog.RESOURCE_DIR, "item") and real["structures"] == disk_resources(catalog.RESOURCE_DIR, "structure"), str(real))
check("the real tiles match TILE_TYPES", real["tiles"] == sorted({tile.name for tile in TILE_TYPES.values()}) and len(real["tiles"]) > 0, str(real["tiles"]))
check("the real gallery entries are exactly the catalog's blueprints and resources", sorted({name for kind, name, _ in catalog.gallery_entries() if kind == "entity"}) == real["blueprints"] and sorted({name for kind, name, _ in catalog.gallery_entries() if kind in ("item", "structure")}) == real["resources"])
check("every listed blueprint can be spawned by name", all(tools.load_entity(name) is not None for name in real["blueprints"]), str([name for name in real["blueprints"] if tools.load_entity(name) is None]))
check("every listed item and structure resource has that form on disk", all(tools.load_resource(name) is not None and "item" in tools.load_resource(name) for name in real["items"]) and all(tools.load_resource(name) is not None and "structure" in tools.load_resource(name) for name in real["structures"]))
check("every listed tile can be painted", all(name in tools.tiles_by_name() for name in real["tiles"]))

live = server_for()
result = ask(live)
check("a real dev catalog on a sandbox server returns the real lists", result.ok and result.data == real, str(result.text))
print(result.text)
live_normal = server_for(False)
check("a real normal server refuses it", ask(live_normal).text == "not available")

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")