import math
from collections import namedtuple

from ..ai import stats
from ...shared.dev_commands import MAX_SEED
from ...world.sandbox import REGION_SIZE, region_origin
from .catalog import ENTITY, ENTITY_DIR, ITEM, RESOURCE_DIR, STRUCTURE, json_files, read_object
from .layout import create_entity, find_function

KINDS = {"item": ITEM, "structure": STRUCTURE}

Spawned = namedtuple("Spawned", "id label tile_x tile_y")
Deleted = namedtuple("Deleted", "id label")
Woke = namedtuple("Woke", "id label was_frozen")
Painted = namedtuple("Painted", "name tile_x tile_y before changed")
Inspection = namedtuple("Inspection", "text data")
Regenerated = namedtuple("Regenerated", "changed total")
Listed = namedtuple("Listed", "text data")
Switched = namedtuple("Switched", "text data")

GEN_KEYS = ("seed", "disabled_features", "disabled_maps")
NO_SECTION = "this sandbox has no generated section to change"
SECTION_STEP = 8

BASE_STATS = ("health", "energy", "age", "carried")
MAX_FAILURES = 5
MAX_LISTED = 6
MAX_KEY_TEXT = 24
MAX_TEXT_LINES = 900
MAX_FAILURE_TEXT = 120


class DevError(Exception):
    pass


def default_tile_units():
    from ..core.sim_context import TILE_UNITS

    return TILE_UNITS


def split_target(text):
    kind, separator, key = text.partition(":")

    if not separator:
        return ENTITY, text

    if kind not in KINDS:
        raise DevError(f"unknown kind '{kind[:32]}': use a blueprint name, item:<resource> or structure:<resource>")

    if not key:
        raise DevError(f"{kind}: needs a resource name")

    return KINDS[kind], key


def load_entity(name, folder=None):
    for path in json_files(ENTITY_DIR if folder is None else folder):
        if path.stem == name:
            try:
                return read_object(path)
            except ValueError as problem:
                raise DevError(f"blueprint '{name}': {problem}") from None

    return None


def load_resource(name, folder=None):
    for path in json_files(RESOURCE_DIR if folder is None else folder):
        try:
            data = read_object(path)
        except ValueError:
            continue

        if data.get("id", path.stem) == name:
            return data

    return None


def tile_at(world, x, y):
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (x, y)):
        raise DevError("the point must be two numbers")

    tile_x, tile_y = math.floor(x), math.floor(y)

    if not (0 <= tile_x < world.width and 0 <= tile_y < world.height):
        raise DevError(f"{tile_x},{tile_y} is outside the world ({world.width}x{world.height} tiles)")

    return tile_x, tile_y


def place_point(world, x, y, tile_units):
    tile_x, tile_y = tile_at(world, x, y)
    return tile_x, tile_y, (tile_x + 0.5) * tile_units, (tile_y + 0.5) * tile_units


def label_of(entity):
    return getattr(entity, "name", "") or getattr(entity, "sprite_id", "") or "entity"


def spawn_thing(sim, target, x, y, owner=None, tile_units=None, entity_dir=None, resource_dir=None, creators=None):
    kind, key = split_target(target)
    tile_units = default_tile_units() if tile_units is None else tile_units

    if kind == ENTITY:
        definition = load_entity(key, entity_dir)

        if definition is None:
            raise DevError(f"unknown blueprint '{key[:64]}'")
    else:
        resource = load_resource(key, resource_dir)

        if resource is None:
            raise DevError(f"unknown resource '{key[:64]}'")

        if kind not in resource:
            raise DevError(f"resource '{key}' has no {kind} form")

        function = creators.get(kind) if creators is not None else find_function(kind)

        if function is None:
            raise DevError(f"{kind}: spawning is not available yet")

    tile_x, tile_y, position_x, position_y = place_point(sim.world, x, y, tile_units)

    try:
        if kind == ENTITY:
            result = create_entity(sim, key, definition, position_x, position_y, owner)
        elif kind == ITEM:
            result = function(sim.systems.context, key, 1, position_x, position_y)
        else:
            result = function(sim.systems.context, key, position_x, position_y, owner)
    except Exception as problem:
        raise DevError(f"{target}: {type(problem).__name__}: {problem}") from None

    if result is None or isinstance(result, str):
        raise DevError(f"{target}: {result or 'nothing was created'}")

    return Spawned(result.id, target, tile_x, tile_y)


def delete_pixel(sim, pixel_id):
    entity = living_entity(sim, pixel_id)
    sim.entity_manager.kill(pixel_id)
    return Deleted(pixel_id, label_of(entity))


