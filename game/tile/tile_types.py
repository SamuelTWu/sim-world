import importlib
import pkgutil

from .tile import Tile
from . import tiles


def load_tiles() -> dict[str, Tile]:
    tile_types = {}

    for module_info in pkgutil.iter_modules(tiles.__path__):
        module = importlib.import_module(f"{tiles.__name__}.{module_info.name}")

        for value in vars(module).values():
            if isinstance(value, Tile):
                tile_types[value.name.lower()] = value

    return tile_types


TILE_TYPES = load_tiles()
