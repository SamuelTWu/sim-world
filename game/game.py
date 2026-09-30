import random
import pygame

from .rendering.renderer import Renderer
from .world.generator import WorldGenerator, GenerationSettings
from .entity.entityManager import EntityManager
from .entity.entity_systems.systemRunner import SystemRunner
from .entity.entity import Vec3

#CHANGE THIS TO AN ACTIONS MANAGER
from .entity.actions.wander import register_wander
from .entity.actions.build import register_build
from .entity.actions.reactions import register_reactions


class Game:
    def __init__(self):
        self.running = True

        self.generation_settings = GenerationSettings(
            width=100, 
            height=100, 
            seed=None, 
            debug=True, 
            tag_modifiers={"all":{"scale": 1}}
            )

        self.generator = WorldGenerator(self.generation_settings)
        self.world = None

        self.entity_manager = EntityManager()
        self.systems = None

        self.renderer = Renderer(
            width=1400,
            height=900,
        )

    def start_new_game(self, seed=None):
        if seed is not None:
            self.generation_settings.seed = seed

        self.generator = WorldGenerator(self.generation_settings)
        self.world = self.generator.generate()
        self.entity_manager = EntityManager()

        self.systems = SystemRunner(self.world, self.entity_manager)
        #change this, to an actions register
        register_build(self.systems)
        #register_wander(self.systems)
        
        register_reactions(self.systems)

        ant = self.entity_manager.spawn("ant")
        ant.position = Vec3(random.uniform(0, self.generation_settings.width), random.uniform(0, self.generation_settings.height), 0.0)

        tile_x, tile_y = int(ant.position.x // 32), int(ant.position.y // 32)
        ant.components["blueprint"] = [(tile_x + i, tile_y, "stone_brick") for i in range(5)]
        self.systems.initialize()

    def update(self, delta_time):
        if self.world is not None:
            self.systems.update(delta_time)
            self.world.update(delta_time)

    def run(self):
        

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
                self.renderer.render(
                    self.world,
                    self.generator.maps,
                    self.generator.features,
                    self.entity_manager.all(),
                )

        self.renderer.close()
