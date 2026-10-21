import pygame

from ....shared.dev_commands import DEV_COMMANDS, usage
from .console_state import ConsoleState, line_alpha

OPEN_KEY = pygame.K_t
OPEN_TEXT = "/"
FONT_SIZE = 20
MARGIN = 8
MAX_WIDTH = 760
OPEN_LINES = 14
MODIFIERS = pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META
TEXT_EVENTS = tuple(getattr(pygame, name) for name in ("KEYDOWN", "KEYUP", "TEXTINPUT", "TEXTEDITING") if hasattr(pygame, name))
COLORS = {"ok": (110, 230, 120), "error": (240, 100, 100), "echo": (190, 195, 205), "hint": (150, 160, 175), "info": (235, 235, 235)}
BACKGROUND = (0, 0, 0, 150)
BOX_FILL = (20, 22, 28, 235)
BOX_BORDER = (120, 130, 150)
TEXT_COLOR = (240, 240, 240)
HINT_COLOR = (140, 150, 165)
BLINK_PER_SECOND = 2


def wrap(font, text, width):
    if font.size(text)[0] <= width:
        return [text]

    lines, line = [], ""

    for word in text.split(" "):
        trial = f"{line} {word}" if line else word

        if font.size(trial)[0] <= width:
            line = trial
            continue

        if line:
            lines.append(line)

        while font.size(word)[0] > width and len(word) > 1:
            cut = len(word)

            while cut > 1 and font.size(word[:cut])[0] > width:
                cut -= 1

            lines.append(word[:cut])
            word = word[cut:]

        line = word

    return lines + [line] if line else lines


class Console:
    def __init__(self):
        self.state = ConsoleState()
        self.is_open = False
        self.enabled = False
        self.requests = []
        self.font = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

        if not self.enabled:
            self.close()

    def set_catalog(self, data):
        self.state.set_catalog(data)

    def reset(self):
        self.close()
        self.enabled = False
        self.requests.clear()
        self.state = ConsoleState()

    def open(self, text=""):
        self.is_open = True
        self.state.clear()
        self.state.insert(text)

    def close(self):
        self.is_open = False
        self.state.clear()

    def add_result(self, text, ok, now):
        self.state.add_result(text, ok, now)

    def add_line(self, text, kind, now):
        self.state.log_line(text, kind, now)

    def take_requests(self):
        requests, self.requests = self.requests, []
        return requests

    def handle_event(self, event, context=None, now=0.0, blocked=False):
        if not self.enabled:
            return False

        if not self.is_open:
            return self.handle_closed(event, blocked)

        if event.type not in TEXT_EVENTS:
            return False

        if event.type == pygame.KEYDOWN:
            self.handle_key(event, context, now)

        return True

    def handle_closed(self, event, blocked):
        if blocked or event.type != pygame.KEYDOWN or event.mod & MODIFIERS:
            return False

        if event.unicode == OPEN_TEXT:
            self.open(OPEN_TEXT)
            return True

        if event.key == OPEN_KEY:
            self.open()
            return True

        return False

    def handle_key(self, event, context, now):
        state, key = self.state, event.key

        if key == pygame.K_ESCAPE:
            self.close()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            request = state.submit(context() if callable(context) else context, now)
            self.is_open = False

            if request is not None:
                self.requests.append(request)
        elif key == pygame.K_BACKSPACE:
            state.backspace()
        elif key == pygame.K_DELETE:
            state.delete()
        elif key == pygame.K_LEFT:
            state.left()
        elif key == pygame.K_RIGHT:
            state.right()
        elif key == pygame.K_HOME:
            state.home()
        elif key == pygame.K_END:
            state.end()
        elif key == pygame.K_UP:
            state.history_up()
        elif key == pygame.K_DOWN:
            state.history_down()
        elif key == pygame.K_TAB:
            state.tab(now)
        elif event.unicode and not event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META):
            state.insert(event.unicode)

    def get_font(self):
        if self.font is None:
            pygame.font.init()
            self.font = pygame.font.Font(None, FONT_SIZE)

        return self.font

    def draw(self, surface, now, bounds=None):
        if not self.enabled:
            return

        font = self.get_font()
        area = bounds if isinstance(bounds, pygame.Rect) else surface.get_rect()
        width = max(80, min(area.width - 2 * MARGIN, MAX_WIDTH))
        left = area.left + MARGIN
        line_height = font.get_linesize() + 2
        bottom = area.bottom - MARGIN

        if self.is_open:
            box = pygame.Rect(left, bottom - line_height - 8, width, line_height + 8)
            self.draw_input(surface, font, box, now)
            bottom = box.top - 4
            hint = self.hint()

            if hint:
                bottom = self.draw_line(surface, font, hint, "hint", left, bottom, width, line_height, 255)

            lines = [(line, 255) for line in self.state.log[-OPEN_LINES:]]
        else:
            lines = [(line, line_alpha(now - line.time)) for line in self.state.recent(now)]

        for line, alpha in reversed(lines):
            if alpha > 0:
                bottom = self.draw_line(surface, font, line.text, line.kind, left, bottom, width, line_height, alpha)

    def hint(self):
        words = self.state.buffer.lstrip().lstrip("/").split()

        if not words or words[0].lower() not in DEV_COMMANDS:
            return None

        return usage(words[0].lower())

    def draw_line(self, surface, font, text, kind, left, bottom, width, line_height, alpha):
        color = COLORS.get(kind, COLORS["info"])

        for piece in reversed(wrap(font, text, width - 8)):
            bottom -= line_height
            background = pygame.Surface((width, line_height), pygame.SRCALPHA)
            background.fill((BACKGROUND[0], BACKGROUND[1], BACKGROUND[2], BACKGROUND[3] * alpha // 255))
            image = font.render(piece, True, color)
            image.set_alpha(alpha)
            background.blit(image, (4, 1))
            surface.blit(background, (left, bottom))

        return bottom

    def draw_input(self, surface, font, box, now):
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill(BOX_FILL)
        surface.blit(panel, box.topleft)
        pygame.draw.rect(surface, BOX_BORDER, box, 1)
        inner = box.inflate(-12, -4)
        caret_x = font.size(self.state.buffer[: self.state.cursor])[0]
        scroll = max(0, caret_x - inner.width + 4)
        image = font.render(self.state.buffer, True, TEXT_COLOR)
        previous = surface.get_clip()
        surface.set_clip(inner)
        surface.blit(image, (inner.x - scroll, inner.y + 2))

        if int(now * BLINK_PER_SECOND) % 2 == 0:
            pygame.draw.line(surface, TEXT_COLOR, (inner.x - scroll + caret_x, inner.y + 2), (inner.x - scroll + caret_x, inner.bottom - 2))

        surface.set_clip(previous)