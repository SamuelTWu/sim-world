import math
from collections import namedtuple

from .catalog import ENTITY, ENTITY_DIR, ITEM, RESOURCE_DIR, STRUCTURE, json_files, read_object
from .layout import create_entity, find_function

KINDS = {"item": ITEM, "structure": STRUCTURE}

Spawned = namedtuple("Spawned", "id label tile_x tile_y")
Deleted = namedtuple("Deleted", "id label")


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


def place_point(world, x, y, tile_units):
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (x, y)):
        raise DevError("the point must be two numbers")

    tile_x, tile_y = math.floor(x), math.floor(y)

    if not (0 <= tile_x < world.width and 0 <= tile_y < world.height):
        raise DevError(f"{tile_x},{tile_y} is outside the world ({world.width}x{world.height} tiles)")

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
    manager = sim.entity_manager

    try:
        entity = manager.get(pixel_id)
    except KeyError:
        entity = None

    if entity is None or not entity.alive:
        raise DevError(f"no entity #{pixel_id}")

    manager.kill(pixel_id)
    return Deleted(pixel_id, label_of(entity))