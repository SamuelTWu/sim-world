import importlib
import inspect
import pkgutil

from .feature import Feature
from .feature_selection_strategy import BlendedSelection

FEATURES_PACKAGE = "...content.features"


def find_feature_modules(package) -> list[str]:
    names = []

    for info in pkgutil.iter_modules(package.__path__):
        name = f"{package.__name__}.{info.name}"

        if info.ispkg:
            names += find_feature_modules(importlib.import_module(name))
        else:
            names.append(name)

    return names

class FeatureManager:
    def __init__(self, selection_strategy=None):
        self.features = {}
        self.selection_strategy = selection_strategy or BlendedSelection()
        self._load_features()

    def _load_features(self):
        root = importlib.import_module(FEATURES_PACKAGE, __package__)

        for module_name in sorted(find_feature_modules(root), key=lambda name: name.rsplit(".", 1)[1]):
            module = importlib.import_module(module_name)

            for _, feature_class in inspect.getmembers(module, inspect.isclass):
                if feature_class is not Feature and issubclass(feature_class, Feature) and feature_class.__module__ == module.__name__:
                    self.register(feature_class())

    def register(self, feature: Feature):
        if feature.name in self.features:
            raise ValueError(f"Feature already registered: {feature.name}")

        self.features[feature.name] = feature

    def get(self, name: str) -> Feature:
        return self.features[name]

    def all(self):
        return self.features.values()

    def names(self):
        return list(self.features.keys())

    def generate_all(self, context):
        world = context.world
        debug = context.settings.debug
        features = list(self.features.values())
        world.feature_grid = [[None] * world.width for _ in range(world.height)]

        for feature in features:
            feature.initialize_generation(context)

        for y in range(world.height):
            for x in range(world.width):
                candidates = []

                for feature in features:
                    influence = feature.get_influence(context, x, y)

                    if debug:
                        feature.record_debug_data(x, y, influence)

                    if influence > 0:
                        candidates.append((feature, influence))

                if not candidates:
                    continue

                feature = self.selection_strategy.choose(candidates, context, x, y)

                if feature is None:
                    continue

                world.feature_grid[y][x] = feature.name
                tile = feature.generate_tile(context, x, y)

                if tile is not None:
                    world.set_tile(x, y, tile)