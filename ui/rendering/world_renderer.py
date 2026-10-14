import os
import pygame


class WorldRenderer:
    SPRITE_DIR = "ui/sprites"

    def __init__(self, screen, camera, font, tile_size):
        self.screen = screen
        self.camera = camera
        self.font = font
        self.TILE_SIZE = tile_size

        self.world_surface = None
        self.cached_world = None
        self.debug_feature_colors = {}
        self.images = {}
        self.scaled_images = {}

    def render_world(self, world):
        if self.cached_world is not world:
            self.world_surface = self.build_world_surface(world)
            self.cached_world = world

        min_x, max_x, min_y, max_y = self.camera.get_visible_tile_bounds(world)
        min_x, min_y = max(0, min_x), max(0, min_y)
        max_x, max_y = min(world.width - 1, max_x), min(world.height - 1, max_y)

        if max_x >= min_x and max_y >= min_y:
            columns, rows = max_x - min_x + 1, max_y - min_y + 1
            tile_size = self.camera.scaled_tile_size
            visible = self.world_surface.subsurface((min_x, min_y, columns, rows))
            scaled = pygame.transform.scale(visible, (max(1, round(columns * tile_size)), max(1, round(rows * tile_size))))
            self.screen.blit(scaled, self.camera.world_to_screen(min_x * self.TILE_SIZE, min_y * self.TILE_SIZE))

            for y in range(min_y, max_y + 1):
                for x in range(min_x, max_x + 1):
                    tile = world.get_tile(x, y)
                    if tile and getattr(tile, "sprite_id", None):
                        screen_x, screen_y = self.camera.world_to_screen(x * self.TILE_SIZE, y * self.TILE_SIZE)
                        self.draw_sprite(tile.sprite_id, screen_x, screen_y, tile_size)

        self.camera.draw_hovered_tile_name(self.screen, world, self.font)

    def build_world_surface(self, world):
        surface = pygame.Surface((world.width, world.height))

        for y in range(world.height):
            for x in range(world.width):
                tile = world.get_tile(x, y)
                surface.set_at((x, y), tile.color if tile else (0, 0, 0))

        return surface

    def draw_sprite(self, name, x, y, size):
        key = (name, size)

        if key not in self.scaled_images:
            image = self.load_image(name)
            if image is None:
                return False

            self.trim_cache(self.scaled_images)
            self.scaled_images[key] = pygame.transform.scale(image, (size, size))

        self.screen.blit(self.scaled_images[key], (x, y))
        return True

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

    def set_world_pixel(self, x, y, color):
        if self.world_surface is not None:
            self.world_surface.set_at((x, y), color)

    def render_feature(self, world, features, feature_name):
        feature = features.get(feature_name)
        debug_data = feature.get_debug_data()

        if not debug_data:
            return

        tile_size = self.camera.scaled_tile_size
        min_x, max_x, min_y, max_y = self.camera.get_visible_tile_bounds(world)
        min_x, max_x = max(0, min_x), min(world.width - 1, max_x)
        min_y, max_y = max(0, min_y), min(world.height - 1, max_y)
        highlight_color = self.get_feature_color(feature_name)

        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                influence = min(1.0, debug_data[y][x])
                color = (20, 20, 20) if influence <= 0 else tuple(int(40 + (base - 40) * influence) for base in highlight_color)
                screen_x, screen_y = self.camera.world_to_screen(x * self.TILE_SIZE, y * self.TILE_SIZE)
                pygame.draw.rect(self.screen, color, (screen_x, screen_y, tile_size, tile_size))

        self.screen.blit(self.font.render(f"Feature: {feature_name}", True, (255, 255, 255)), (10, 10))

    def render_map(self, maps, map_name):
        map_object = maps.get(map_name)
        min_x, max_x, min_y, max_y = self.camera.get_visible_tile_bounds(map_object)
        tile_size = self.camera.scaled_tile_size

        for y in range(max(0, min_y), min(map_object.height - 1, max_y) + 1):
            for x in range(max(0, min_x), min(map_object.width - 1, max_x) + 1):
                value = max(0.0, min(1.0, map_object.get(x, y)))
                color = int(value * 255)
                screen_x, screen_y = self.camera.world_to_screen(x * self.TILE_SIZE, y * self.TILE_SIZE)
                pygame.draw.rect(self.screen, (color, color, color), (screen_x, screen_y, tile_size, tile_size))

        self.screen.blit(self.font.render(f"Map: {map_name}", True, (255, 255, 255)), (10, 10))

    def get_feature_color(self, name):
        if name not in self.debug_feature_colors:
            self.debug_feature_colors[name] = self.random_color(name)
        return self.debug_feature_colors[name]

    @staticmethod
    def random_color(name):
        value = hash(name)
        return 80 + (value & 127), 80 + ((value >> 8) & 127), 80 + ((value >> 16) & 127)