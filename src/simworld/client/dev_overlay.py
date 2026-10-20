import pygame

TAG_TEXT = "DEV"
TAG_COLOR = (255, 196, 64)
TAG_INK = (30, 24, 8)
LABEL_COLOR = (235, 235, 235)
LABEL_BACKGROUND = (0, 0, 0, 150)
MAX_CACHE = 512
TAG_INSET = 8


def entity_label(entity):
    return entity.name or entity.sprite_id


class DevOverlay:
    def __init__(self):
        self.font = None
        self.cache = {}

    def label_image(self, text):
        image = self.cache.get(text)

        if image is None:
            if self.font is None:
                pygame.font.init()
                self.font = pygame.font.Font(None, 18)

            if len(self.cache) >= MAX_CACHE:
                self.cache.clear()

            text_image = self.font.render(text, True, LABEL_COLOR)
            image = pygame.Surface((text_image.get_width() + 6, text_image.get_height() + 2), pygame.SRCALPHA)
            image.fill(LABEL_BACKGROUND)
            image.blit(text_image, (3, 1))
            self.cache[text] = image

        return image

    def draw_label(self, surface, text, x, y, centered=False):
        image = self.label_image(text)
        left = x - image.get_width() // 2 if centered else x
        width, height = surface.get_size()

        if left + image.get_width() < 0 or left > width or y + image.get_height() < 0 or y > height:
            return False

        surface.blit(image, (left, y))
        return True

    def draw_tag(self, surface):
        if self.font is None:
            pygame.font.init()
            self.font = pygame.font.Font(None, 18)

        text = self.font.render(TAG_TEXT, True, TAG_INK)
        box = pygame.Rect(0, 0, text.get_width() + 12, text.get_height() + 6)
        box.topright = (surface.get_width() - TAG_INSET, TAG_INSET)
        pygame.draw.rect(surface, TAG_COLOR, box, border_radius=4)
        surface.blit(text, (box.x + 6, box.y + 3))

    def draw(self, surface, camera, labels, entities, tile_size):
        for x, y, text in labels or ():
            sx, sy = camera.world_to_screen(x * tile_size, y * tile_size)
            self.draw_label(surface, text, int(sx) + 2, int(sy) + 2)

        for entity in entities or ():
            sx, sy = camera.world_to_screen(entity.position.x, entity.position.y)
            self.draw_label(surface, entity_label(entity), int(sx), int(sy) + 10, centered=True)

        self.draw_tag(surface)