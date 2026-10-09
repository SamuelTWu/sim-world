import pygame

from .camera import Camera
from .world_renderer import WorldRenderer
from .entity_renderer import EntityRenderer
from ..gui.gui import Gui


MIN_SIZE = (640, 400)
RESIZE_EVENTS = tuple(getattr(pygame, name) for name in ("VIDEORESIZE", "WINDOWRESIZED", "WINDOWSIZECHANGED") if hasattr(pygame, name))


class Renderer:
    TILE_SIZE = 32

    def __init__(self, width: int, height: int):
        pygame.init()
        pygame.font.init()

        self.width = width
        self.height = height
        self.restart_requested = False
        self.menu_requested = False

        self.fullscreen = False
        self.windowed_size = self.fit_to_desktop(width, height)
        self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.width, self.height = self.screen.get_size()
        pygame.display.set_caption("Sim World")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 18)

        self.camera = Camera(self.width, self.height, self.TILE_SIZE)
        self.world_renderer = WorldRenderer(self.screen, self.camera, self.font, self.TILE_SIZE)
        self.entity_renderer = EntityRenderer(self.screen, self.camera)

        self.gui = Gui()

        self.debug_map_index = -1
        self.debug_map_names = []
        self.debug_feature_index = -1
        self.debug_feature_names = []

    @staticmethod
    def fit_to_desktop(width, height):
        """A window larger than the desktop would hang off the screen, so shrink it to about 90% of the desktop."""
        try:
            desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        except (AttributeError, pygame.error, IndexError):
            return width, height

        return min(width, int(desktop_w * 0.9)), min(height, int(desktop_h * 0.9))

    def toggle_fullscreen(self):
        """F11 / Alt+Enter. Fullscreen covers everything at the desktop's size; toggling back restores the old window."""
        self.fullscreen = not self.fullscreen

        if self.fullscreen:
            self.windowed_size = (self.width, self.height)
            self.apply_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.apply_mode(self.windowed_size, pygame.RESIZABLE)

    def apply_mode(self, size, flags):
        self.screen = pygame.display.set_mode(size, flags)
        self.resized()

    def resized(self):
        """Call after the window changes size. Re-reads the real size and tells everything that draws to the screen."""
        self.screen = pygame.display.get_surface()
        self.width, self.height = self.screen.get_size()

        if not self.fullscreen and (self.width < MIN_SIZE[0] or self.height < MIN_SIZE[1]):
            self.screen = pygame.display.set_mode((max(self.width, MIN_SIZE[0]), max(self.height, MIN_SIZE[1])), pygame.RESIZABLE)
            self.width, self.height = self.screen.get_size()

        for part in (self.world_renderer, self.entity_renderer):
            if hasattr(part, "screen"):
                part.screen = self.screen

        if hasattr(self.camera, "resize"):
            self.camera.resize(self.width, self.height)
        else:
            for name, value in (("width", self.width), ("height", self.height), ("screen_width", self.width), ("screen_height", self.height), ("viewport_width", self.width), ("viewport_height", self.height)):
                if hasattr(self.camera, name):
                    setattr(self.camera, name, value)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type in RESIZE_EVENTS:
                self.resized()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11 or (event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT):
                    self.toggle_fullscreen()
                    continue

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

            if self.gui.handle_event(event):
                continue

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

        self.gui.draw(self.screen)
        pygame.display.flip()

    def tick(self, fps=60):
        return self.clock.tick(fps) / 1000.0

    def close(self):
        pygame.quit()