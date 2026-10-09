import pygame

from .bar import Bar
from .widgets import Painter

REFERENCE_SIZE = (1800, 1000)
MIN_SCALE = 0.7
MAX_SCALE = 2.0


class Gui:
    """Everything drawn on top of the world. The renderer calls handle_event() before the camera and draw() last.

    `scale` follows the window: 1.0 at the reference size, smaller in a small window, larger when fullscreen on a
    big display. Anything new in the GUI should size itself with `gui.px(value)` instead of fixed pixels.
    """

    def __init__(self):
        self.painter = Painter()
        self.bar = Bar()
        self.scale = 1.0

    def area(self):
        width, height = pygame.display.get_surface().get_size()
        self.scale = max(MIN_SCALE, min(MAX_SCALE, min(width / REFERENCE_SIZE[0], height / REFERENCE_SIZE[1])))
        self.bar.scale = self.scale
        return pygame.Rect(0, 0, width, height)

    def px(self, value):
        return max(1, round(value * self.scale))

    def handle_event(self, event):
        return self.bar.handle_event(event, self.area())

    def draw(self, surface):
        self.bar.draw(surface, self.painter, self.area())