def living_entity(sim, pixel_id):
    try:
        entity = sim.entity_manager.get(pixel_id)
    except KeyError:
        entity = None

    if entity is None or not entity.alive:
        raise DevError(f"no entity #{pixel_id}")

    return entity


def wake_pixel(sim, pixel_id):
    entity = living_entity(sim, pixel_id)
    activity = getattr(getattr(sim, "systems", None), "activity", None)

    if activity is None:
        raise DevError("the activity system is not available")

    was_frozen = pixel_id in activity.frozen

    if was_frozen:
        activity.unfreeze(pixel_id)

    return Woke(pixel_id, label_of(entity), was_frozen)


def read_stat(entity, name):
    function = stats.resolve(name)

    try:
        if function is not None:
            value = function(entity)
        else:
            family, _, key = name.partition(":")

            if family != "status":
                return None

            value = sum(status.strength for status in entity.statuses if status.name == key)

        value = float(value)
    except Exception:
        return None

    return value if math.isfinite(value) else None


def stat_names(entity):
    names = list(BASE_STATS)

    for family, keys in (("need", entity.needs), ("need_value", entity.needs), ("inventory", entity.inventory), ("prop", entity.props), ("tag", entity.tags), ("status", {status.name for status in entity.statuses})):
        names += [f"{family}:{key}" for key in sorted(str(key) for key in keys)]

    return names


def number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".") if value % 1 else str(int(value))


def listing(values):
    shown = values[:MAX_LISTED]
    return ", ".join(shown) + (f" (+{len(values) - MAX_LISTED} more)" if len(values) > MAX_LISTED else "")


def failure_lines(entity):
    failures = entity.components.get("failures")

    if not isinstance(failures, (list, tuple)) or not failures:
        return None

    return [str(failure)[:MAX_FAILURE_TEXT] for failure in list(failures)[-MAX_FAILURES:]]


def inspect_pixel(sim, pixel_id, tile_units=None):
    entity = living_entity(sim, pixel_id)
    tile_units = default_tile_units() if tile_units is None else tile_units
    activity = getattr(getattr(sim, "systems", None), "activity", None)
    values = {}

    for name in stat_names(entity):
        value = read_stat(entity, name)

        if value is not None:
            values[name] = value

    task = entity.task
    task_info = None if task is None else {"name": str(getattr(task, "name", type(task).__name__)), "score": float(entity.task_score)}
    frozen = activity is not None and pixel_id in activity.frozen
    x, y = round(entity.position.x / tile_units, 2), round(entity.position.y / tile_units, 2)
    statuses = [{"name": status.name, "strength": float(status.strength), "left": max(0.0, float(status.duration - status.age))} for status in entity.statuses]
    data = {"id": pixel_id, "name": entity.name, "sprite": entity.sprite_id, "kind": entity.kind, "blueprint": entity.blueprint_name or "", "owner": entity.owner, "frozen": frozen, "x": x, "y": y, "stats": values, "task": task_info, "statuses": statuses}
    failures = failure_lines(entity)

    if failures is not None:
        data["failures"] = failures

    first = f"{label_of(entity)} #{pixel_id} at {number(x)},{number(y)}" + (f" - owner {entity.owner}" if entity.owner is not None else "") + (" - frozen" if frozen else "")
    lines = [first, f"health {number(values.get('health', 0.0) * 100)}% - energy {number(values.get('energy', 0.0) * 100)}% - age {number(values.get('age', 0.0))}s"]

    for title, family in (("needs", "need"), ("inventory", "inventory"), ("props", "prop"), ("status", "status")):
        found = [(name.partition(":")[2], value) for name, value in values.items() if name.partition(":")[0] == family]

        if found:
            lines.append(f"{title}: " + listing([f"{key[:MAX_KEY_TEXT]} {number(value)}" for key, value in found]))

    tags = sorted(str(tag) for tag in entity.tags)

    if tags:
        lines.append("tags: " + listing(tags))

    lines.append(f"task: {task_info['name']} (score {number(task_info['score'])})" if task_info else "task: none")

    if failures:
        lines.append("failed: " + "; ".join(failure[:60] for failure in failures[-3:]))

    text = "\n".join(lines)
    return Inspection(text if len(text) <= MAX_TEXT_LINES else text[: MAX_TEXT_LINES - 3] + "...", data)


def tiles_by_name():
    from ...world.tile_types import TILE_TYPES

    named = {}

    for tile in TILE_TYPES.values():
        named.setdefault(tile.name, tile)

    return named


def paint_tile(sim, name, x, y, tiles=None):
    tiles = tiles_by_name() if tiles is None else tiles
    tile = tiles.get(name)

    if tile is None:
        raise DevError(f"unknown tile '{name[:64]}'")

    tile_x, tile_y = tile_at(sim.world, x, y)
    before = sim.world.get_tile(tile_x, tile_y)
    changed = bool(sim.world.set_tile(tile_x, tile_y, tile))
    return Painted(tile.name, tile_x, tile_y, before.name, changed)


