import pygame

from . import theme
from .widgets import draw_button

BUTTONS = (("tech", "Tech Tree"), ("resources", "Resources"), ("structures", "Structures"), ("blueprints", "Blueprints"))
STATS = (("score", "Score"), ("pixels", "Pixels"))
BUTTON_WIDTH = 150
STAT_WIDTH = 150
MARGIN = 12


class Bar:
    """The bottom bar: window buttons on the left, a stats panel on the right. All of it is placeholder for now.

    Everything is laid out from `scale` (set by Gui from the window size), so the bar fits any window: it gets
    taller and wider on big screens, and the buttons shrink to fit on narrow ones.

    Clicking a button only calls the function registered for it in `handlers` (empty for now). Stats come from
    `stats` (name -> text); anything missing shows a dash.
    """

    def __init__(self):
        self.handlers = {}
        self.stats = {}
        self.pressed = None
        self.scale = 1.0
        self.active = set()

    def px(self, value):
        return max(1, round(value * self.scale))

    def rect(self, area):
        height = self.px(theme.BAR_HEIGHT)
        return pygame.Rect(area.x, area.bottom - height, area.width, height)

    def stats_rect(self, area):
        bar, margin = self.rect(area), self.px(MARGIN)
        width = len(STATS) * self.px(STAT_WIDTH) + margin * 2
        return pygame.Rect(bar.right - width - margin, bar.y + margin, width, bar.height - margin * 2)

    def button_rects(self, area):
        bar, margin = self.rect(area), self.px(MARGIN)
        count = len(BUTTONS)
        room = self.stats_rect(area).x - bar.x - margin * (count + 2)
        width = max(40, min(self.px(BUTTON_WIDTH), room // count))
        return [(name, label, pygame.Rect(bar.x + margin + index * (width + margin), bar.y + margin, width, bar.height - margin * 2)) for index, (name, label) in enumerate(BUTTONS)]

    def handle_event(self, event, area):
        """Returns True if the bar used the event, so the camera should not see it."""
        bar = self.rect(area)
        pos = getattr(event, "pos", None)

        if event.type == pygame.MOUSEBUTTONDOWN and pos is not None and bar.collidepoint(pos):
            if event.button == 1:
                self.pressed = next((name for name, _, rect in self.button_rects(area) if rect.collidepoint(pos)), "bar")

            return True

        if event.type == pygame.MOUSEBUTTONUP and pos is not None:
            pressed = self.pressed if event.button == 1 else None

            if event.button == 1:
                self.pressed = None

            for name, _, rect in self.button_rects(area):
                if name == pressed and rect.collidepoint(pos) and name in self.handlers:
                    self.handlers[name]()

            return pressed is not None or bar.collidepoint(pos)

        return False

    def draw(self, surface, painter, area):
        bar, margin = self.rect(area), self.px(MARGIN)
        pygame.draw.rect(surface, theme.PANEL_DARK, bar)
        pygame.draw.line(surface, theme.BORDER, bar.topleft, bar.topright, 2)
        mouse = pygame.mouse.get_pos()

        for name, label, rect in self.button_rects(area):
            draw_button(surface, painter, rect, label, hovered=rect.collidepoint(mouse), active=name in self.active, size=self.px(26))

        panel = self.stats_rect(area)
        pygame.draw.rect(surface, theme.PANEL, panel, border_radius=self.px(8))
        pygame.draw.rect(surface, theme.BORDER, panel, width=2, border_radius=self.px(8))

        for index, (name, label) in enumerate(STATS):
            x = panel.x + margin + index * self.px(STAT_WIDTH)
            painter.text(surface, label, (x, panel.y + self.px(5)), size=self.px(20), color=theme.MUTED)
            painter.text(surface, str(self.stats.get(name, "--")), (x, panel.y + self.px(21)), size=self.px(26), max_width=self.px(STAT_WIDTH) - margin)