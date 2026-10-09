import pygame

from . import theme

CACHE_LIMIT = 800


class Painter:
    """Draws text with cached fonts and cached rendered text. Shared by everything in the GUI."""

    def __init__(self):
        self.fonts = {}
        self.images = {}

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = pygame.font.Font(None, size)

        return self.fonts[size]

    def measure(self, text, size):
        return self.font(size).size(text)

    def image(self, text, size, color):
        key = (text, size, color)

        if key not in self.images:
            if len(self.images) > CACHE_LIMIT:
                self.images.clear()

            self.images[key] = self.font(size).render(text, True, color)

        return self.images[key]

    def fit(self, text, size, width):
        if self.measure(text, size)[0] <= width:
            return text

        while text and self.measure(text + "...", size)[0] > width:
            text = text[:-1]

        return text + "..."

    def wrap(self, text, size, width):
        lines, line = [], ""

        for word in text.split():
            candidate = f"{line} {word}".strip()

            if line and self.measure(candidate, size)[0] > width:
                lines.append(line)
                line = word
            else:
                line = candidate

        return lines + [line] if line else lines

    def text(self, surface, text, pos, size=22, color=theme.TEXT, max_width=None, center=False):
        """Draws text at pos (its top-left, or its center). Returns the text's height."""
        if max_width is not None:
            text = self.fit(text, size, max_width)

        image = self.image(text, size, color)
        x, y = pos

        if center:
            x, y = x - image.get_width() // 2, y - image.get_height() // 2

        surface.blit(image, (x, y))
        return image.get_height()


def draw_button(surface, painter, rect, label, hovered=False, active=False, enabled=True, size=26):
    if not enabled:
        fill, border, color = theme.PANEL, theme.PANEL_LIGHT, theme.DISABLED
    elif active:
        fill, border, color = theme.mix(theme.ACCENT, theme.PANEL, 0.45), theme.ACCENT, theme.TEXT
    else:
        fill, border, color = (theme.PANEL_LIGHT if hovered else theme.PANEL), (theme.ACCENT if hovered else theme.BORDER), theme.TEXT

    pygame.draw.rect(surface, fill, rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, width=2, border_radius=8)
    painter.text(surface, label, rect.center, size=size, color=color, max_width=rect.width - 12, center=True)