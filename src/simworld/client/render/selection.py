"""Selecting your pixels and giving them orders with the mouse.

    ctrl + left-drag         draws a rectangle on the map and selects your pixels inside it (add shift to add to the selection)
    ctrl + left-click        selects the pixel under it (on empty ground it clears the selection)
    plain left-click         on one of your pixels (the mouse not moving) asks the server for its attributes: the side panel
                             shows them with controls to upgrade it (`inspect`, see Renderer.take_inspect_requests)
                             (plain left-drag is the camera's: it pans. Cmd works like ctrl on a Mac.)
    right-click              sends `act` for the selection at that spot: attack a hostile pixel there, otherwise move
    after selecting          a small menu pops up next to the mouse: Move, Attack, Spawn, Drop everything, Pick up.
                             Pick one, then click a spot on the map (Esc or right-click cancels). Spawn uses the blueprint
                             picked in the Blueprints tray.
    Esc                      closes the menu, then cancels a pending action, then clears the selection

Selected pixels get a highlight ring, the drag shows a translucent box, and the top left says how many are selected.

This file only decides WHAT to ask for. The requests it builds ({"ids", "point", "action"?, ...}, the arguments of the `act`
command) wait in `requests` until the game sends them (Renderer.take_act_requests); the server checks everything. The client
only knows about pixels it was told about, so for now only the pixels you own can be selected.
"""
import pygame

from src.simworld.client.ui.gui import theme
from ..ui.widgets import draw_button
from .sprites import get_sprite

CONTROL = pygame.KMOD_CTRL | getattr(pygame, "KMOD_META", 0)
DRAG_START = 6
MENU_WIDTH = 190
ITEM_HEIGHT = 34
MIN_RING = 10

# (action sent to `act` or None, label, hint shown while waiting for the click)
ACTIONS = [
    ("move", "Move", "Click where to go"),
    ("attack", "Attack", "Click the pixel to attack"),
    ("spawn", "Spawn", "Click where to spawn"),
    ("drop", "Drop everything", "Click where to drop"),
    ("pickup", "Pick up", "Click one of your pixels to pick it up"),
]


