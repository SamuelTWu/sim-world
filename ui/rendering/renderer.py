import pygame

from .camera import Camera
from .world_renderer import WorldRenderer
from .entity_renderer import EntityRenderer


class Renderer:
    TILE_SIZE = 32

    def __init__(self, width: int, height: int):
        pygame.init()
        pygame.font.init()

        self.width = width
        self.height = height
        self.restart_requested = False
        self.menu_requested = False

        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Sim World")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 18)

        self.camera = Camera(width, height, self.TILE_SIZE)
        self.world_renderer = WorldRenderer(self.screen, self.camera, self.font, self.TILE_SIZE)
        self.entity_renderer = EntityRenderer(self.screen, self.camera)

        self.debug_map_index = -1
        self.debug_map_names = []
        self.debug_feature_index = -1
        self.debug_feature_names = []

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    self.debug_map_index += 1
                    if self.debug_map_index >= len(self.debug_map_names):
                        self.debug_map_index = -1
                elif event.key == pygame.K_b:
                    self.debug_feature_index += 1
                    if self.debug_feature_index >= len(self.debug_feature_names):
                        self.debug_feature_index = -1
                elif event.key == pygame.K_r:
                    self.restart_requested = True
                elif event.key == pygame.K_ESCAPE:
                    self.menu_requested = True

            self.camera.handle_event(event)

        return True

    def update(self, delta_time):
        self.camera.update(delta_time)

    def render(self, view):
        """Draw one frame from a View (see server/replica.py). This is the renderer's only source of game data."""
        world, maps, features, entities = view.world, view.maps, view.features, view.entities

        self.screen.fill((0, 0, 0))

        if maps:
            self.debug_map_names = maps.names()

        if features:
            self.debug_feature_names = features.names()

        if self.debug_map_index >= 0 and maps and self.debug_map_names:
            self.world_renderer.render_map(maps, self.debug_map_names[self.debug_map_index])
        elif self.debug_feature_index >= 0 and features and self.debug_feature_names:
            self.world_renderer.render_feature(world, features, self.debug_feature_names[self.debug_feature_index])
        else:
            self.world_renderer.render_world(world)

        if entities:
            self.entity_renderer.render_entities(entities)

        pygame.display.flip()

    def tick(self, fps=60):
        return self.clock.tick(fps) / 1000.0

    def close(self):
        pygame.quit()