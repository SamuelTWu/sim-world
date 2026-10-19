import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

from src.simworld.sim.dev import catalog
from src.simworld.sim.dev.catalog import ENTITY, ITEM, STRUCTURE, gallery_entries, load_gallery

failures = 0


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


def write(folder, name, data):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def keys(entries):
    return [(kind, name) for kind, name, _ in entries]


with tempfile.TemporaryDirectory() as root:
    root = Path(root)
    entities, resources = root / "entities", root / "resources"
    write(entities, "pixel.json", {"name": "Pixel", "maxHealth": 5})
    write(entities, "tree.json", {"props": {"durability": 10}})
    write(entities, "door.json", {"structure": {}, "props": {"blocks_movement": 1}})
    write(entities, "item.json", {"kind": "item", "gallery": False})
    write(entities, "_scratch.json", {"name": "hidden"})
    write(entities, "broken.json", "{ not json")
    write(entities, "list.json", "[1, 2]")
    write(entities, "badname.json", {"name": 5})
    write(entities, "notes.txt", "ignored")
    write(resources, "wood.json", {"id": "wood", "item": {"stack": 100}, "structure": {"max_health": 4}})
    write(resources, "fish.json", {"id": "fish", "item": {"stack": 20}})
    write(resources, "gold.json", {"id": "gold"})
    write(resources, "seeds.json", {"id": "seeds", "structure": {}})
    write(resources, "bad_item.json", {"id": "bad", "item": 5})
    write(resources, "bad_id.json", {"id": 7, "item": {}})

    entries, skipped = load_gallery(entities, resources)
    expected = [(ENTITY, "door"), (ENTITY, "pixel"), (ENTITY, "tree"), (ITEM, "fish"), (ITEM, "wood"), (STRUCTURE, "seeds"), (STRUCTURE, "wood")]
    check("entries match the files in the folders, sorted by (kind, name)", keys(entries) == expected, str(keys(entries)))
    check("a resource with both forms gives two entries", (ITEM, "wood") in keys(entries) and (STRUCTURE, "wood") in keys(entries))
    check("a resource with neither form gives none", not any(name == "gold" for _, name, _ in entries))
    check("a blueprint file is passed through as its JSON", dict(((k, n), d) for k, n, d in entries)[(ENTITY, "pixel")] == {"name": "Pixel", "maxHealth": 5})
    check("an item entry is one item of that resource", dict(((k, n), d) for k, n, d in entries)[(ITEM, "fish")] == {"resource": "fish", "amount": 1})
    check("a structure entry names its resource", dict(((k, n), d) for k, n, d in entries)[(STRUCTURE, "seeds")] == {"resource": "seeds"})
    check("gallery false, underscore files and other extensions are left out without a message", all(name not in {"item", "_scratch", "notes"} for _, name, _ in entries) and not any(file in {"item.json", "_scratch.json", "notes.txt"} for file, _ in skipped))
    check("every bad file is reported by name", sorted(file for file, _ in skipped) == ["bad_id.json", "bad_item.json", "badname.json", "broken.json", "list.json"], str(skipped))
    check("every skipped file has a reason", all(reason for _, reason in skipped))

    out = io.StringIO()

    with contextlib.redirect_stdout(out):
        printed = gallery_entries(entities, resources)

    check("gallery_entries prints the name of each skipped file", all(file in out.getvalue() for file in ("broken.json", "list.json", "bad_item.json")), out.getvalue())
    check("gallery_entries returns the same entries", keys(printed) == expected)

    write(entities, "boulder.json", {"props": {"blocks_movement": 1}})
    after, _ = load_gallery(entities, resources)
    check("dropping in a new JSON file adds exactly one entry", keys(after) == sorted(expected + [(ENTITY, "boulder")]) and len(after) == len(entries) + 1)
    write(resources, "stone.json", {"id": "stone", "item": {}, "structure": {}})
    later, _ = load_gallery(entities, resources)
    check("a new resource with both forms adds two entries", len(later) == len(after) + 2)
    (entities / "boulder.json").unlink()
    gone, _ = load_gallery(entities, resources)
    check("removing a file removes its entry", (ENTITY, "boulder") not in keys(gone))

    other = root / "again"
    for name in ("z.json", "a.json", "m.json"):
        write(other, name, {})

    first = keys(load_gallery(other, None)[0])
    for name in ("z.json", "a.json", "m.json"):
        (other / name).unlink()
    for name in ("m.json", "z.json", "a.json"):
        write(other, name, {})
    check("the order does not depend on file creation order", first == keys(load_gallery(other, None)[0]) == [(ENTITY, "a"), (ENTITY, "m"), (ENTITY, "z")])

    check("missing folders give no entries and no error", load_gallery(root / "nope", root / "nada") == ([], []))
    check("None folders are allowed", load_gallery(None, None) == ([], []))

for label, folder in (("entity", catalog.ENTITY_DIR), ("resource", catalog.RESOURCE_DIR)):
    print(f"INFO {label} folder: {folder} ({'found' if folder.is_dir() else 'not found'})")

real, bad = load_gallery()
files = catalog.json_files(catalog.ENTITY_DIR)
hidden = 0

for path in files:
    try:
        if catalog.read_object(path).get("gallery") is False:
            hidden += 1
    except ValueError:
        pass

entity_count = sum(1 for kind, _, _ in real if kind == ENTITY)
check("real folders: one entity entry per readable, visible blueprint file", entity_count == len(files) - hidden - sum(1 for name, _ in bad if (catalog.ENTITY_DIR / name).exists()), f"{entity_count} entries, {len(files)} files, {hidden} hidden, {len(bad)} skipped")
check("real folders: every entry is well formed", all(kind in (ENTITY, ITEM, STRUCTURE) and isinstance(name, str) and name and isinstance(definition, dict) for kind, name, definition in real))
check("real folders: no two entries share a kind and name", len(set(keys(real))) == len(real))
check("real folders: the order is stable", keys(real) == keys(load_gallery()[0]))

for name, reason in bad:
    print(f"WARN real file skipped: {name}: {reason}")

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)