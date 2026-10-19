from .catalog import ENTITY, gallery_entries
from .layout import create_entity, default_tile_units

UNIT_BLUEPRINTS = ("commander", "runner")
UNITS_PER_PLAYER = 3
SPACING = 2
ROWS = 4
START_X = 2
START_Y = 1


def start_spots(player_index, count=UNITS_PER_PLAYER):
    column, row = divmod(player_index, ROWS)
    left = START_X + column * (count * SPACING + 2)
    return [(left + number * SPACING, START_Y + row * SPACING) for number in range(count)]


def pick_unit(entries):
    blueprints = {name: definition for kind, name, definition in entries if kind == ENTITY}

    for name in UNIT_BLUEPRINTS:
        if name in blueprints:
            return name, blueprints[name]

    return next(iter(blueprints.items()), (None, None))


def give_test_units(sim, player_id, entries=None, count=UNITS_PER_PLAYER, tile_units=None):
    slots = sim.__dict__.setdefault("dev_player_slots", {})

    if player_id in slots:
        return []

    entries = gallery_entries() if entries is None else entries
    tile_units = default_tile_units() if tile_units is None else tile_units
    name, definition = pick_unit(entries)
    index = len(slots)
    spots = start_spots(index, count)
    slots[player_id] = index

    if name is None:
        print(f"[sandbox] player {player_id} gets no test units: there is no entity blueprint", flush=True)
        return []

    if any(x >= sim.world.width or y >= sim.world.height for x, y in spots):
        print(f"[sandbox] player {player_id} gets no test units: the start area is full", flush=True)
        return []

    units = [create_entity(sim, name, definition, (x + 0.5) * tile_units, (y + 0.5) * tile_units, owner=player_id) for x, y in spots]
    print(f"[sandbox] player {player_id} gets {len(units)} test units from '{name}'", flush=True)
    return units