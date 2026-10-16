import importlib
import pkgutil

from .tile import Tile
from ..content import tiles


def load_tiles() -> dict[str, Tile]:
    tile_types = {}
    module_names = [info.name for info in pkgutil.walk_packages(tiles.__path__, f"{tiles.__name__}.") if not info.ispkg]

    for module_name in sorted(module_names, key=lambda name: name.rsplit(".", 1)[1]):
        module = importlib.import_module(module_name)

        for value in vars(module).values():
            if isinstance(value, Tile):
                tile_types[value.name.lower()] = value

    return tile_types


TILE_TYPES = load_tiles()