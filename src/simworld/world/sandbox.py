import math
from dataclasses import dataclass

from .world import World
from .tile_types import TILE_TYPES

MIN_SIZE = 64
MARGIN = 8
BLOCK = 3
GAP = 2
PITCH = BLOCK + GAP
SECTION_GAP = 8
ENTITY_PITCH = 4
ENTITY_CAPACITY = 256
REGION_SIZE = 50
REGION_LABEL = "generated 50x50"


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    columns: int
    rows: int
    entity_top: int
    entity_columns: int
    entity_rows: int
    region_x: int = 0
    region_y: int = 0


def sorted_tiles():
    return [tile for _, tile in sorted(TILE_TYPES.items(), key=lambda item: (item[1].name, str(item[0])))]


def default_tile():
    for tile in TILE_TYPES.values():
        if tile.name == "default":
            return tile

    if not TILE_TYPES:
        raise ValueError("No tile types are available.")

    return next(iter(TILE_TYPES.values()))


def layout_for(tile_count):
    fits = (MIN_SIZE - 2 * MARGIN + GAP) // PITCH
    columns = max(math.ceil(math.sqrt(max(tile_count, 1))), fits)
    rows = max(math.ceil(tile_count / columns), 1)
    width = max(MIN_SIZE, 2 * MARGIN + columns * PITCH - GAP)
    entity_top = MARGIN + rows * PITCH - GAP + SECTION_GAP
    entity_columns = max((width - 2 * MARGIN) // ENTITY_PITCH, 1)
    entity_rows = math.ceil(ENTITY_CAPACITY / entity_columns)
    height = max(MIN_SIZE, entity_top + entity_rows * ENTITY_PITCH + MARGIN, 2 * MARGIN + REGION_SIZE)
    region_x = width + SECTION_GAP
    return Layout(region_x + REGION_SIZE + MARGIN, height, columns, rows, entity_top, entity_columns, entity_rows, region_x, MARGIN)


def tile_blocks(tiles=None):
    tiles = sorted_tiles() if tiles is None else tiles
    layout = layout_for(len(tiles))
    return [(tile, MARGIN + (index % layout.columns) * PITCH, MARGIN + (index // layout.columns) * PITCH) for index, tile in enumerate(tiles)]


def region_origin(tile_count=None):
    layout = layout_for(len(TILE_TYPES) if tile_count is None else tile_count)
    return layout.region_x, layout.region_y


def entity_slots(tile_count=None):
    layout = layout_for(len(TILE_TYPES) if tile_count is None else tile_count)
    return [(MARGIN + (index % layout.entity_columns) * ENTITY_PITCH + ENTITY_PITCH // 2, layout.entity_top + (index // layout.entity_columns) * ENTITY_PITCH + ENTITY_PITCH // 2) for index in range(ENTITY_CAPACITY)]


def generate_sandbox(settings, region=None):
    tiles = sorted_tiles()
    layout = layout_for(len(tiles))
    world = World(width=layout.width, height=layout.height, default_tile=default_tile())

    for tile, x0, y0 in tile_blocks(tiles):
        for y in range(y0, y0 + BLOCK):
            for x in range(x0, x0 + BLOCK):
                world.tiles[y][x] = tile

        world.labels.append((x0, y0, tile.name))

    if region is not None:
        if region.width != REGION_SIZE or region.height != REGION_SIZE:
            raise ValueError(f"The generated section must be {REGION_SIZE}x{REGION_SIZE}, got {region.width}x{region.height}")

        for y in range(REGION_SIZE):
            for x in range(REGION_SIZE):
                world.tiles[layout.region_y + y][layout.region_x + x] = region.tiles[y][x]

    world.labels.append((layout.region_x, layout.region_y, REGION_LABEL))

    return world