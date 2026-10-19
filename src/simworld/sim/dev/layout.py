from collections import namedtuple
from importlib import import_module
from importlib.util import resolve_name

from .catalog import ENTITY, ITEM, STRUCTURE, gallery_entries
from ...world.sandbox import ENTITY_CAPACITY, entity_slots

Gallery = namedtuple("Gallery", "placed skipped")

CREATOR_MODULES = {ITEM: ("..items.items", "make_item"), STRUCTURE: ("..structures.structures", "build_structure")}


def default_tile_units():
    from ..core.sim_context import TILE_UNITS

    return TILE_UNITS


def create_entity(sim, name, definition, x, y, owner=None):
    blueprint = {**definition, "name": definition.get("name", name)}
    blueprint.pop("owner", None)
    blueprint.setdefault("sprite_id", name)
    return sim.spawn_pixel(blueprint, owner, x, y)


def item_creator(function):
    return lambda sim, name, definition, x, y: function(sim.systems.context, definition["resource"], definition["amount"], x, y)


def structure_creator(function):
    return lambda sim, name, definition, x, y: function(sim.systems.context, definition["resource"], x, y, None)


def find_function(kind):
    module_name, function_name = CREATOR_MODULES[kind]
    absolute = resolve_name(module_name, __package__)

    try:
        module = import_module(absolute)
    except ModuleNotFoundError as problem:
        if problem.name is not None and (absolute == problem.name or absolute.startswith(problem.name + ".")):
            return None

        raise

    return getattr(module, function_name, None)


def resolve_creators():
    creators = {ENTITY: create_entity}
    item = find_function(ITEM)
    structure = find_function(STRUCTURE)

    if item is not None:
        creators[ITEM] = item_creator(item)

    if structure is not None:
        creators[STRUCTURE] = structure_creator(structure)

    return creators


def build_sandbox_entities(sim, entries=None, creators=None, tile_units=None):
    entries = gallery_entries() if entries is None else entries
    creators = resolve_creators() if creators is None else creators
    tile_units = default_tile_units() if tile_units is None else tile_units
    slots = entity_slots()
    placed, skipped = [], []
    used = 0

    for kind, name, definition in entries:
        create = creators.get(kind)

        if create is None:
            skipped.append((kind, name, f"{kind} entries are not available yet"))
            continue

        if used >= min(len(slots), ENTITY_CAPACITY):
            skipped.append((kind, name, f"the gallery is full ({ENTITY_CAPACITY} slots)"))
            continue

        tile_x, tile_y = slots[used]

        try:
            result = create(sim, name, definition, (tile_x + 0.5) * tile_units, (tile_y + 0.5) * tile_units)
        except Exception as problem:
            result = f"{type(problem).__name__}: {problem}"

        if result is None or isinstance(result, str):
            skipped.append((kind, name, result or "nothing was created"))
            continue

        used += 1
        placed.append((kind, name, result, tile_x, tile_y))
        sim.world.labels.append((tile_x, tile_y, f"{kind} {name}"))

    print(f"[sandbox] gallery: {len(placed)} placed, {len(skipped)} skipped", flush=True)

    for kind, name, reason in skipped:
        print(f"[sandbox] skipped {kind} {name}: {reason}", flush=True)

    return Gallery(placed, skipped)