def catalog_text(names):
    lines = []

    for title in ("blueprints", "tiles", "resources"):
        values = names[title]
        lines.append(f"{title} ({len(values)}): " + (listing(values) if values else "none"))

    return "\n".join(lines)


def sandbox_gen(sim):
    gen = getattr(sim, "sandbox_gen", None)

    if not isinstance(gen, dict) or any(key not in gen for key in GEN_KEYS):
        raise DevError(NO_SECTION)

    seed, features, maps = (gen[key] for key in GEN_KEYS)

    if isinstance(seed, bool) or not isinstance(seed, int) or not isinstance(features, set) or not isinstance(maps, set):
        raise DevError(NO_SECTION)

    return gen


def section_names(sim):
    generator = getattr(sim, "generator", None)

    try:
        return sorted(generator.features.names()), sorted(generator.maps.map_type_names())
    except AttributeError:
        raise DevError(NO_SECTION) from None


def gen_data(sim, gen=None):
    gen = sandbox_gen(sim) if gen is None else gen
    features, maps = section_names(sim)
    return {"seed": gen["seed"], "features": {name: name not in gen["disabled_features"] for name in features}, "maps": {name: name not in gen["disabled_maps"] for name in maps}}


def switches(values):
    return ", ".join(f"{name} {'on' if state else 'off'}" for name, state in values.items()) or "none"


def regen_section(sim, generate=None, origin=None):
    gen = sandbox_gen(sim)

    if generate is None:
        from ...world.generator import generate_section as generate

    region = generate(sim.generation_settings, gen)
    left, top = region_origin() if origin is None else origin
    world = sim.world
    changed = 0

    for y in range(REGION_SIZE):
        for x in range(REGION_SIZE):
            tile = region.tiles[y][x]

            if world.get_tile(left + x, top + y) is not tile:
                world.set_tile(left + x, top + y, tile)
                changed += 1

    return Regenerated(changed, REGION_SIZE * REGION_SIZE)


def gen_listing(sim):
    data = gen_data(sim)
    text = "\n".join([f"section {REGION_SIZE}x{REGION_SIZE}, seed {data['seed']}", f"features: {switches(data['features'])}", f"maps: {switches(data['maps'])}"])
    return Listed(text, data)


def regenerate_or_restore(sim, restore, generate, origin):
    try:
        return regen_section(sim, generate, origin)
    except Exception:
        restore()
        raise


def set_switch(sim, kind, name, on, generate=None, origin=None):
    gen = sandbox_gen(sim)
    features, maps = section_names(sim)
    found = {value.lower(): value for value in (features if kind == "feature" else maps)}.get(name.lower())

    if found is None:
        raise DevError(f"unknown {kind} '{name[:64]}': /gen list shows them")

    disabled = gen["disabled_features" if kind == "feature" else "disabled_maps"]
    word = "on" if on else "off"

    if (found not in disabled) == on:
        return Switched(f"{kind} {found} is already {word}", {**gen_data(sim, gen), "action": kind, "name": found, "on": on, "changed": 0, "total": REGION_SIZE * REGION_SIZE})

    (disabled.discard if on else disabled.add)(found)
    done = regenerate_or_restore(sim, lambda: (disabled.add if on else disabled.discard)(found), generate, origin)
    return Switched(f"{kind} {found} {word}: {done.changed} of {done.total} tiles changed", {**gen_data(sim, gen), "action": kind, "name": found, "on": on, "changed": done.changed, "total": done.total})


def set_seed(sim, value, generate=None, origin=None):
    gen = sandbox_gen(sim)

    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_SEED:
        raise DevError(f"the seed must be a whole number from 0 to {MAX_SEED}")

    before = gen["seed"]

    if value == before:
        return Switched(f"the section seed is already {value}", {**gen_data(sim, gen), "action": "seed", "changed": 0, "total": REGION_SIZE * REGION_SIZE})

    gen["seed"] = value
    done = regenerate_or_restore(sim, lambda: gen.__setitem__("seed", before), generate, origin)
    return Switched(f"section seed {value}: {done.changed} of {done.total} tiles changed", {**gen_data(sim, gen), "action": "seed", "changed": done.changed, "total": done.total})


def section_points(tile_units=None, step=SECTION_STEP):
    units = default_tile_units() if tile_units is None else tile_units
    left, top = region_origin()
    return [((left + dx + 0.5) * units, (top + dy + 0.5) * units) for dy in range(0, REGION_SIZE, step) for dx in range(0, REGION_SIZE, step)]