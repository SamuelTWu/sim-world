import os
import pygame


class EntityRenderer:
    SPRITE_DIR = "sprite"

    def __init__(self, screen, camera):
        self.screen = screen
        self.camera = camera
        self.scaled_images = {}
        self.glyphs = {}
        self.glyph_fonts = {}
        self.images = {}

    def render_entities(self, entities):
        for entity in sorted(entities, key=lambda e: e.sprite.layer):
            self.render_entity(entity)

    def render_entity(self, entity):
        sprite = entity.sprite
        screen_x, screen_y = self.camera.world_to_screen(entity.position.x, entity.position.y)
        width = max(1, int(sprite.size[0] * self.camera.zoom))
        height = max(1, int(sprite.size[1] * self.camera.zoom))

        if sprite.image and self.draw_image(sprite.image, screen_x, screen_y, width, height):
            self.draw_owner_border(entity, screen_x, screen_y, width, height)
            return

        if sprite.shape:
            self.draw_shape(sprite.shape, sprite.color, screen_x, screen_y, width, height)
        elif sprite.character:
            self.draw_glyph(sprite.character, sprite.color, screen_x, screen_y, height)
        else:
            pygame.draw.rect(self.screen, sprite.color, (screen_x - width // 2, screen_y - height // 2, width, height))

        self.draw_owner_border(entity, screen_x, screen_y, width, height)

    def draw_owner_border(self, entity, x, y, width, height):
        owner = entity.props.get("owner")
        if not owner:
            return

        rect = pygame.Rect(x - width // 2 - 2, y - height // 2 - 2, width + 4, height + 4)
        pygame.draw.rect(self.screen, self.owner_color(owner), rect, width=2)

    @staticmethod
    def owner_color(owner):
        value = hash(owner)
        return 80 + (value & 127), 80 + ((value >> 8) & 127), 80 + ((value >> 16) & 127)

    def draw_shape(self, shape, color, x, y, width, height):
        polygons = shape if isinstance(shape[0][0], (list, tuple)) else [shape]

        for polygon in polygons:
            points = [(x + px * width, y + py * height) for px, py in polygon]
            pygame.draw.polygon(self.screen, color, points)

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

    def load_image(self, name):
        if name not in self.images:
            try:
                self.images[name] = pygame.image.load(os.path.join(self.SPRITE_DIR, name)).convert_alpha()
            except (pygame.error, FileNotFoundError):
                self.images[name] = None

        return self.images[name]

    def draw_glyph(self, character, color, x, y, height):
        key = (character, tuple(color), height)

        if key not in self.glyphs:
            font = self.glyph_fonts.setdefault(height, pygame.font.Font(None, height))
            self.trim_cache(self.glyphs)
            self.glyphs[key] = font.render(character, True, color)

        surface = self.glyphs[key]
        self.screen.blit(surface, (x - surface.get_width() // 2, y - surface.get_height() // 2))

    @staticmethod
    def trim_cache(cache, limit=512):
        if len(cache) >= limit:
            cache.clear()
