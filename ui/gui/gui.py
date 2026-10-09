import pygame

from .bar import Bar
from .blueprints.blueprint_panel import BlueprintSidebar
from .blueprints.blueprints import load_blueprints, summary
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
    button again closes it, the last one clicked is drawn in front, and they stay above the bar and left of the
    sidebar. The Blueprints button is not a window: it expands the bar into a tray of saved blueprints, and
    picking one opens the sidebar on the right with its attributes.

    Esc closes things from the top: a window, then the sidebar, then the tray, and only then opens the menu.
    """

    def __init__(self, blueprint_folder=None):
        self.painter = Painter()
        self.bar = Bar()
        self.sidebar = BlueprintSidebar()
        self.blueprint_folder = blueprint_folder
        self.blueprints = {}
        self.scale = 1.0
        self.windows = {}

        for name in WINDOWS:
            self.bar.handlers[name] = lambda name=name: self.toggle(name)

        self.bar.handlers["blueprints"] = self.toggle_blueprints
        self.bar.on_select = self.select_blueprint

    def area(self):
        width, height = pygame.display.get_surface().get_size()
        self.scale = max(MIN_SCALE, min(MAX_SCALE, min(width / REFERENCE_SIZE[0], height / REFERENCE_SIZE[1])))
        self.bar.scale = self.sidebar.scale = self.scale
        self.bar.active = set(self.windows) | ({"blueprints"} if self.bar.expanded else set())
        return pygame.Rect(0, 0, width, height)

    def play_area(self, area):
        """The part of the screen windows live in: above the bar and left of the sidebar."""
        side = self.sidebar.width(area) if self.sidebar.is_open else 0
        return pygame.Rect(area.x, area.y, area.width - side, area.height - self.bar.rect(area).height)

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

    def toggle_blueprints(self):
        if self.bar.expanded:
            self.collapse_blueprints()
            return

        self.load_blueprints()
        self.bar.expanded = True
        self.bar.tray_scroll = 0

    def load_blueprints(self):
        blueprints, problems = load_blueprints(self.blueprint_folder)
        self.blueprints = {blueprint.id: blueprint for blueprint in blueprints}
        self.bar.cards = [{"id": blueprint.id, "name": blueprint.name, "sub": blueprint.kind, "color": blueprint.color, "summary": summary(blueprint)} for blueprint in blueprints]
        self.bar.empty_text = "No saved blueprints yet." if not problems else problems[0]

        if self.bar.selected not in self.blueprints:
            self.close_sidebar()

    def collapse_blueprints(self):
        self.close_sidebar()
        self.bar.expanded = False
        self.bar.pressed = None

    def select_blueprint(self, blueprint_id):
        if blueprint_id == self.bar.selected:
            self.close_sidebar()
            return

        if blueprint_id in self.blueprints:
            self.bar.selected = blueprint_id
            self.sidebar.show(self.blueprints[blueprint_id])

    def close_sidebar(self):
        self.bar.selected = None
        self.sidebar.close()

    def reset(self):
        """Closes everything (used when leaving a game)."""
        for name in list(self.windows):
            self.close(name)

        self.collapse_blueprints()

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

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.windows:
                self.close(next(reversed(self.windows)))
                return True

            if self.sidebar.is_open:
                self.close_sidebar()
                return True

            if self.bar.expanded:
                self.collapse_blueprints()
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

        if not used:
            used = self.sidebar.handle_event(event, area, self.bar.rect(area).y, self.painter)

            if self.sidebar.close_requested:
                self.sidebar.close_requested = False
                self.close_sidebar()

        return used or self.bar.handle_event(event, area)

    def draw(self, surface):
        area = self.area()
        self.sync(area)
        self.bar.draw(surface, self.painter, area)

        for window in self.windows.values():
            window.draw(surface, self.painter)

        self.sidebar.draw(surface, self.painter, area, self.bar.rect(area).y)