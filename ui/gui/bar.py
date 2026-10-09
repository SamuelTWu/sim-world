import pygame

from . import theme
from .widgets import draw_button

BUTTONS = (("tech", "Tech Tree"), ("resources", "Resources"), ("blueprints", "Blueprints"))
STATS = (("score", "Score"), ("pixels", "Pixels"))
BUTTON_WIDTH = 150
STAT_WIDTH = 150
MARGIN = 12
TRAY_HEIGHT = 150
CARD_WIDTH = 190


class Bar:
    """The bottom bar: window buttons on the left, a stats panel on the right.

    The Blueprints button expands the bar upward into a tray of cards (`cards`, set by Gui), one per saved
    blueprint. Clicking a card calls `on_select(card id)`; the wheel scrolls the tray sideways. Everything is laid
    out from `scale` (set by Gui from the window size), so it fits any window.

    Clicking a button calls the function registered for it in `handlers`. Stats come from `stats` (name -> text);
    anything missing shows a dash.
    """

    def __init__(self):
        self.handlers = {}
        self.stats = {}
        self.pressed = None
        self.scale = 1.0
        self.active = set()
        self.expanded = False
        self.cards = []
        self.selected = None
        self.on_select = None
        self.tray_scroll = 0
        self.empty_text = "No saved blueprints yet."

    def px(self, value):
        return max(1, round(value * self.scale))

    def tray_height(self):
        return self.px(TRAY_HEIGHT) if self.expanded else 0

    def rect(self, area):
        height = self.px(theme.BAR_HEIGHT) + self.tray_height()
        return pygame.Rect(area.x, area.bottom - height, area.width, height)

    def row_rect(self, area):
        """The strip with the buttons and stats (the whole bar when the tray is closed)."""
        height = self.px(theme.BAR_HEIGHT)
        return pygame.Rect(area.x, area.bottom - height, area.width, height)

    def tray_rect(self, area):
        bar = self.rect(area)
        return pygame.Rect(bar.x, bar.y, bar.width, self.tray_height())

    def stats_rect(self, area):
        row, margin = self.row_rect(area), self.px(MARGIN)
        width = len(STATS) * self.px(STAT_WIDTH) + margin * 2
        return pygame.Rect(row.right - width - margin, row.y + margin, width, row.height - margin * 2)

    def button_rects(self, area):
        row, margin = self.row_rect(area), self.px(MARGIN)
        count = len(BUTTONS)
        room = self.stats_rect(area).x - row.x - margin * (count + 2)
        width = max(40, min(self.px(BUTTON_WIDTH), room // count))
        return [(name, label, pygame.Rect(row.x + margin + index * (width + margin), row.y + margin, width, row.height - margin * 2)) for index, (name, label) in enumerate(BUTTONS)]

    def card_rects(self, area):
        tray, margin = self.tray_rect(area), self.px(MARGIN)
        width = self.px(CARD_WIDTH)
        return [(card, pygame.Rect(tray.x + margin + index * (width + margin) - self.tray_scroll, tray.y + margin, width, tray.height - margin * 2)) for index, card in enumerate(self.cards)]

    def clamp_tray(self, area):
        margin = self.px(MARGIN)
        total = len(self.cards) * (self.px(CARD_WIDTH) + margin) + margin
        self.tray_scroll = max(0, min(self.tray_scroll, total - area.width))

    def card_at(self, pos, area):
        if not self.tray_rect(area).collidepoint(pos):
            return None

        return next((card["id"] for card, rect in self.card_rects(area) if rect.collidepoint(pos)), None)

    def handle_event(self, event, area):
        """Returns True if the bar used the event, so the camera should not see it."""
        bar = self.rect(area)
        pos = getattr(event, "pos", None)

        if event.type == getattr(pygame, "MOUSEWHEEL", None):
            if not self.expanded or not self.tray_rect(area).collidepoint(pygame.mouse.get_pos()):
                return False

            self.tray_scroll -= (event.y + event.x) * self.px(60)
            self.clamp_tray(area)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and pos is not None and bar.collidepoint(pos):
            if event.button == 1:
                card = self.card_at(pos, area)
                button = next((name for name, _, rect in self.button_rects(area) if rect.collidepoint(pos)), None)
                self.pressed = ("card", card) if card else ("button", button) if button else ("bar", None)

            return True

        if event.type == pygame.MOUSEBUTTONUP and pos is not None:
            pressed = self.pressed if event.button == 1 else None

            if event.button == 1:
                self.pressed = None

            if pressed is not None:
                kind, name = pressed

                if kind == "card" and self.card_at(pos, area) == name and self.on_select is not None:
                    self.on_select(name)
                elif kind == "button" and name in self.handlers and any(n == name and rect.collidepoint(pos) for n, _, rect in self.button_rects(area)):
                    self.handlers[name]()

            return pressed is not None or bar.collidepoint(pos)

        return False

    def draw(self, surface, painter, area):
        bar, margin = self.rect(area), self.px(MARGIN)
        pygame.draw.rect(surface, theme.PANEL_DARK, bar)
        pygame.draw.line(surface, theme.BORDER, bar.topleft, bar.topright, 2)
        mouse = pygame.mouse.get_pos()

        if self.expanded:
            self.draw_tray(surface, painter, area, mouse)

        for name, label, rect in self.button_rects(area):
            draw_button(surface, painter, rect, label, hovered=rect.collidepoint(mouse), active=name in self.active, size=self.px(26))

        panel = self.stats_rect(area)
        pygame.draw.rect(surface, theme.PANEL, panel, border_radius=self.px(8))
        pygame.draw.rect(surface, theme.BORDER, panel, width=2, border_radius=self.px(8))

        for index, (name, label) in enumerate(STATS):
            x = panel.x + margin + index * self.px(STAT_WIDTH)
            painter.text(surface, label, (x, panel.y + self.px(5)), size=self.px(20), color=theme.MUTED)
            painter.text(surface, str(self.stats.get(name, "--")), (x, panel.y + self.px(21)), size=self.px(26), max_width=self.px(STAT_WIDTH) - margin)

    def draw_tray(self, surface, painter, area, mouse):
        tray, margin = self.tray_rect(area), self.px(MARGIN)
        pygame.draw.line(surface, theme.BORDER, (tray.x, tray.bottom - 1), (tray.right, tray.bottom - 1), 1)
        self.clamp_tray(area)

        if not self.cards:
            painter.text(surface, self.empty_text, tray.center, size=self.px(24), color=theme.MUTED, max_width=tray.width - margin * 2, center=True)
            return

        surface.set_clip(tray)

        for card, rect in self.card_rects(area):
            if rect.right < tray.x or rect.x > tray.right:
                continue

            selected, hovered = card["id"] == self.selected, rect.collidepoint(mouse) and tray.collidepoint(mouse)
            fill = theme.mix(theme.ACCENT, theme.PANEL, 0.55) if selected else (theme.PANEL_LIGHT if hovered else theme.PANEL)
            pygame.draw.rect(surface, fill, rect, border_radius=self.px(8))
            pygame.draw.rect(surface, theme.ACCENT if selected or hovered else theme.BORDER, rect, width=2, border_radius=self.px(8))
            swatch = pygame.Rect(rect.x + self.px(12), rect.y + self.px(12), self.px(34), self.px(34))
            pygame.draw.rect(surface, card["color"], swatch, border_radius=self.px(6))
            pygame.draw.rect(surface, theme.BORDER, swatch, width=1, border_radius=self.px(6))
            painter.text(surface, card["name"], (swatch.right + self.px(10), rect.y + self.px(12)), size=self.px(26), max_width=rect.right - swatch.right - self.px(18))
            painter.text(surface, card["sub"], (swatch.right + self.px(10), rect.y + self.px(36)), size=self.px(20), color=theme.MUTED, max_width=rect.right - swatch.right - self.px(18))
            painter.text(surface, card["summary"], (rect.x + self.px(12), rect.bottom - self.px(32)), size=self.px(21), color=theme.MUTED, max_width=rect.width - self.px(24))

        surface.set_clip(None)