from dataclasses import dataclass, field
import random
import time

from .noise import pnoise2
from .world import World
from ..map.map_types import MapManager
from ..feature.featureManager import FeatureManager
from ..tile.tile_types import TILE_TYPES
from ..map.mapModifiers import MODIFIERS, resolve_modifiers, apply_post_modifiers


@dataclass
class GenerationSettings:
    width: int = 100
    height: int = 100
    seed: int | None = None
    debug: bool = False
    tag_modifiers: dict = field(default_factory=dict)


@dataclass
class GenerationContext:
    world: World
    maps: MapManager
    features: FeatureManager
    random: random.Random
    settings: GenerationSettings
    generator: object = None

    @property
    def tiles(self):
        return TILE_TYPES


class WorldGenerator:
    def __init__(self, settings: GenerationSettings | None = None):
        self.settings = settings or GenerationSettings()
        self.random = random.Random(self.settings.seed)

        self.noise_offset_x = self.random.uniform(-10000, 10000)
        self.noise_offset_y = self.random.uniform(-10000, 10000)

        self.modifiers = self._default_modifiers()

        self.maps = MapManager()
        self.features = FeatureManager()

    def generate(self) -> World:
        start = time.perf_counter()

        world = World(
            width=self.settings.width,
            height=self.settings.height,
            default_tile=self._get_default_tile(),
        )

        self.maps.generate_all(self, world.width, world.height)
        maps_done = time.perf_counter()

        context = GenerationContext(
            world=world,
            maps=self.maps,
            features=self.features,
            random=self.random,
            settings=self.settings,
            generator=self
        )

        self.features.generate_all(context)
        end = time.perf_counter()

        print(f"Generated {world.width}x{world.height} world in {end - start:.3f}s (maps {maps_done - start:.3f}s, features {end - maps_done:.3f}s)")

        return world

    def generate_map(self, map_object):
        start = time.perf_counter()

        self.modifiers = resolve_modifiers(map_object, self.settings.tag_modifiers)
        map_object.generate(self)
        apply_post_modifiers(map_object, self.modifiers)
        self.modifiers = self._default_modifiers()

        if self.settings.debug:
            print(f"  map '{map_object.name}': {time.perf_counter() - start:.3f}s")

    @staticmethod
    def _default_modifiers():
        return {name: default for name, (default, _) in MODIFIERS.items()}

    def _get_default_tile(self):
        for tile in TILE_TYPES.values():
            if tile.name == "default":
                return tile

        if not TILE_TYPES:
            raise ValueError("No tile types are available.")

        return next(iter(TILE_TYPES.values()))

    def noise(self, x: int, y: int, scale: float = 0.01, offset: float = 0) -> float:
        scale = scale / self.modifiers["scale"]
        offset = offset + self.modifiers["offset"]

        return pnoise2(
            x * scale + self.noise_offset_x + offset,
            y * scale + self.noise_offset_y + offset,
            octaves=2,
            persistence=0.5,
            lacunarity=2.0,
            repeatx=100000,
            repeaty=100000,
            base=self.settings.seed or 0,
        )