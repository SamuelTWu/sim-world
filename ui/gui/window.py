import pygame

from . import theme
from .widgets import draw_button

CLOSE_SIZE = 26
HEADER_BUTTON_WIDTH = 78


class Window:
    """A draggable window with a title bar and a close button. Subclasses draw and handle their own content.

    Override draw_content(), on_event() (return True if you used the event) and on_action() for extra header buttons
    listed in extra_header as (action, label).
    """

    title = "Window"
    size = (900, 600)
    extra_header = ()

    def __init__(self):
        self.rect = pygame.Rect(0, 0, *self.size)
        self.drag_offset = None
        self.pressed = False
        self.close_requested = False

    def place(self, area):
        self.rect.width = max(300, min(self.size[0], area.width - 40))
        self.rect.height = max(200, min(self.size[1], area.height - 40))
        self.rect.x = area.x + (area.width - self.rect.width) // 2
        self.rect.y = area.y + (area.height - self.rect.height) // 2

    def title_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.width, theme.TITLE_HEIGHT)

    def content_rect(self):
        return pygame.Rect(self.rect.x + 2, self.rect.y + theme.TITLE_HEIGHT, self.rect.width - 4, self.rect.height - theme.TITLE_HEIGHT - 2)

    def header_buttons(self):
        """Right-aligned buttons in the title bar as (action, label, rect); the close button is always last."""
        top = self.rect.y + (theme.TITLE_HEIGHT - CLOSE_SIZE) // 2
        buttons = [("close", "X", pygame.Rect(self.rect.right - CLOSE_SIZE - 8, top, CLOSE_SIZE, CLOSE_SIZE))]
        right = self.rect.right - CLOSE_SIZE - 16

        for action, label in reversed(self.extra_header):
            buttons.insert(0, (action, label, pygame.Rect(right - HEADER_BUTTON_WIDTH, top, HEADER_BUTTON_WIDTH, CLOSE_SIZE)))
            right -= HEADER_BUTTON_WIDTH + 8

        return buttons

    def on_event(self, event):
        return False

    def on_action(self, action):
        pass

    def draw_content(self, surface, painter, rect):
        pass

    def handle_event(self, event, area):
        """Returns True if the window used the event, so nothing underneath (the camera) should see it."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.pressed = True

            for action, _, rect in self.header_buttons():
                if rect.collidepoint(event.pos):
                    if action == "close":
                        self.close_requested = True
                    else:
                        self.on_action(action)

                    return True

            if self.title_rect().collidepoint(event.pos):
                self.drag_offset = (event.pos[0] - self.rect.x, event.pos[1] - self.rect.y)
            else:
                self.on_event(event)

            return True

        if event.type == pygame.MOUSEMOTION:
            if self.drag_offset is not None:
                self.rect.x = max(80 - self.rect.width, min(area.right - 80, event.pos[0] - self.drag_offset[0]))
                self.rect.y = max(area.y, min(area.bottom - theme.TITLE_HEIGHT, event.pos[1] - self.drag_offset[1]))
                return True

            return self.on_event(event)

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.on_event(event)
            used = self.pressed
            self.pressed = False
            self.drag_offset = None
            return used

        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button in (2, 3, 4, 5):
            return self.rect.collidepoint(event.pos)

        if event.type == getattr(pygame, "MOUSEWHEEL", None):
            return self.on_event(event) or self.rect.collidepoint(pygame.mouse.get_pos())

        return False

    def draw(self, surface, painter):
        shadow = self.rect.move(5, 6)
        pygame.draw.rect(surface, theme.SHADOW, shadow, border_radius=10)
        pygame.draw.rect(surface, theme.PANEL, self.rect, border_radius=10)
        pygame.draw.rect(surface, theme.PANEL_LIGHT, self.title_rect(), border_top_left_radius=10, border_top_right_radius=10)
        painter.text(surface, self.title, (self.rect.x + 16, self.rect.y + 10), size=28)
        mouse = pygame.mouse.get_pos()

        for action, label, rect in self.header_buttons():
            draw_button(surface, painter, rect, label, hovered=rect.collidepoint(mouse))

        self.draw_content(surface, painter, self.content_rect())
        pygame.draw.rect(surface, theme.BORDER, self.rect, width=2, border_radius=10)