import pygame
import os
from .camera import Camera
from ..world.world import World


class Renderer:
    TILE_SIZE = 32
    SPRITE_DIR = "sprite"

    def __init__(self, width: int, height: int):
        pygame.init()
        pygame.font.init()
        self.restart_requested = False
        self.world_surface = None
        self.cached_world = None
        self.scaled_images = {}
        self.glyphs = {}
        self.glyph_fonts = {}

        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Sim World")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 18)

        self.camera = Camera(width, height, self.TILE_SIZE)

        self.debug_map_index = -1
        self.debug_map_names = []

        self.debug_feature_index = -1
        self.debug_feature_names = []
        self.debug_feature_colors = {}

        self.images = {}

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    self.debug_map_index += 1
                    if self.debug_map_index >= len(self.debug_map_names):
                        self.debug_map_index = -1

                if event.key == pygame.K_b:
                    self.debug_feature_index += 1
                    if self.debug_feature_index >= len(self.debug_feature_names):
                        self.debug_feature_index = -1
                        
                if event.key == pygame.K_r:
                    self.restart_requested = True

            self.camera.handle_event(event)

        return True

    def update(self, delta_time):
        self.camera.update(delta_time)

    def render(self, world, maps=None, features=None, entities=None):
        self.screen.fill((0, 0, 0))

        if maps:
            self.debug_map_names = maps.names()

        if features:
            self.update_feature_names(features)

        if self.debug_map_index >= 0 and maps and self.debug_map_names:
            self.render_map(maps)
        elif self.debug_feature_index >= 0 and features and self.debug_feature_names:
            self.render_feature(world, features)
        else:
            self.render_world(world)

        if entities:
            self.render_entities(entities)

        pygame.display.flip()

    def build_world_surface(self, world):
        surface = pygame.Surface((world.width, world.height))

        for y in range(world.height):
            for x in range(world.width):
                tile = world.get_tile(x, y)
                surface.set_at((x, y), tile.color if tile else (0, 0, 0))

        return surface

    def render_world(self, world):
        if self.cached_world is not world:
            self.world_surface = self.build_world_surface(world)
            self.cached_world = world

        min_x, max_x, min_y, max_y = self.camera.get_visible_tile_bounds(world)
        min_x, min_y, max_x, max_y = max(0, min_x), max(0, min_y), min(world.width - 1, max_x), min(world.height - 1, max_y)

        if max_x >= min_x and max_y >= min_y:
            columns, rows = max_x - min_x + 1, max_y - min_y + 1
            tile_size = self.camera.scaled_tile_size
            scaled = pygame.transform.scale(self.world_surface.subsurface((min_x, min_y, columns, rows)), (max(1, round(columns * tile_size)), max(1, round(rows * tile_size))))
            self.screen.blit(scaled, self.camera.world_to_screen(min_x * self.TILE_SIZE, min_y * self.TILE_SIZE))

        self.camera.draw_hovered_tile_name(self.screen, world, self.font)

    def render_feature(self, world, features):
        feature_name = self.debug_feature_names[self.debug_feature_index]
        feature = features.get(feature_name)
        debug_data = feature.get_debug_data()
        if not debug_data: 
                    return

        tile_size = self.camera.scaled_tile_size
        min_x, max_x, min_y, max_y = self.camera.get_visible_tile_bounds(world)
        highlight_color = self.debug_feature_colors[feature_name]

        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                influence = min(1.0, debug_data[y][x])

                if influence <= 0:
                    color = (20, 20, 20)
                else:
                    color = tuple(
                        int(40 + (base - 40) * influence)
                        for base in highlight_color
                    )

                screen_x, screen_y = self.camera.world_to_screen(x * self.TILE_SIZE, y * self.TILE_SIZE)
                pygame.draw.rect(self.screen, color, (screen_x, screen_y, tile_size, tile_size))

        self.screen.blit(
            self.font.render(f"Feature: {feature_name}", True, (255, 255, 255)),
            (10, 10),
        )


    def render_entities(self, entities):
        for entity in sorted(entities, key=lambda e: e.sprite.layer):
            self.render_entity(entity)

    def render_entity(self, entity):
        sprite = entity.sprite
        screen_x, screen_y = self.camera.world_to_screen(entity.position.x, entity.position.y)
        width = max(1, int(sprite.size[0] * self.camera.zoom))
        height = max(1, int(sprite.size[1] * self.camera.zoom))

        if sprite.image and self.draw_image(sprite.image, screen_x, screen_y, width, height):
            return

        if sprite.shape:
            self.draw_shape(sprite.shape, sprite.color, screen_x, screen_y, width, height)
        elif sprite.character:
            self.draw_glyph(sprite.character, sprite.color, screen_x, screen_y, height)
        else:
            pygame.draw.rect(self.screen, sprite.color, (screen_x - width // 2, screen_y - height // 2, width, height))

    def draw_image(self, name, x, y, width, height):
        key = (name, width, height)

        if key not in self.scaled_images:
            image = self.load_image(name)

            if image is None:
                return False

            self.trim_cache(self.scaled_images)
            self.scaled_images[key] = pygame.transform.scale(image, (width, height))

        self.screen.blit(self.scaled_images[key], (x - width // 2, y - height // 2))

        return True

    def draw_shape(self, shape, color, x, y, width, height):
        polygons = shape if isinstance(shape[0][0], (list, tuple)) else [shape]

        for polygon in polygons:
            pygame.draw.polygon(self.screen, color, [(x + px * width, y + py * height) for px, py in polygon])

    def draw_glyph(self, character, color, x, y, height):
        key = (character, tuple(color), height)

        if key not in self.glyphs:
            font = self.glyph_fonts.setdefault(height, pygame.font.Font(None, height))
            self.trim_cache(self.glyphs)
            self.glyphs[key] = font.render(character, True, color)

        surface = self.glyphs[key]
        self.screen.blit(surface, (x - surface.get_width() // 2, y - surface.get_height() // 2))

    def load_image(self, name):
        if name not in self.images:
            try:
                self.images[name] = pygame.image.load(os.path.join(self.SPRITE_DIR, name)).convert_alpha()
            except (pygame.error, FileNotFoundError):
                self.images[name] = None

        return self.images[name]

    @staticmethod
    def trim_cache(cache, limit=512):
        if len(cache) >= limit:
            cache.clear()

    def render_map(self, maps):
        map_name = self.debug_map_names[self.debug_map_index]
        map_object = maps.get(map_name)
        min_x, max_x, min_y, max_y = self.camera.get_visible_tile_bounds(map_object)
        tile_size = self.camera.scaled_tile_size

        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                value = max(0.0, min(1.0, map_object.get(x, y)))
                color = int(value * 255)

                screen_x, screen_y = self.camera.world_to_screen(x * self.TILE_SIZE, y * self.TILE_SIZE)
                pygame.draw.rect(self.screen, (color, color, color), (screen_x, screen_y, tile_size, tile_size))

        self.screen.blit(self.font.render(f"Map: {map_name}", True, (255, 255, 255)), (10, 10))

    def update_feature_names(self, features):
        self.debug_feature_names = features.names()

        for name in self.debug_feature_names:
            if name not in self.debug_feature_colors:
                self.debug_feature_colors[name] = self.random_debug_color(name)

    def random_debug_color(self, name):
        value = hash(name)
        return (
            80 + (value & 127),
            80 + ((value >> 8) & 127),
            80 + ((value >> 16) & 127),
        )

    def tick(self, fps=60):
        return self.clock.tick(fps) / 1000.0

    def close(self):
        pygame.quit()
