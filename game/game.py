import random

from .rendering.renderer import Renderer
from .world.generator import WorldGenerator, GenerationSettings
from .entity.entityManager import EntityManager
from .entity.behavior.behaviorManager import BehaviorManager
from .entity.system.systemRunner import SystemRunner
from .entity.system.simContext import TILE_UNITS
from .entity.entity import Vec3


class Game:
    def __init__(self):
        self.running = True

        self.generation_settings = GenerationSettings(
            width=400, 
            height=400, 
            seed=None, 
            debug=True, 
            tag_modifiers={"all": {"scale": 1.6}}
            )

        self.generator = WorldGenerator(self.generation_settings)
        self.world = None

        self.entity_manager = EntityManager()
        self.behavior_manager = BehaviorManager()
        self.systems = None

        self.renderer = Renderer(width=1400, height=900)

    def start_new_game(self, seed=None):
        if seed is not None:
            self.generation_settings.seed = seed

        self.generator = WorldGenerator(self.generation_settings)
        self.world = self.generator.generate()
        self.entity_manager = EntityManager()

        self.systems = SystemRunner(self.world, self.entity_manager, self.behavior_manager)
        self.systems.events.on("tile_placed", self.on_tile_placed)

        blueprint = self.entity_manager.entity_factory.load_definition("pixel")
        for _ in range(20):
            pixel = self.systems.spawn_blueprint(blueprint)
            pixel.position = Vec3((random.randint(2, self.world.width - 2) + 0.5) * TILE_UNITS, (random.randint(2, self.world.height - 2) + 0.5) * TILE_UNITS, 0.0)

    def on_tile_placed(self, x, y, tile, **_):
        stored = self.world.get_tile(x, y)
        self.renderer.cached_world = None

    def update(self, delta_time):
        if self.world is not None:
            self.systems.update(delta_time)
            self.world.update(delta_time)

    def run(self):
        self.start_new_game()

        while self.running:
            delta_time = self.renderer.tick(60)

            self.running = self.renderer.handle_events()

            if not self.running:
                break

            if self.renderer.restart_requested:
                self.renderer.restart_requested = False
                self.start_new_game()

            self.update(delta_time)
            self.renderer.update(delta_time)

            if self.world is not None:
                self.renderer.render(self.world, self.generator.maps, self.generator.features, self.entity_manager.all())

        self.renderer.close()