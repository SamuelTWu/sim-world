import pygame

from .dev_panel_state import PanelState, entity_at, fit_zoom, goto_target

TOGGLE_KEY = pygame.K_F3
WIDTH = 240
ROW = 26
GAP = 4
TOP = 44
TITLE = 22
HEADING = 18
MARGIN = 8
FONT_SIZE = 20
PICKER_WIDTH = 230
PICKER_ROWS = 12
PICKER_ROW = 22
CLICK_MOVE = 6
FILL = (20, 22, 28, 225)
BORDER = (120, 130, 150)
BUTTON = (52, 58, 72)
HOVER = (74, 82, 102)
ACTIVE = (200, 150, 40)
TEXT = (240, 240, 240)
MUTED = (150, 160, 175)
INK = (30, 24, 8)
RING = (255, 196, 64)


class DevPanel:
    def __init__(self, host):
        self.host = host
        self.state = PanelState()
        self.requests = []
        self.down = None
        self.swallow = False
        self.font = None

    @property
    def enabled(self):
        return self.state.enabled

    @property
    def is_open(self):
        return self.state.open

    def set_enabled(self, enabled):
        self.state.set_enabled(enabled)

        if not enabled:
            self.down = None
            self.swallow = False

    def reset(self):
        self.state.reset()
        self.requests.clear()
        self.down = None
        self.swallow = False

    def set_catalog(self, data):
        self.state.set_catalog(data)

    def note_result(self, what, message):
        self.state.note_result(what, message)

    def take_requests(self):
        requests, self.requests = self.requests, []
        return requests

    def get_font(self):
        if self.font is None:
            pygame.font.init()
            self.font = pygame.font.Font(None, FONT_SIZE)

        return self.font

    def area(self):
        area = self.host.gui_area()

        if area is not None:
            return area

        surface = pygame.display.get_surface()
        return surface.get_rect() if surface is not None else pygame.Rect(0, 0, 800, 600)

    def layout(self):
        area = self.area()
        left, top = area.x + MARGIN, area.y + TOP
        y = top + TITLE
        items, heading = [], None

        for row in self.state.rows():
            if row[0][0].startswith("goto:"):
                heading = y
                y += HEADING

            width = (WIDTH - GAP * (len(row) - 1)) // len(row)

            for index, (key, label, active) in enumerate(row):
                items.append((key, label, active, pygame.Rect(left + index * (width + GAP), y, width, ROW)))

            y += ROW + GAP

        hint = self.state.hint()
        box = pygame.Rect(left - 4, top - 4, WIDTH + 8, y - top + 4 + (HEADING if hint else 0))
        return items, box, heading, (left, top)

    def picker_layout(self, items):
        kind = self.state.picker

        if kind is None:
            return None, []

        anchor = next(rect for key, _, _, rect in items if key == kind)
        names = self.state.options(kind)
        shown = names[self.state.scroll : self.state.scroll + PICKER_ROWS]
        height = max(1, len(shown)) * PICKER_ROW + 8
        box = pygame.Rect(anchor.right + 12, anchor.y, PICKER_WIDTH, height)
        return box, [(name, pygame.Rect(box.x + 4, box.y + 4 + index * PICKER_ROW, box.width - 8, PICKER_ROW)) for index, name in enumerate(shown)]

    def context(self):
        context = self.host.dev_context()
        alive = {entity.id for entity in self.host.view_entities}
        selected = self.state.current_selected(alive, context.get("selected"))
        return {"selected": selected, "cursor": context.get("cursor")}

    def tile_at(self, pos):
        x, y = self.host.screen_to_world(pos)
        return x / self.host.TILE_SIZE, y / self.host.TILE_SIZE

    def entity_at(self, pos):
        return entity_at(pos, self.host.view_entities, self.host.camera.world_to_screen, self.host.entity_radius)

    def apply(self, result, now):
        self.requests.extend(result.requests)

        for text, kind in result.lines:
            self.host.console.add_line(text, kind, now)

        if result.goto is not None:
            self.go_to(result.goto, now)

    def go_to(self, name, now):
        target = goto_target(getattr(self.host, "world_labels", ()), name)

        if target is None:
            self.host.console.add_line(f"nothing to go to for '{name}'", "error", now)
            return

        camera, tile = self.host.camera, self.host.TILE_SIZE
        area = self.area()
        camera.x, camera.y = target.x * tile, target.y * tile
        camera.zoom = fit_zoom(target.span, (area.width, area.height), tile, camera.min_zoom, camera.max_zoom)

    def handle_event(self, event, now=0.0):
        state = self.state

        if not state.enabled:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == TOGGLE_KEY:
                state.toggle()
                self.down = None
                self.swallow = False
                return True

            return event.key == pygame.K_ESCAPE and state.open and state.cancel()

        if not state.open:
            return False

        if event.type == pygame.MOUSEWHEEL:
            return self.wheel(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.mouse_down(event, now)

        if event.type == pygame.MOUSEMOTION and state.painting:
            self.apply(state.drag(self.tile_at(event.pos)), now)
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return self.mouse_up(event)

        return False

    def wheel(self, event):
        items, _, _, _ = self.layout()
        box, _ = self.picker_layout(items)

        if box is None or not box.collidepoint(pygame.mouse.get_pos()):
            return False

        biggest = max(0, len(self.state.options(self.state.picker)) - PICKER_ROWS)
        self.state.scroll = max(0, min(biggest, self.state.scroll - event.y))
        return True

    def mouse_down(self, event, now):
        state = self.state
        items, box, _, _ = self.layout()
        picker_box, options = self.picker_layout(items)

        if picker_box is not None and picker_box.collidepoint(event.pos):
            for name, rect in options:
                if rect.collidepoint(event.pos):
                    self.apply(state.pick_option(name), now)

            self.swallow = True
            return True

        if box.collidepoint(event.pos):
            for key, _, _, rect in items:
                if rect.collidepoint(event.pos):
                    self.apply(state.press(key, self.context()), now)

            self.swallow = True
            return True

        state.picker = None

        if not self.host.over_map(event.pos):
            return False

        if state.mode is not None:
            self.apply(state.click(self.tile_at(event.pos), self.entity_at(event.pos)), now)
            self.swallow = True
            return True

        self.down = event.pos
        return False

    def mouse_up(self, event):
        self.state.release()

        if self.swallow:
            self.swallow = False
            return True

        down, self.down = self.down, None

        if down is not None and max(abs(event.pos[0] - down[0]), abs(event.pos[1] - down[1])) < CLICK_MOVE:
            self.state.select(self.entity_at(event.pos))

        return False

    def draw(self, surface, now):
        state = self.state

        if not state.enabled or not state.open:
            return

        font = self.get_font()
        items, box, heading, origin = self.layout()
        mouse = pygame.mouse.get_pos()
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill(FILL)
        surface.blit(panel, box.topleft)
        pygame.draw.rect(surface, BORDER, box, 1)
        surface.blit(font.render("DEV TOOLS (F3)", True, RING), origin)

        if heading is not None:
            surface.blit(font.render("Go to", True, MUTED), (origin[0], heading))

        for _, label, active, rect in items:
            pygame.draw.rect(surface, ACTIVE if active else (HOVER if rect.collidepoint(mouse) else BUTTON), rect, border_radius=4)
            image = font.render(label, True, INK if active else TEXT)
            previous = surface.get_clip()
            surface.set_clip(rect)
            surface.blit(image, image.get_rect(center=rect.center) if image.get_width() <= rect.width - 8 else (rect.x + 4, rect.centery - image.get_height() // 2))
            surface.set_clip(previous)

        hint = state.hint()

        if hint:
            surface.blit(font.render(hint, True, MUTED), (origin[0], box.bottom - HEADING))

        self.draw_picker(surface, font, items, mouse)
        self.draw_selected(surface, font)

    def draw_picker(self, surface, font, items, mouse):
        box, options = self.picker_layout(items)

        if box is None:
            return

        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill(FILL)
        surface.blit(panel, box.topleft)
        pygame.draw.rect(surface, BORDER, box, 1)

        if not options:
            surface.blit(font.render("catalog not loaded", True, MUTED), (box.x + 8, box.y + 6))

        for name, rect in options:
            if rect.collidepoint(mouse):
                pygame.draw.rect(surface, HOVER, rect, border_radius=3)

            surface.blit(font.render(name, True, TEXT), (rect.x + 4, rect.y + 3))

    def draw_selected(self, surface, font):
        alive = {entity.id: entity for entity in self.host.view_entities}
        selected = self.state.selected
        inspect = self.state.inspect

        if selected in alive:
            entity = alive[selected]
            x, y = self.host.camera.world_to_screen(entity.position.x, entity.position.y)
            pygame.draw.circle(surface, RING, (round(x), round(y)), round(self.host.entity_radius(entity)), 2)

        if inspect is None or inspect[0] not in alive:
            return

        entity = alive[inspect[0]]
        x, y = self.host.camera.world_to_screen(entity.position.x, entity.position.y)
        lines = inspect[1].split("\n")
        images = [font.render(line, True, TEXT) for line in lines if line]

        if not images:
            return

        width = max(image.get_width() for image in images) + 12
        height = sum(image.get_height() + 2 for image in images) + 8
        area = self.area()
        left = x + self.host.entity_radius(entity) + 8
        left = left if left + width <= area.right else x - self.host.entity_radius(entity) - 8 - width
        box = pygame.Rect(round(max(area.x, left)), round(max(area.y, min(area.bottom - height, y - height / 2))), width, height)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill(FILL)
        surface.blit(panel, box.topleft)
        pygame.draw.rect(surface, RING, box, 1)
        offset = box.y + 4

        for image in images:
            surface.blit(image, (box.x + 6, offset))
            offset += image.get_height() + 2