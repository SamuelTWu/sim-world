"""Headless simulation: no pygame, no renderer, no camera.

The server will run this directly. Single player will run it behind a local server.
Anything that draws or reads input belongs in game.py / the client, not here.
"""
import random

from .world.generator import WorldGenerator, GenerationSettings
from .entity.entityManager import EntityManager
from .entity.behavior.behaviorManager import BehaviorManager
from .entity.system.systemRunner import SystemRunner
from .entity.system.simContext import TILE_UNITS
from .entity.entity import Vec3

# The simulation ALWAYS advances in fixed steps of TICK_DT seconds.
# Rendering FPS, lag spikes, and network timing never change this.
TICK_RATE = 20              # steps per second
TICK_DT = 1.0 / TICK_RATE   # 0.05s


class Simulation:
    def __init__(self, generation_settings=None):
        self.generation_settings = generation_settings or GenerationSettings(
            width=500,
            height=500,
            seed=None,
            debug=True,
            tag_modifiers={"all": {"scale": 1.3}},
        )

        # None = pick a new random seed on every new game.
        # An explicit seed passed to start_new_game() sticks until changed.
        self.configured_seed = self.generation_settings.seed
        self.seed = None
        self.rng = None  # created in start_new_game, seeded from self.seed
        self.tick = 0    # number of steps since the game started
        self.owned = {}  # player id -> ids of the pixels that player placed (what the server sends back to that player)

        self.generator = WorldGenerator(self.generation_settings)
        self.world = None

        self.entity_manager = EntityManager()
        self.behavior_manager = BehaviorManager()
        self.systems = None

    def start_new_game(self, seed=None):
        if seed is not None:
            self.configured_seed = seed

        # Always resolve to a concrete seed so the server can send it to clients
        # and so the simulation RNG is seeded.
        self.seed = self.configured_seed
        if self.seed is None:
            self.seed = random.randrange(2**32)
        self.generation_settings.seed = self.seed
        self.rng = random.Random(self.seed)
        self.tick = 0
        self.owned = {}

        self.generator = WorldGenerator(self.generation_settings)
        self.world = self.generator.generate()
        self.world.finish_generation()
        self.entity_manager = EntityManager()

        self.systems = SystemRunner(
            self.world, self.entity_manager, self.behavior_manager, maps=self.generator.maps, rng=self.rng
        )

        self._spawn_starting_pixels()

    def _spawn_starting_pixels(self):
        factory = self.entity_manager.entity_factory
        water = factory.load_definition("pixel_swimmer")
        grass = factory.load_definition("pixel_runner")

        w, h = self.world.width, self.world.height
        for _ in range(150):
            pixel = self.systems.spawn_blueprint(water)
            pixel.position = Vec3(
                self.rng.randint(2, int(w / 2)) * TILE_UNITS,
                self.rng.randint(2, h - 2) * TILE_UNITS,
                0.0,
            )

            pixel = self.systems.spawn_blueprint(grass)
            pixel.position = Vec3(
                self.rng.randint(int(w / 2), int(w) - 1) * TILE_UNITS,
                self.rng.randint(2, h - 2) * TILE_UNITS,
                0.0,
            )

    def claim(self, player_id, pixel):
        self.owned.setdefault(player_id, []).append(pixel.id)

    def owned_ids(self, player_id):
        return list(self.owned.get(player_id, ()))

    def step(self):
        """Advance the simulation by exactly one fixed tick (TICK_DT seconds)."""
        if self.world is None:
            return
        self.systems.update(TICK_DT)
        self.world.update(TICK_DT)
        self.tick += 1