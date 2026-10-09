import pygame

from .bar import Bar
from .tech.tech_window import TechWindow
from .widgets import Painter

REFERENCE_SIZE = (1800, 1000)
MIN_SCALE = 0.7
MAX_SCALE = 2.0

WINDOWS = {"tech": TechWindow}


class Gui:
    """Everything drawn on top of the world. The renderer calls handle_event() before the camera and draw() last.

    `scale` follows the window: 1.0 at the reference size, smaller in a small window, larger when fullscreen on a
    big display. Anything new in the GUI should size itself with `gui.px(value)` instead of fixed pixels.

    Windows are opened by name from the bar (see WINDOWS). Each name has at most one window; clicking its bar
    button again closes it, Esc closes the top window, and the last one clicked is drawn in front.
    """

    def __init__(self):
        self.painter = Painter()
        self.bar = Bar()
        self.scale = 1.0
        self.windows = {}

        for name in WINDOWS:
            self.bar.handlers[name] = lambda name=name: self.toggle(name)

    def area(self):
        width, height = pygame.display.get_surface().get_size()
        self.scale = max(MIN_SCALE, min(MAX_SCALE, min(width / REFERENCE_SIZE[0], height / REFERENCE_SIZE[1])))
        self.bar.scale = self.scale
        self.bar.active = set(self.windows)
        return pygame.Rect(0, 0, width, height)

    def play_area(self, area):
        """The part of the screen above the bar, where windows live."""
        return pygame.Rect(area.x, area.y, area.width, area.height - self.bar.rect(area).height)

    def px(self, value):
        return max(1, round(value * self.scale))

    def toggle(self, name):
        if name in self.windows:
            self.close(name)
            return

        window = WINDOWS[name]()
        window.scale = self.scale
        window.place(self.play_area(self.area()))
        self.windows[name] = window

    def close(self, name):
        window = self.windows.pop(name, None)

        if window is not None:
            window.reset_input()

    def reset(self):
        """Closes everything (used when leaving a game)."""
        for name in list(self.windows):
            self.close(name)

        self.bar.pressed = None

    def raise_window(self, name):
        self.windows[name] = self.windows.pop(name)

    def keep_inside(self, window, play):
        if window.rect.width > play.width or window.rect.height > play.height:
            window.place(play)
            return

        window.rect.x = max(play.x, min(play.right - window.rect.width, window.rect.x))
        window.rect.y = max(play.y, min(play.bottom - window.rect.height, window.rect.y))

    def sync(self, area):
        play = self.play_area(area)

        for window in self.windows.values():
            window.scale = self.scale
            self.keep_inside(window, play)

        return play

    def handle_event(self, event):
        """Returns True if the GUI used the event, so the camera (and the menu key) should not see it."""
        area = self.area()
        play = self.sync(area)

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.windows:
            self.close(next(reversed(self.windows)))
            return True

        used = False

        for name, window in reversed(list(self.windows.items())):
            if window.handle_event(event, play):
                if event.type == pygame.MOUSEBUTTONDOWN and name in self.windows:
                    self.raise_window(name)

                used = True
                break

        for name, window in list(self.windows.items()):
            if window.close_requested:
                self.close(name)

        return used or self.bar.handle_event(event, area)

    def draw(self, surface):
        area = self.area()
        self.sync(area)
        self.bar.draw(surface, self.painter, area)

        for window in self.windows.values():
            window.draw(surface, self.painter)