class Selection:
    def __init__(self, gui):
        self.gui = gui
        self.ids = set()
        self.drag = None
        self.menu = None
        self.pending = None
        self.requests = []
        self.inspects = []
        self.click = None
        self.right_down = False
        self.swallow_up = False

    def take_inspects(self):
        inspects, self.inspects = self.inspects, []
        return inspects

    def reset(self):
        self.ids.clear()
        self.drag = self.menu = self.pending = None
        self.requests = []
        self.inspects = []
        self.click = None
        self.right_down = self.swallow_up = False

    def take_requests(self):
        requests, self.requests = self.requests, []
        return requests

    def prune(self, entities, player_id):
        """Forget pixels that are gone (or were never yours)."""
        mine = {entity.id for entity in entities if player_id is not None and entity.owner == player_id}
        self.ids &= mine

        if not self.ids:
            self.menu = None
            self.pending = None

    # ---- hit testing

    def screen_point(self, camera, entity):
        return camera.world_to_screen(entity.position.x, entity.position.y)

    def ring_radius(self, camera, entity):
        sprite = get_sprite(entity.sprite_id)
        return max(self.gui.px(MIN_RING), max(sprite.size) * camera.zoom / 2 + self.gui.px(4))

    def pixel_at(self, pos, entities, player_id, camera):
        best, best_distance = None, None

        for entity in entities:
            if player_id is None or entity.owner != player_id:
                continue

            x, y = self.screen_point(camera, entity)
            distance = ((x - pos[0]) ** 2 + (y - pos[1]) ** 2) ** 0.5

            if distance <= self.ring_radius(camera, entity) and (best is None or distance < best_distance):
                best, best_distance = entity, distance

        return best

    def pixels_in(self, rect, entities, player_id, camera):
        return {entity.id for entity in entities if player_id is not None and entity.owner == player_id and rect.collidepoint(self.screen_point(camera, entity))}

    # ---- the menu

    def menu_rect(self, area):
        scale = self.gui.px
        height = scale(ITEM_HEIGHT) * (len(ACTIONS) + 1) + scale(12)
        width = scale(MENU_WIDTH)
        play = self.gui.play_area(area)
        x = max(play.x, min(play.right - width, self.menu["pos"][0] + scale(14)))
        y = max(play.y, min(play.bottom - height, self.menu["pos"][1] + scale(14)))
        return pygame.Rect(x, y, width, height)

    def item_rects(self, area):
        box = self.menu_rect(area)
        item = self.gui.px(ITEM_HEIGHT)
        gap = self.gui.px(6)
        return [(action, pygame.Rect(box.x + gap, box.y + gap + item * (index + 1), box.width - gap * 2, item - self.gui.px(4))) for index, (action, _, _) in enumerate(ACTIONS)]

    def choose(self, action):
        self.menu = None
        hint = next(hint for name, _, hint in ACTIONS if name == action)

        if action == "spawn":
            blueprint = self.gui.bar.selected

            if blueprint is None:
                self.gui.notify("Open Blueprints and pick one to spawn first")
                return

            self.pending = {"action": "spawn", "hint": hint, "extras": {"blueprint": blueprint}}
        elif action == "drop":
            self.pending = {"action": "drop", "hint": hint, "extras": {"item": {"all": True}}}
        else:
            self.pending = {"action": action, "hint": hint, "extras": {}}

    # ---- events

    def request(self, point, action=None, extras=None):
        args = {"ids": sorted(self.ids), "point": [float(point[0]), float(point[1])]}

        if action is not None:
            args["action"] = action
            args.update(extras or {})

        self.requests.append(args)

    def handle_event(self, event, entities, player_id, camera, screen_to_world):
        """Returns True if the selection used the event, so the camera should not see it."""
        area = self.gui.area()

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.menu is not None:
                self.menu = None
            elif self.pending is not None:
                self.pending = None
            elif self.ids:
                self.ids.clear()
            else:
                return False

            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.left_down(event, entities, player_id, camera, screen_to_world, area)

        if event.type == pygame.MOUSEMOTION and self.drag is not None:
            self.drag["pos"] = event.pos
            far = max(abs(event.pos[0] - self.drag["start"][0]), abs(event.pos[1] - self.drag["start"][1]))
            self.drag["active"] = self.drag["active"] or far >= self.gui.px(DRAG_START)
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag is not None:
            return self.left_up(event, entities, player_id, camera)

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.click is not None:
            click, self.click = self.click, None
            moved = max(abs(event.pos[0] - click["pos"][0]), abs(event.pos[1] - click["pos"][1]))

            if moved < self.gui.px(DRAG_START) and not self.swallow_up:
                self.inspects.append(click["id"])

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.swallow_up:
            self.swallow_up = False
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            return self.right_click(event, screen_to_world, area)

        if event.type == pygame.MOUSEBUTTONUP and event.button == 3 and self.right_down:
            self.right_down = False
            return True

        return False

    def left_down(self, event, entities, player_id, camera, screen_to_world, area):
        self.click = None
        if self.menu is not None:
            for action, rect in self.item_rects(area):
                if rect.collidepoint(event.pos):
                    self.choose(action)
                    self.swallow_up = True
                    return True

            if self.menu_rect(area).collidepoint(event.pos):
                self.swallow_up = True
                return True

            self.menu = None

        if not self.gui.over_map(event.pos, area):
            return False

        if self.pending is not None:
            pending, self.pending = self.pending, None
            self.request(screen_to_world(event.pos), pending["action"], pending["extras"])
            self.swallow_up = True
            return True

        if not pygame.key.get_mods() & CONTROL:
            pixel = self.pixel_at(event.pos, entities, player_id, camera)
            self.click = {"pos": event.pos, "id": pixel.id} if pixel is not None else None
            return False  # the camera still gets the press: a click on a pixel is only a click if the mouse does not move

        self.drag = {"start": event.pos, "pos": event.pos, "active": False}
        return True

    def left_up(self, event, entities, player_id, camera):
        drag, self.drag = self.drag, None
        add = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)

        if drag["active"]:
            left, top = min(drag["start"][0], event.pos[0]), min(drag["start"][1], event.pos[1])
            rect = pygame.Rect(left, top, abs(event.pos[0] - drag["start"][0]), abs(event.pos[1] - drag["start"][1]))
            picked = self.pixels_in(rect, entities, player_id, camera)
        else:
            pixel = self.pixel_at(event.pos, entities, player_id, camera)
            picked = {pixel.id} if pixel is not None else set()

        self.ids = (self.ids | picked) if add else picked
        self.menu = {"pos": event.pos} if self.ids else None
        return True

    def right_click(self, event, screen_to_world, area):
        if self.menu is not None or self.pending is not None:
            self.menu = self.pending = None
            self.right_down = True
            return True

        if not self.ids or not self.gui.over_map(event.pos, area):
            return False

        self.request(screen_to_world(event.pos))
        self.right_down = True
        return True

    # ---- drawing

    def draw_world(self, surface, entities, camera):
        """The rings and the drag box. Draw this after the pixels and before the GUI."""
        for entity in entities:
            if entity.id in self.ids:
                x, y = self.screen_point(camera, entity)
                pygame.draw.circle(surface, theme.ACCENT, (round(x), round(y)), round(self.ring_radius(camera, entity)), width=max(2, self.gui.px(2)))

        if self.drag is not None and self.drag["active"]:
            start, pos = self.drag["start"], self.drag["pos"]
            rect = pygame.Rect(min(start[0], pos[0]), min(start[1], pos[1]), abs(pos[0] - start[0]), abs(pos[1] - start[1]))
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill((*theme.ACCENT, 50))
            surface.blit(overlay, rect.topleft)
            pygame.draw.rect(surface, theme.ACCENT, rect, width=max(1, self.gui.px(2)))

    def draw_menu(self, surface):
        """The count, the menu and the waiting hint. Draw this after the GUI so it is on top."""
        area = self.gui.area()
        painter = self.gui.painter
        px = self.gui.px

        if self.ids:
            text = f"{len(self.ids)} selected"
            painter.text(surface, text, (area.x + px(16), area.y + px(14)), size=px(24), color=theme.TEXT)

        mouse = pygame.mouse.get_pos()

        if self.menu is not None:
            box = self.menu_rect(area)
            pygame.draw.rect(surface, theme.SHADOW, box.move(px(4), px(5)), border_radius=px(8))
            pygame.draw.rect(surface, theme.PANEL, box, border_radius=px(8))
            pygame.draw.rect(surface, theme.BORDER, box, width=2, border_radius=px(8))
            painter.text(surface, f"{len(self.ids)} selected", (box.x + px(12), box.y + px(8)), size=px(20), color=theme.MUTED)

            for (action, rect), (_, label, _) in zip(self.item_rects(area), ACTIONS):
                draw_button(surface, painter, rect, label, hovered=rect.collidepoint(mouse), size=px(22))

        if self.pending is not None:
            text = f"{self.pending['hint']}   (Esc or right-click cancels)"
            width = painter.measure(text, px(22))[0] + px(24)
            x = max(area.x + px(8), min(area.right - width - px(8), mouse[0] + px(16)))
            box = pygame.Rect(x, max(area.y + px(8), mouse[1] - px(40)), width, px(34))
            pygame.draw.rect(surface, theme.PANEL_DARK, box, border_radius=px(8))
            pygame.draw.rect(surface, theme.ACCENT, box, width=2, border_radius=px(8))
            painter.text(surface, text, box.center, size=px(22), center=True)