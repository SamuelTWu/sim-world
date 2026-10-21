import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
ENTITY_DIR = PACKAGE / "content" / "entities"
RESOURCE_DIR = PACKAGE / "content" / "resources"

ENTITY = "entity"
ITEM = "item"
STRUCTURE = "structure"


def json_files(folder):
    if folder is None or not Path(folder).is_dir():
        return []

    return sorted((path for path in Path(folder).glob("*.json") if path.is_file() and not path.name.startswith(("_", "."))), key=lambda path: path.name)


def read_object(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as problem:
        raise ValueError(f"cannot read it: {problem}") from None

    if not isinstance(data, dict):
        raise ValueError("the file must hold one JSON object")

    return data


def entity_entries(folder, skipped):
    entries = []

    for path in json_files(folder):
        try:
            data = read_object(path)

            if "name" in data and not isinstance(data["name"], str):
                raise ValueError("`name` must be text")
        except ValueError as problem:
            skipped.append((path.name, str(problem)))
            continue

        if data.get("gallery") is False:
            continue

        entries.append((ENTITY, path.stem, data))

    return entries


def resource_entries(folder, skipped):
    entries = []

    for path in json_files(folder):
        try:
            data = read_object(path)
            resource = data.get("id", path.stem)

            if not isinstance(resource, str) or not resource:
                raise ValueError("`id` must be non-empty text")

            for part in (ITEM, STRUCTURE):
                if part in data and not isinstance(data[part], dict):
                    raise ValueError(f"`{part}` must be an object")
        except ValueError as problem:
            skipped.append((path.name, str(problem)))
            continue

        if data.get("gallery") is False:
            continue

        if ITEM in data:
            entries.append((ITEM, resource, {"resource": resource, "amount": 1}))

        if STRUCTURE in data:
            entries.append((STRUCTURE, resource, {"resource": resource}))

    return entries


def load_gallery(entity_dir=ENTITY_DIR, resource_dir=RESOURCE_DIR):
    skipped = []
    entries = entity_entries(entity_dir, skipped) + resource_entries(resource_dir, skipped)
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return entries, skipped

def catalog_names(entity_dir=ENTITY_DIR, resource_dir=RESOURCE_DIR, tiles=None):
    if tiles is None:
        from ...world.tile_types import TILE_TYPES as tiles

    entries, _ = load_gallery(entity_dir, resource_dir)
    return {
        "blueprints": sorted({name for kind, name, _ in entries if kind == ENTITY}),
        "tiles": sorted({tile.name for tile in tiles.values()}),
        "resources": sorted({name for kind, name, _ in entries if kind in (ITEM, STRUCTURE)}),
        "items": sorted({name for kind, name, _ in entries if kind == ITEM}),
        "structures": sorted({name for kind, name, _ in entries if kind == STRUCTURE}),
    }

def gallery_entries(entity_dir=ENTITY_DIR, resource_dir=RESOURCE_DIR):
    entries, skipped = load_gallery(entity_dir, resource_dir)

    for name, reason in skipped:
        print(f"[catalog] skipped {name}: {reason}", flush=True)

    return entries