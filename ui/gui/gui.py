import time

import pygame

from . import theme
from .bar import Bar
from .blueprints.blueprint_panel import BlueprintSidebar
from .blueprints.blueprints import load_blueprints, summary
from .tech.tech_window import TechWindow
from .widgets import Painter

REFERENCE_SIZE = (1800, 1000)
MIN_SCALE = 0.7
MAX_SCALE = 2.0
DRAG_START = 8
NOTICE_SECONDS = 4.0

WINDOWS = {"tech": TechWindow}


class Gui:
    """Everything drawn on top of the world. The renderer calls handle_event() before the camera and draw() last.

    `scale` follows the window: 1.0 at the reference size, smaller in a small window, larger when fullscreen on a
    big display. Anything new in the GUI should size itself with `gui.px(value)` instead of fixed pixels.

    Windows are opened by name from the bar (see WINDOWS). Each name has at most one window; clicking its bar
    button again closes it, the last one clicked is drawn in front, and they stay above the bar and left of the
    sidebar. The Blueprints button is not a window: it expands the bar into a tray of saved blueprints, and
    picking one opens the sidebar on the right with its attributes.

    A card in the tray can be dragged out onto the map. Letting go over the map (not over the bar, the sidebar or
    a window) adds (blueprint id, screen position) to `drops`; the renderer turns that into a world position and
    the game sends the `place` command (the player creating a pixel; `spawn` is a pixel creating another). A short press on a card still selects it. Esc cancels a drag.

    Esc closes things from the top: a drag, a window, then the sidebar, then the tray, and only then opens the menu.
    """

    def __init__(self, blueprint_folder=None):
        self.painter = Painter()
        self.bar = Bar()
        self.sidebar = BlueprintSidebar()
        self.blueprint_folder = blueprint_folder
        self.blueprints = {}
        self.scale = 1.0
        self.windows = {}
        self.drag = None
        self.drops = []
        self.notice = None

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

    def take_drops(self):
        drops, self.drops = self.drops, []
        return drops

    def notify(self, text, seconds=NOTICE_SECONDS):
        """Shows a short message at the top of the screen."""
        self.notice = (text, time.monotonic() + seconds)

    def over_map(self, pos, area):
        """True if pos is on the map: not on the bar, the sidebar or a window."""
        if not area.collidepoint(pos) or self.bar.rect(area).collidepoint(pos):
            return False

        if self.sidebar.is_open and self.sidebar.rect(area, self.bar.rect(area).y).collidepoint(pos):
            return False

        return not any(window.rect.collidepoint(pos) for window in self.windows.values())

    def handle_drag(self, event, area):
        """Returns True if the drag used the event."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.bar.expanded:
            card = self.bar.card_at(event.pos, area)

            if card is not None:
                self.drag = {"id": card, "start": event.pos, "pos": event.pos, "active": False}

            return False

        if self.drag is None:
            return False

        if event.type == pygame.MOUSEMOTION:
            self.drag["pos"] = event.pos

            if not self.drag["active"] and max(abs(event.pos[0] - self.drag["start"][0]), abs(event.pos[1] - self.drag["start"][1])) >= self.px(DRAG_START):
                self.drag["active"] = True
                self.bar.pressed = None

            return self.drag["active"]

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            drag, self.drag = self.drag, None

            if not drag["active"]:
                return False

            if self.over_map(event.pos, area):
                self.drops.append((drag["id"], event.pos))

            return True

        return self.drag["active"] and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)

    def reset(self):
        """Closes everything (used when leaving a game)."""
        self.drag = None
        self.drops = []
        self.notice = None
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
            if self.drag is not None and self.drag["active"]:
                self.drag = None
                return True

            if self.windows:
                self.close(next(reversed(self.windows)))
                return True

            if self.sidebar.is_open:
                self.close_sidebar()
                return True

            if self.bar.expanded:
                self.collapse_blueprints()
                return True

        if self.handle_drag(event, area):
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
        self.draw_drag(surface, area)
        self.draw_notice(surface, area)

    def draw_drag(self, surface, area):
        if self.drag is None or not self.drag["active"]:
            return

        card = next((card for card in self.bar.cards if card["id"] == self.drag["id"]), None)

        if card is None:
            return

        x, y = self.drag["pos"]
        valid = self.over_map((x, y), area)
        size = self.px(40)
        swatch = pygame.Rect(x - size // 2, y - size // 2, size, size)
        pygame.draw.rect(surface, card["color"] if valid else theme.mix(card["color"], theme.PANEL_DARK, 0.6), swatch, border_radius=self.px(6))
        pygame.draw.rect(surface, theme.ACCENT if valid else theme.BAD, swatch, width=2, border_radius=self.px(6))
        self.painter.text(surface, card["name"] if valid else "Drop it on the map", (x + size // 2 + self.px(8), y - self.px(10)), size=self.px(24), color=theme.TEXT if valid else theme.BAD)

    def draw_notice(self, surface, area):
        if self.notice is None:
            return

        text, until = self.notice

        if time.monotonic() > until:
            self.notice = None
            return

        size = self.px(26)
        width = min(area.width - self.px(40), self.painter.measure(text, size)[0] + self.px(40))
        box = pygame.Rect(area.centerx - width // 2, area.y + self.px(16), width, self.px(46))
        pygame.draw.rect(surface, theme.PANEL_DARK, box, border_radius=self.px(10))
        pygame.draw.rect(surface, theme.BAD, box, width=2, border_radius=self.px(10))
        self.painter.text(surface, text, box.center, size=size, max_width=width - self.px(24), center=True)