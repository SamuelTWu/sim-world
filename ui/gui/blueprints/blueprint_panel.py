import pygame

from .. import theme
from .blueprints import describe
from ..widgets import draw_button

SIDEBAR_WIDTH = 380
CLOSE_SIZE = 30
MARGIN = 16
LABEL_SHARE = 0.42


class BlueprintSidebar:
    """A panel down the right side of the screen showing one blueprint's attributes. Scrolls with the wheel."""

    def __init__(self):
        self.scale = 1.0
        self.blueprint = None
        self.sections = []
        self.scroll = 0
        self.pressed = False
        self.close_requested = False

    @property
    def is_open(self):
        return self.blueprint is not None

    def px(self, value):
        return max(1, round(value * self.scale))

    def show(self, blueprint):
        self.blueprint = blueprint
        self.sections = describe(blueprint)
        self.scroll = 0
        self.pressed = False
        self.close_requested = False

    def close(self):
        self.blueprint = None
        self.sections = []
        self.pressed = False

    def width(self, area):
        return min(self.px(SIDEBAR_WIDTH), int(area.width * 0.45))

    def rect(self, area, bottom):
        width = self.width(area)
        return pygame.Rect(area.right - width, area.y, width, bottom - area.y)

    def close_rect(self, panel):
        return pygame.Rect(panel.right - self.px(CLOSE_SIZE) - self.px(10), panel.y + self.px(10), self.px(CLOSE_SIZE), self.px(CLOSE_SIZE))

    def body_rect(self, panel):
        top = panel.y + self.px(92)
        return pygame.Rect(panel.x, top, panel.width, panel.bottom - top - self.px(40))

    def layout(self, painter, body):
        """Rows as (kind, text or (label lines, value lines), height, y) with y relative to the top of the body."""
        margin, size = self.px(MARGIN), self.px(22)
        label_w = int((body.width - margin * 2) * LABEL_SHARE)
        value_w = body.width - margin * 2 - label_w - self.px(8)
        line = self.px(25)
        rows, y = [], 0

        for title, items in self.sections:
            y += self.px(8)
            rows.append(("title", title, y))
            y += self.px(32)

            for label, value in items:
                label_lines = painter.wrap(label, size, label_w) or [""]
                value_lines = painter.wrap(value, size, value_w) or [""]
                height = max(len(label_lines), len(value_lines)) * line + self.px(4)
                rows.append(("row", (label_lines, value_lines), y))
                y += height

        return rows, y + self.px(12)

    def clamp(self, painter, body):
        _, total = self.layout(painter, body)
        self.scroll = max(0, min(self.scroll, total - body.height))

    def handle_event(self, event, area, bottom, painter):
        """Returns True if the sidebar used the event."""
        if not self.is_open:
            return False

        panel = self.rect(area, bottom)
        pos = getattr(event, "pos", None)

        if event.type == getattr(pygame, "MOUSEWHEEL", None):
            if not panel.collidepoint(pygame.mouse.get_pos()):
                return False

            self.scroll -= event.y * self.px(48)
            self.clamp(painter, self.body_rect(panel))
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and pos is not None and panel.collidepoint(pos):
            if event.button == 1:
                self.pressed = self.close_rect(panel).collidepoint(pos)

            return True

        if event.type == pygame.MOUSEBUTTONUP and pos is not None:
            pressed, self.pressed = (self.pressed, False) if event.button == 1 else (False, self.pressed)

            if pressed and self.close_rect(panel).collidepoint(pos):
                self.close_requested = True

            return panel.collidepoint(pos)

        return False

    def draw(self, surface, painter, area, bottom):
        if not self.is_open:
            return

        panel, margin = self.rect(area, bottom), self.px(MARGIN)
        pygame.draw.rect(surface, theme.PANEL, panel)
        pygame.draw.line(surface, theme.BORDER, panel.topleft, panel.bottomleft, 2)
        mouse = pygame.mouse.get_pos()

        swatch = pygame.Rect(panel.x + margin, panel.y + self.px(16), self.px(52), self.px(52))
        pygame.draw.rect(surface, self.blueprint.color, swatch, border_radius=self.px(8))
        pygame.draw.rect(surface, theme.BORDER, swatch, width=2, border_radius=self.px(8))
        close = self.close_rect(panel)
        text_x = swatch.right + self.px(14)
        painter.text(surface, self.blueprint.name, (text_x, panel.y + self.px(18)), size=self.px(32), max_width=close.x - text_x - self.px(8))
        painter.text(surface, f"Blueprint  |  {self.blueprint.kind}", (text_x, panel.y + self.px(48)), size=self.px(22), color=theme.MUTED, max_width=close.x - text_x - self.px(8))
        draw_button(surface, painter, close, "X", hovered=close.collidepoint(mouse), size=self.px(24))
        pygame.draw.line(surface, theme.BORDER, (panel.x, panel.y + self.px(86)), (panel.right, panel.y + self.px(86)), 1)

        body = self.body_rect(panel)
        self.clamp(painter, body)
        rows, total = self.layout(painter, body)
        size, line = self.px(22), self.px(25)
        label_w = int((body.width - margin * 2) * LABEL_SHARE)
        surface.set_clip(body)

        for kind, content, y in rows:
            top = body.y + y - self.scroll

            if top > body.bottom or top < body.y - self.px(200):
                continue

            if kind == "title":
                painter.text(surface, content, (body.x + margin, top), size=self.px(24), color=theme.ACCENT)
                pygame.draw.line(surface, theme.BORDER, (body.x + margin, top + self.px(27)), (body.right - margin, top + self.px(27)), 1)
                continue

            label_lines, value_lines = content

            for index, text in enumerate(label_lines):
                painter.text(surface, text, (body.x + margin, top + index * line), size=size, color=theme.MUTED)

            for index, text in enumerate(value_lines):
                painter.text(surface, text, (body.x + margin + label_w + self.px(8), top + index * line), size=size)

        surface.set_clip(None)

        if total > body.height:
            track = pygame.Rect(panel.right - self.px(6), body.y, self.px(4), body.height)
            thumb_h = max(self.px(24), int(track.height * body.height / total))
            thumb_y = track.y + int((track.height - thumb_h) * self.scroll / max(1, total - body.height))
            pygame.draw.rect(surface, theme.PANEL_LIGHT, track, border_radius=2)
            pygame.draw.rect(surface, theme.BORDER, pygame.Rect(track.x, thumb_y, track.width, thumb_h), border_radius=2)

        footer = pygame.Rect(panel.x, panel.bottom - self.px(40), panel.width, self.px(40))
        pygame.draw.line(surface, theme.BORDER, footer.topleft, footer.topright, 1)
        painter.text(surface, "Drag onto the map to spawn: coming soon", (footer.x + margin, footer.y + self.px(10)), size=self.px(20), color=theme.MUTED, max_width=footer.width - margin * 2)