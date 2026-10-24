"""Headless simulation: no pygame, no renderer, no camera.

The server will run this directly. Single player will run it behind a local server.
Anything that draws or reads input belongs in game.py / the client, not here.
"""
import random

from ..world.generator import WorldGenerator, GenerationSettings
from .entities.entity_manager import EntityManager
from .behaviors.behavior_manager import BehaviorManager
from .core.system_runner import SystemRunner
from .core.sim_context import TILE_UNITS
from .entities.entity import Vec3

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
            tag_modifiers={"all": {"scale": 1.5}},
        )

        # None = pick a new random seed on every new game.
        # An explicit seed passed to start_new_game() sticks until changed.
        self.configured_seed = self.generation_settings.seed
        self.seed = None
        self.rng = None  # created in start_new_game, seeded from self.seed
        self.tick = 0    # number of steps since the game started
        self.sandbox = False #set da sandy boxy mody
        self.sandbox_gen = None
        
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

        self.systems.context.spawn = self.create_pixel
        self.world.on_tile_change = self.systems.activity.tile_changed  # a changed tile wakes the sleeping pixels around it (9.3)

    def spawn_pixel(self, definition, owner, x, y):
        """Create a pixel from a blueprint definition at (x, y) for an owner (a player id, or None) and record who owns it.

        The one way a pixel is created during play: `place` (the player) and the `spawn` behavior (a pixel) both use it.
        """
        pixel = self.systems.spawn_blueprint(definition, owner)
        pixel.position = Vec3(x, y, 0.0)
        self.systems.context.proximity.invalidate()  # the pixel is at its place now: the next near() sees it (9.7)

        if not self.entity_manager.roster.visits(pixel):
            self.systems.activity.moved(pixel)  # the loop never visits it, so it announces itself to the sleepers around it once, here

        if owner is not None:
            self.claim(owner, pixel)

        return pixel

    def create_pixel(self, definition, owner, x, y):
        limits = self.systems.limits
        limits.check_spawn(self.tick, owner, self.count_alive, self.count_owned)
        pixel = self.spawn_pixel(definition, owner, x, y)
        limits.note_spawn(owner)
        return pixel

    def count_alive(self):
        return sum(1 for pixel in self.entity_manager.all() if pixel.alive)

    def count_owned(self, player_id):
        total = 0

        for pixel_id in self.owned.get(player_id, ()):
            try:
                pixel = self.entity_manager.get(pixel_id)
            except KeyError:
                continue

            if pixel is not None and pixel.alive:
                total += 1

        return total

    def claim(self, player_id, pixel):
        self.owned.setdefault(player_id, []).append(pixel.id)

    def owned_ids(self, player_id):
        return list(self.owned.get(player_id, ()))

    def activity_anchors(self):
        """Where the pixels that players own are, (x, y) each: what decides which parts of the world get the full simulation (entity/system/activity.py).

        Only simulation state is used (not the cameras, not who is connected), so the same commands always give the same world.
        """
        anchors = []

        for ids in self.owned.values():
            for pixel_id in ids:
                try:
                    pixel = self.entity_manager.get(pixel_id)
                except KeyError:
                    continue

                if pixel is not None and pixel.alive:
                    anchors.append((pixel.position.x, pixel.position.y))

        return anchors

    def step(self):
        """Advance the simulation by exactly one fixed tick (TICK_DT seconds)."""
        if self.world is None:
            return
        self.systems.activity.refresh(self.activity_anchors())
        self.systems.update(TICK_DT)
        self.world.update(TICK_DT)
        self.tick += 1