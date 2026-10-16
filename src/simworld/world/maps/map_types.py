import importlib
import inspect
import pkgutil

from .map import Map

MAPS_PACKAGE = "...content.maps"


def load_map_types() -> dict[str, type[Map]]:
    map_types = {}
    package = importlib.import_module(MAPS_PACKAGE, __package__)

    for module_info in sorted(pkgutil.iter_modules(package.__path__), key=lambda info: info.name):
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Map) and obj is not Map and obj.__module__ == module.__name__:
                map_types[getattr(obj, "MAP_NAME", obj.__name__.lower()).lower()] = obj

    return map_types

class MapManager:
    def __init__(self):
        self.map_types = load_map_types()
        self.maps: dict[str, Map] = {}

    def get_map_type(self, name: str) -> type[Map]:
        return self.map_types[name.lower()]

    def has_map_type(self, name: str) -> bool:
        return name.lower() in self.map_types

    def all_map_types(self) -> list[type[Map]]:
        return list(self.map_types.values())

    def map_type_names(self) -> list[str]:
        return list(self.map_types.keys())

    def generate_all(self, generator, width: int, height: int) -> dict[str, Map]:
        self.maps.clear()
        for name, map_type in self.map_types.items():
            self.maps[name] = map_type(width, height)
            generator.generate_map(self.maps[name])
        return self.maps

    def generate(self, name: str, generator, width: int, height: int) -> Map:
        name = name.lower()
        if name not in self.map_types:
            raise KeyError(f"Unknown map type: {name}")
        self.maps[name] = self.map_types[name](width, height)
        generator.generate_map(self.maps[name])
        return self.maps[name]

    def get(self, name: str) -> Map:
        name = name.lower()
        if name not in self.maps:
            raise KeyError(f"Map '{name}' has not been generated.")
        return self.maps[name]

    def has(self, name: str) -> bool:
        return name.lower() in self.maps

    def all(self) -> list[Map]:
        return list(self.maps.values())

    def names(self) -> list[str]:
        return list(self.maps.keys())

    def __getitem__(self, name: str) -> Map:
        return self.get(name)

    def __contains__(self, name: str) -> bool:
        return name.lower() in self.maps


MAP_TYPES = load_map_types()