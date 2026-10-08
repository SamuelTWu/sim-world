import textwrap
import time
from urllib.parse import urlsplit

import pygame

from server.server import DEFAULT_PORT

SINGLEPLAYER = "singleplayer"
JOIN = "join"
QUIT = "quit"

DEFAULT_ADDRESS = f"127.0.0.1:{DEFAULT_PORT}"
MAX_ADDRESS_LENGTH = 100

BACKGROUND = (20, 22, 28)
TITLE = (235, 235, 240)
TEXT = (225, 225, 230)
MUTED = (140, 145, 155)
BUTTON = (45, 50, 62)
BUTTON_SELECTED = (70, 110, 190)
FIELD = (32, 35, 44)
FIELD_BORDER = (90, 100, 125)
WARNING = (240, 130, 120)


def normalize_address(text):
    """Turn what the player typed ("host", "host:port", "ws://host:port") into a ws:// URL, or raise ValueError."""
    text = text.strip()

    if not text:
        raise ValueError("Enter a server address")

    if any(char.isspace() for char in text):
        raise ValueError("The address cannot contain spaces")

    parts = urlsplit(text if "://" in text else f"ws://{text}")

    if parts.scheme not in ("ws", "wss"):
        raise ValueError("The address must start with ws:// or wss:// (or have no prefix)")

    try:
        port = parts.port
    except ValueError:
        raise ValueError("The port must be a number between 1 and 65535") from None

    if not parts.hostname:
        raise ValueError("Enter a host name or IP address")

    if port == 0:
        raise ValueError("The port must be a number between 1 and 65535")

    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{parts.scheme}://{host}:{port or DEFAULT_PORT}"


def read_clipboard():
    try:
        pygame.scrap.init()
        data = pygame.scrap.get(pygame.SCRAP_TEXT)
    except (pygame.error, AttributeError, TypeError):
        return ""

    return "".join(data.decode("utf-8", "ignore").replace("\x00", "").split()) if data else ""


class Menu:
    def __init__(self):
        self.address = DEFAULT_ADDRESS
        self.screen = "main"
        self.notice = None
        self.selected = 0
        self.fonts = {}

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = pygame.font.Font(None, size)

        return self.fonts[size]

    def show(self, notice=None, screen="main"):
        """Blocks until the player chooses. Returns (SINGLEPLAYER, None), (JOIN, url) or (QUIT, None)."""
        pygame.font.init()
        self.screen, self.notice, self.selected = screen, notice, 0
        clock = pygame.time.Clock()
        pygame.key.set_repeat(400, 40)

        try:
            while True:
                surface = pygame.display.get_surface()

                for event in pygame.event.get():
                    result = self.handle(event, surface)

                    if result is not None:
                        return result

                self.draw(surface)
                clock.tick(60)
        finally:
            pygame.key.set_repeat()

    def buttons(self, surface):
        width, height = surface.get_size()
        labels = [("Singleplayer", SINGLEPLAYER), ("Join", "join_screen"), ("Quit", QUIT)] if self.screen == "main" else [("Connect", "connect"), ("Back", "back")]
        top = int(height * (0.40 if self.screen == "main" else 0.56))
        return [(label, action, pygame.Rect((width - 380) // 2, top + index * 80, 380, 60)) for index, (label, action) in enumerate(labels)]

    def field_rect(self, surface):
        width, height = surface.get_size()
        return pygame.Rect((width - 600) // 2, int(height * 0.42), 600, 56)

    def activate(self, action):
        if action in (SINGLEPLAYER, QUIT):
            return action, None

        if action == "join_screen":
            self.screen, self.notice, self.selected = "join", None, 0
        elif action == "back":
            self.screen, self.notice, self.selected = "main", None, 0
        elif action == "connect":
            try:
                return JOIN, normalize_address(self.address)
            except ValueError as problem:
                self.notice = str(problem)

        return None

    def handle(self, event, surface):
        if event.type == pygame.QUIT:
            return QUIT, None

        buttons = self.buttons(surface)

        if event.type == pygame.MOUSEMOTION:
            for index, (_, _, rect) in enumerate(buttons):
                if rect.collidepoint(event.pos):
                    self.selected = index
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for _, action, rect in buttons:
                if rect.collidepoint(event.pos):
                    return self.activate(action)
        elif event.type == pygame.KEYDOWN:
            return self.handle_key(event, buttons)

        return None

    def handle_key(self, event, buttons):
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self.activate("connect" if self.screen == "join" else buttons[self.selected][1])

        if self.screen == "main":
            if event.key == pygame.K_DOWN:
                self.selected = (self.selected + 1) % len(buttons)
            elif event.key == pygame.K_UP:
                self.selected = (self.selected - 1) % len(buttons)

            return None

        if event.key == pygame.K_ESCAPE:
            return self.activate("back")

        if event.key == pygame.K_BACKSPACE:
            self.address, self.notice = self.address[:-1], None
        elif event.key == pygame.K_v and event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
            self.address, self.notice = (self.address + read_clipboard())[:MAX_ADDRESS_LENGTH], None
        elif event.unicode and event.unicode.isprintable() and not event.unicode.isspace():
            self.address, self.notice = (self.address + event.unicode)[:MAX_ADDRESS_LENGTH], None

        return None

    def draw(self, surface):
        width, height = surface.get_size()
        surface.fill(BACKGROUND)
        title = self.font(120).render("Sim World", True, TITLE)
        surface.blit(title, ((width - title.get_width()) // 2, int(height * 0.12)))

        if self.screen == "join":
            field = self.field_rect(surface)
            surface.blit(self.font(30).render("Server address", True, MUTED), (field.x, field.y - 36))
            pygame.draw.rect(surface, FIELD, field, border_radius=8)
            pygame.draw.rect(surface, FIELD_BORDER, field, width=2, border_radius=8)
            shown = self.address + ("|" if int(time.monotonic() * 2) % 2 == 0 else "")

            while len(shown) > 1 and self.font(40).size(shown)[0] > field.width - 32:
                shown = shown[1:]

            text = self.font(40).render(shown, True, TEXT)
            surface.blit(text, (field.x + 16, field.y + (field.height - text.get_height()) // 2))
            surface.blit(self.font(26).render(f"Example: 192.168.1.20:{DEFAULT_PORT}  (port {DEFAULT_PORT} if left out)", True, MUTED), (field.x, field.bottom + 12))

        for index, (label, _, rect) in enumerate(self.buttons(surface)):
            pygame.draw.rect(surface, BUTTON_SELECTED if index == self.selected else BUTTON, rect, border_radius=10)
            image = self.font(40).render(label, True, TEXT)
            surface.blit(image, (rect.centerx - image.get_width() // 2, rect.centery - image.get_height() // 2))

        for index, line in enumerate(textwrap.wrap(self.notice or "", 110)):
            image = self.font(28).render(line, True, WARNING)
            surface.blit(image, ((width - image.get_width()) // 2, int(height * 0.86) + index * 32))

        pygame.display.flip()