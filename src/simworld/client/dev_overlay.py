
import pygame

TAG_TEXT = "DEV"
TAG_COLOR = (255, 196, 64)
TAG_INK = (30, 24, 8)
LABEL_COLOR = (235, 235, 235)
LABEL_BACKGROUND = (0, 0, 0, 150)
MAX_CACHE = 512
TAG_INSET = 8
MIN_FONT_SIZE = 15
MAX_FONT_SIZE = 20
LABEL_GAP = 2


def entity_label(entity):
    return entity.name or entity.sprite_id


class DevOverlay:
    def __init__(self):
        self.font = None
        self.cache = {}
        self.font_size = MAX_FONT_SIZE
        self.used_labels = []

    def update_font(self, zoom):
        size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(MAX_FONT_SIZE * zoom)))
        if size != self.font_size:
            self.font_size = size
            self.font = pygame.font.Font(None, size)
            self.cache.clear()

    def label_image(self, text, max_width=180):
        key = (text, max_width)
        image = self.cache.get(key)

        if image is None:
            if self.font is None:
                pygame.font.init()
                self.font = pygame.font.Font(None, self.font_size)

            if len(self.cache) >= MAX_CACHE:
                self.cache.clear()

            lines = []
            line = ""

            for word in text.split():
                test_line = f"{line} {word}".strip()
                if line and self.font.size(test_line)[0] > max_width - 6:
                    lines.append(line)
                    line = word
                else:
                    line = test_line

            if line:
                lines.append(line)

            if not lines:
                lines = [""]

            line_height = self.font.get_linesize()
            width = min(max_width, max(self.font.size(line)[0] for line in lines) + 6)
            image = pygame.Surface((width, len(lines) * line_height + 2), pygame.SRCALPHA)
            image.fill(LABEL_BACKGROUND)

            for i, line in enumerate(lines):
                text_image = self.font.render(line, True, LABEL_COLOR)
                image.blit(text_image, (3, 1 + i * line_height))

            self.cache[key] = image

        return image

    def draw_label(self, surface, text, x, y, centered=False):
        width, height = surface.get_size()
        max_width = min(180, width)
        image = self.label_image(text, max_width)
        left = x - image.get_width() // 2 if centered else x
        rect = pygame.Rect(left, y, image.get_width(), image.get_height())

        if rect.right < 0 or rect.left > width or rect.bottom < 0 or rect.top > height:
            return False

        while any(rect.colliderect(other) for other in self.used_labels):
            rect.y += LABEL_GAP + 1
            if rect.bottom > height:
                return False

        surface.blit(image, rect.topleft)
        self.used_labels.append(rect)
        return True

    def draw_tag(self, surface):
        if self.font is None:
            pygame.font.init()
            self.font = pygame.font.Font(None, self.font_size)

        text = self.font.render(TAG_TEXT, True, TAG_INK)
        box = pygame.Rect(0, 0, text.get_width() + 12, text.get_height() + 6)
        box.topright = (surface.get_width() - TAG_INSET, TAG_INSET)
        pygame.draw.rect(surface, TAG_COLOR, box, border_radius=4)
        surface.blit(text, (box.x + 6, box.y + 3))

    def draw(self, surface, camera, labels, entities, tile_size):
        self.update_font(getattr(camera, "zoom", 1.0))
        self.used_labels.clear()

        for x, y, text in labels or ():
            sx, sy = camera.world_to_screen(x * tile_size, y * tile_size)
            self.draw_label(surface, text, int(sx) + 2, int(sy) + 2)

        for entity in entities or ():
            sx, sy = camera.world_to_screen(entity.position.x, entity.position.y)
            self.draw_label(surface, entity_label(entity), int(sx), int(sy) + 10, centered=True)

        self.draw_tag(surface)
