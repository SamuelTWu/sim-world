import importlib
import inspect
import pkgutil

from . import features
from .feature import Feature
from .featureSelectionStrategy import BlendedSelection

class FeatureManager:
    def __init__(self, selection_strategy=None):
        self.features = {}
        self.selection_strategy = selection_strategy or BlendedSelection()
        self._load_features()

    def _load_features(self):
        for module_info in sorted(pkgutil.iter_modules(features.__path__)):
            module = importlib.import_module(f"{features.__name__}.{module_info.name}")

            for _, feature_class in inspect.getmembers(module, inspect.isclass):
                if feature_class is Feature or not issubclass(feature_class, Feature) or feature_class.__module__ != module.__name__:
                    continue

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