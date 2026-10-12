import time

import pygame

from .. import theme
from ..icon import draw_icon
from .editor_model import COLORS, SHAPES, STATS, EditorModel, kind_of, prettify, show_number
from ..widgets import draw_button

MARGIN = 16
ROW = 36
BUTTON = 30
HEADER = 86
FOOTER = 96
CARET_BLINK = 0.5


class BlueprintEditor:
    """Designing a new blueprint, drawn inside the sidebar (BlueprintSidebar hands it the panel).

    Everything is clicks: a name field, a colour palette and shape buttons, - / + steppers for the stats, and
    "+ Add behavior" which lists every behavior the game has (gui/catalog.py); an added behavior shows its parameters
    as steppers, on/off buttons, pick-one buttons or text fields, so nothing can be set to a value the server would refuse.
    Shift-click a stepper to move it five times as far. Hovering anything shows what it does at the bottom.
    Save puts (name, definition) in `save_request`; the Gui sends it to the server (`save_blueprint`) and closes the editor
    when the new file appears. The data lives in `self.model` (editor_model.py, no pygame).

    The same panel edits a pixel that exists (`info` given: the server's description of it, from `inspect`): no name or look,
    the stats and behaviors it has now, "+ Add behavior" for new ones, and the cost of the upgrade at the bottom. Apply puts
    (pixel id, changes) in `edit_request` (the paths `edit_property` takes); the Gui sends it and shows the pixel's new
    attributes when the server answers. Behaviors it already has cannot be removed.

    The panel scrolls with the wheel. A field with focus gets the keyboard (Enter or Esc leaves it).
    """

    def __init__(self, catalog, taken=(), info=None, color=None):
        self.model = EditorModel.from_info(catalog, info) if info is not None else EditorModel(catalog, taken)
        self.info = info
        self.edit_request = None
        self.sprite_color = None  # set by the Gui: sprite id -> colour, so a held pixel's icon can use its own colour

        if color is not None:
            self.model.color = tuple(color)

        self.scale = 1.0
        self.scroll = 0
        self.focus = None
        self.pressed = None
        self.picking = None
        self.status = ""
        self.status_good = False
        self.hint = ""
        self.save_request = None
        self.saving = False
        self.close_requested = False
        self.touched = False
        self.confirm_close = False
        self.cells = []
        self.zones = []
        self.total = 0

    def px(self, value):
        return max(1, round(value * self.scale))

    @property
    def editing(self):
        """True when this edits a pixel that exists, false when it designs a new blueprint."""
        return self.info is not None

    @property
    def typing(self):
        return self.focus is not None

    @property
    def dirty(self):
        return bool(self.model.changes()) if self.editing else self.touched

    # --- geometry --------------------------------------------------------------------------------------------------

    def body_rect(self, panel):
        top = panel.y + self.px(HEADER)
        return pygame.Rect(panel.x, top, panel.width, panel.bottom - top - self.px(FOOTER))

    def footer_rects(self, panel):
        """(cancel button, save button) in the footer."""
        height, width, margin = self.px(38), self.px(110), self.px(MARGIN)
        top = panel.bottom - height - self.px(12)
        save = pygame.Rect(panel.right - margin - width, top, width, height)
        return pygame.Rect(save.x - self.px(10) - width, top, width, height), save

    def close_rect(self, panel):
        return pygame.Rect(panel.right - self.px(40), panel.y + self.px(10), self.px(30), self.px(30))

    # --- layout: the scrolling body as a list of cells ---------------------------------------------------------------

    def add(self, kind, rect, **extra):
        self.cells.append({"kind": kind, "rect": pygame.Rect(rect), **extra})

    def title(self, text):
        self.y += self.px(8)
        self.add("title", (self.margin, self.y, self.width, self.px(28)), text=text)
        self.y += self.px(36)

    def note(self, painter, text, color=theme.MUTED, size=20, x=None):
        x = self.margin if x is None else x

        for line in painter.wrap(text, self.px(size), self.width - (x - self.margin)):
            self.add("text", (x, self.y, 10, self.px(size)), text=line, color=color, size=self.px(size))
            self.y += self.px(size + 2)

    def row_label(self, text, y=None):
        self.add("text", (self.margin, (self.y if y is None else y) + self.px(8), 10, 10), text=text, color=theme.MUTED, size=self.px(22))

    def button(self, rect, label, action, hint="", active=False, enabled=True, size=22):
        self.add("button", rect, text=label, action=action, hint=hint, active=active, enabled=enabled, size=self.px(size))

    def stepper(self, label, value, minus, plus, hint="", can_minus=True, can_plus=True):
        button, right = self.px(BUTTON), self.margin + self.width
        top = self.y + self.px(3)
        self.row_label(label)
        self.button((right - button, top, button, button), "+", plus, hint, enabled=can_plus, size=26)
        self.add("value", (right - button - self.px(82), top, self.px(78), button), text=value)
        self.button((right - button - self.px(86) - button, top, button, button), "-", minus, hint, enabled=can_minus, size=26)
        self.y += self.px(ROW)

    def build(self, painter, width):
        m = self.margin = self.px(MARGIN)
        self.width = width - m * 2
        self.cells, self.y = [], self.px(4)
        model, catalog = self.model, self.model.catalog

        if not self.editing:
            self.title("Name")
            self.add("field", (m, self.y, self.width, self.px(36)), text=model.name, action=("focus", "name"), placeholder="e.g. Fast Runner", hint="Click, then type. This is also the file name.")
            self.y += self.px(44)

            self.title("Look")
            size = self.px(36)
            per_row = max(1, (self.width + self.px(8)) // (size + self.px(8)))

            for index, color in enumerate(COLORS):
                x, y = m + (index % per_row) * (size + self.px(8)), self.y + (index // per_row) * (size + self.px(8))
                self.add("swatch", (x, y, size, size), color=color, action=("color", index), active=model.color == color, hint="Pick its colour")

            self.y += ((len(COLORS) + per_row - 1) // per_row) * (size + self.px(8)) + self.px(4)
            shape_w = (self.width - self.px(6) * (len(SHAPES) - 1)) // len(SHAPES)

            for index, name in enumerate(SHAPES):
                self.button((m + index * (shape_w + self.px(6)), self.y, shape_w, self.px(34)), name, ("shape", name), "Pick its shape", active=model.shape == name, size=20)

            self.y += self.px(44)
            self.stepper("Width", f"{model.sprite_size} px", ("spx", -1), ("spx", 1), "How big it is drawn (shift-click: bigger steps)", model.sprite_size > 8, model.sprite_size < 64)

        self.title("Stats")

        for key, (label, default, _, _, whole) in STATS.items():
            low, high = model.stat_limits(key)
            hint = {"health": "How much damage it can take", "energy": "Fuel for what it does", "slots": "How many things it can carry. 0 = nothing", "size": "How many slots it takes up when carried"}[key]
            price = model.stat_price(key)
            hint += f". Costs {show_number(price)} per point more" if price else ""
            hint += ". Locked while it is being carried" if model.stat_locked(key) else ""
            free = not model.stat_locked(key)
            self.stepper(label, show_number(model.stats[key]), ("stat", key, -1), ("stat", key, 1), hint, free and model.stats[key] > low, free and model.stats[key] < high)

        if self.editing:
            self.inventory_grid(painter)

        self.title("Behaviors")

        if not catalog:
            self.note(painter, "The behavior list could not be loaded, so none can be added.", theme.BAD)

        for name, values in model.behaviors.items():
            self.behavior_block(painter, name, values)

        if not model.behaviors and catalog:
            self.note(painter, "None yet: with no behaviors a pixel just sits there. Add what it should be able to do.")
            self.y += self.px(4)

        left = model.addable()
        self.button((m, self.y, self.width, self.px(36)), "+ Add behavior" if self.picking != "behavior" else "Close the list", ("pick", "behavior"), "Everything a pixel can do", active=self.picking == "behavior", enabled=bool(left))
        self.y += self.px(44)

        if self.picking == "behavior":
            for name in left:
                entry = catalog[name]
                self.button((m + self.px(12), self.y, self.width - self.px(12), self.px(34)), f"{name}   ({entry['kind']})", ("add", name), entry.get("description", ""), size=22)
                self.y += self.px(40)

        if self.editing:
            self.y += self.px(16)
            self.total = self.y
            return

        self.title("Inventory (what it starts with)")

        for item, count in model.inventory.items():
            self.stepper(prettify(item), str(count), ("item", item, -1), ("item", item, 1), "Going below 1 removes it (shift-click: steps of 5)")

        if not model.inventory:
            self.note(painter, "Empty. It also needs slots above to hold anything.")
            self.y += self.px(4)

        left_items = model.items_left()
        self.button((m, self.y, self.width, self.px(36)), "+ Add item" if self.picking != "item" else "Close the list", ("pick", "item"), "Resources it starts with", active=self.picking == "item", enabled=bool(left_items))
        self.y += self.px(44)

        if self.picking == "item":
            half = (self.width - self.px(6)) // 2

            for index, item in enumerate(left_items):
                self.button((m + (index % 2) * (half + self.px(6)), self.y + (index // 2) * self.px(40), half, self.px(34)), prettify(item), ("add_item", item), size=22)

            self.y += ((len(left_items) + 1) // 2) * self.px(40)

        self.y += self.px(16)
        self.total = self.y

    def inventory_grid(self, painter):
        """One box per slot (the pixel's capacity, which follows the Slots stepper above), filled in order with what it holds."""
        model, m = self.model, self.margin
        held = (self.info or {}).get("contents", [])
        capacity = max(model.stats["slots"], len(held))
        self.title(f"Inventory   {len(held)} / {model.stats['slots']}")
        size, gap = self.px(42), self.px(6)
        per_row = max(1, (self.width + gap) // (size + gap))

        for index in range(capacity):
            x, y = m + (index % per_row) * (size + gap), self.y + (index // per_row) * (size + gap)
            entry = held[index] if index < len(held) else None
            self.add("slot", (x, y, size, size), entry=entry, over=index >= model.stats["slots"], tip=entry["label"] if entry else "Empty slot")

        if capacity:
            self.y += ((capacity + per_row - 1) // per_row) * (size + gap)
        else:
            self.note(painter, "No slots: it cannot carry anything. Raise Slots above.")

        if capacity and not held:
            self.note(painter, "Empty. Use Pick up and Drop to move things around.")

    def behavior_block(self, painter, name, values):
        model, entry, m = self.model, self.model.catalog[name], self.margin
        self.y += self.px(6)
        self.add("line", (m, self.y, self.width, 1))
        self.y += self.px(8)
        self.add("text", (m, self.y + self.px(4), 10, 10), text=prettify(name), color=theme.TEXT, size=self.px(28))
        self.add("text", (m + self.px(130), self.y + self.px(9), 10, 10), text=f"cost {show_number(round(entry['base_cost'], 2))}", color=theme.MUTED, size=self.px(20))
        needed = model.required_by(name)

        if model.removable(name):
            self.button((m + self.width - self.px(88), self.y, self.px(88), self.px(32)), "Remove", ("remove", name), "Also removes: " + ", ".join(needed) if needed else "Take this behavior out", size=20)

        self.y += self.px(38)
        self.note(painter, entry.get("description", ""))
        self.y += self.px(4)

        for key, spec in entry["params"].items():
            kind, value = kind_of(spec), values.get(key)
            hint = spec.get("description", "")
            label = prettify(key)

            if kind == "number":
                low, high = spec["minimum"], spec["maximum"]
                self.stepper(label, show_number(value), ("param", name, key, -1), ("param", name, key, 1), hint, value is not None and (low is None or value > low or spec["default"] is None), high is None or value is None or value < high)
            else:
                self.row_label(label)
                right, top = m + self.width, self.y + self.px(3)

                if kind == "toggle":
                    self.button((right - self.px(86), top, self.px(86), self.px(30)), "On" if value else "Off", ("toggle", name, key), hint, active=bool(value), size=22)
                elif kind == "choice":
                    self.button((right - self.px(170), top, self.px(170), self.px(30)), str(value), ("cycle", name, key), hint + " (click to change)", size=22)
                else:
                    self.add("field", (right - self.px(170), top, self.px(170), self.px(30)), text=str(value or ""), action=("focus", ("param", name, key)), placeholder="(none)", hint=hint)

                self.y += self.px(ROW)

    # --- reading the layout back as clickable zones ------------------------------------------------------------------

    def refresh(self, painter, panel):
        body = self.body_rect(panel)
        self.build(painter, body.width)
        self.scroll = max(0, min(self.scroll, self.total - body.height))
        self.zones = []

        for cell in self.cells:
            if cell.get("action") is not None and cell.get("enabled", True):
                rect = cell["rect"].move(body.x, body.y - self.scroll).clip(body)

                if rect.width > 0 and rect.height > 0:
                    self.zones.append((rect, cell["action"], cell.get("hint", "")))

        cancel, save = self.footer_rects(panel)
        if not self.editing or self.model.changes():
            self.zones.append((save, ("save",), "Pay for the changes and apply them" if self.editing else "Save it with the other blueprints"))

        away = "Close without applying" if self.editing else "Throw this design away"
        self.zones.append((cancel, ("cancel",), away))
        self.zones.append((self.close_rect(panel), ("cancel",), away))
        return body

    def zone_at(self, pos):
        return next((zone for zone in reversed(self.zones) if zone[0].collidepoint(pos)), None)

    # --- doing things --------------------------------------------------------------------------------------------------

    def say(self, text, good=False):
        self.status, self.status_good = text, good

    def request_close(self):
        """Asks to close. A design with changes needs a second request (Esc, X or Cancel again)."""
        if self.dirty and not self.confirm_close and not self.saving:
            self.confirm_close = True
            self.say("Not applied yet. Press Cancel again to drop the changes." if self.editing else "Not saved yet. Press Cancel again to throw it away.")
            return

        self.close_requested = True

    def act(self, action, shift=False):
        model, factor = self.model, 5 if shift else 1
        what = action[0]

        if what == "cancel":
            self.request_close()
            return

        self.confirm_close = False

        if what != "save":
            self.status = ""

        if what == "focus":
            self.focus = action[1]
            return

        self.focus = None
        self.touched = True if what != "pick" else self.touched

        if what == "save" and self.editing:
            changes = model.changes()

            if changes and not self.saving:
                self.edit_request = (self.info["id"], changes)
                self.saving = True
                self.say("Applying...", True)
        elif what == "save":
            problems = model.problems()

            if problems:
                self.say(problems[0])
            elif not self.saving:
                self.save_request = (model.clean_name(), model.definition())
                self.saving = True
                self.say("Saving...", True)
        elif what == "color":
            model.color = COLORS[action[1]]
        elif what == "shape":
            model.shape = action[1]
        elif what == "spx":
            model.nudge_size(action[1], factor)
        elif what == "stat":
            model.nudge_stat(action[1], action[2], factor)
        elif what == "pick":
            self.picking = None if self.picking == action[1] else action[1]
        elif what == "add":
            model.add_behavior(action[1])
            self.picking = "behavior" if model.addable() else None
        elif what == "remove":
            removed = model.remove_behavior(action[1])

            if len(removed) > 1:
                self.say("Also removed: " + ", ".join(removed[1:]) + " (they need it)")
        elif what == "toggle":
            model.toggle(action[1], action[2])
        elif what == "cycle":
            model.cycle(action[1], action[2])
        elif what == "param":
            model.nudge(action[1], action[2], action[3], factor)
        elif what == "add_item":
            model.add_item(action[1])
            self.picking = "item" if model.items_left() else None
        elif what == "item":
            model.nudge_item(action[1], action[2], factor)

    def key(self, event):
        """A key while a field has focus. Always used, so typing never moves the camera."""
        if event.type != pygame.KEYDOWN:
            return True

        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_TAB):
            self.focus = None
            return True

        self.touched = True
        self.confirm_close = False
        self.status = ""
        model, focus = self.model, self.focus

        if event.key == pygame.K_BACKSPACE:
            if focus == "name":
                model.name = model.name[:-1]
            else:
                model.backspace_param(focus[1], focus[2])
        elif event.unicode and event.unicode.isprintable():
            if focus == "name":
                model.type_name(event.unicode)
            else:
                model.type_param(focus[1], focus[2], event.unicode)

        return True

    def handle_event(self, event, panel, painter):
        """Returns True if the editor used the event."""
        if self.focus is not None and event.type in (pygame.KEYDOWN, pygame.KEYUP):
            return self.key(event)

        body = self.refresh(painter, panel)
        pos = getattr(event, "pos", None)

        if event.type == getattr(pygame, "MOUSEWHEEL", None):
            if not panel.collidepoint(pygame.mouse.get_pos()):
                return False

            self.scroll = max(0, min(self.total - body.height, self.scroll - event.y * self.px(48)))
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and pos is not None and panel.collidepoint(pos):
            if event.button == 1:
                zone = self.zone_at(pos)
                self.pressed = zone[1] if zone else None

                if zone is None:
                    self.focus = None

            return True

        if event.type == pygame.MOUSEBUTTONUP and pos is not None:
            pressed, self.pressed = (self.pressed, None) if event.button == 1 else (None, self.pressed)
            zone = self.zone_at(pos)

            if pressed is not None and zone is not None and zone[1] == pressed:
                self.act(pressed, bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))

            return panel.collidepoint(pos)

        return False

    # --- drawing -------------------------------------------------------------------------------------------------------

    def draw_preview(self, surface, rect):
        model = self.model
        pygame.draw.rect(surface, theme.PANEL_DARK, rect, border_radius=self.px(8))
        pygame.draw.rect(surface, theme.BORDER, rect, width=2, border_radius=self.px(8))
        reach = rect.width * 0.38 * (0.45 + 0.55 * (model.sprite_size - 8) / 56)
        points = [(rect.centerx + x * 2 * reach, rect.centery + y * 2 * reach) for x, y in SHAPES[model.shape]]
        pygame.draw.polygon(surface, model.color, points)
        pygame.draw.polygon(surface, theme.TEXT, points, 1)

    def draw(self, surface, painter, panel):
        body, mouse, margin = self.refresh(painter, panel), pygame.mouse.get_pos(), self.px(MARGIN)
        model = self.model
        pygame.draw.rect(surface, theme.PANEL, panel)
        pygame.draw.line(surface, theme.BORDER, panel.topleft, panel.bottomleft, 2)

        preview = pygame.Rect(panel.x + margin, panel.y + self.px(16), self.px(52), self.px(52))
        self.draw_preview(surface, preview)
        close, text_x = self.close_rect(panel), preview.right + self.px(14)
        title = model.clean_name() or "New blueprint"
        subtitle = f"Pixel #{self.info['id']}  |  upgrade it here" if self.editing else "Blueprint  |  designing"
        painter.text(surface, title, (text_x, panel.y + self.px(18)), size=self.px(32), color=theme.TEXT if model.clean_name() else theme.MUTED, max_width=close.x - text_x - self.px(8))
        painter.text(surface, subtitle, (text_x, panel.y + self.px(48)), size=self.px(22), color=theme.MUTED, max_width=close.x - text_x - self.px(8))
        draw_button(surface, painter, close, "X", hovered=close.collidepoint(mouse), size=self.px(24))
        pygame.draw.line(surface, theme.BORDER, (panel.x, panel.y + self.px(HEADER) - 1), (panel.right, panel.y + self.px(HEADER) - 1), 1)

        self.hint = ""
        surface.set_clip(body)

        for cell in self.cells:
            rect = cell["rect"].move(body.x, body.y - self.scroll)

            if rect.bottom < body.y or rect.y > body.bottom:
                continue

            hovered = (cell.get("action") is not None or "tip" in cell) and cell.get("enabled", True) and rect.collidepoint(mouse) and body.collidepoint(mouse)

            if hovered:
                self.hint = cell.get("hint", cell.get("tip", ""))

            self.draw_cell(surface, painter, cell, rect, hovered)

        surface.set_clip(None)

        if self.total > body.height:
            track = pygame.Rect(panel.right - self.px(6), body.y, self.px(4), body.height)
            thumb_h = max(self.px(24), int(track.height * body.height / self.total))
            thumb_y = track.y + int((track.height - thumb_h) * self.scroll / max(1, self.total - body.height))
            pygame.draw.rect(surface, theme.PANEL_LIGHT, track, border_radius=2)
            pygame.draw.rect(surface, theme.BORDER, pygame.Rect(track.x, thumb_y, track.width, thumb_h), border_radius=2)

        self.draw_footer(surface, painter, panel, mouse)

    def draw_cell(self, surface, painter, cell, rect, hovered):
        kind = cell["kind"]

        if kind == "title":
            painter.text(surface, cell["text"], rect.topleft, size=self.px(24), color=theme.ACCENT)
            pygame.draw.line(surface, theme.BORDER, (rect.x, rect.y + self.px(27)), (rect.right, rect.y + self.px(27)), 1)
        elif kind == "text":
            painter.text(surface, cell["text"], rect.topleft, size=cell["size"], color=cell["color"])
        elif kind == "line":
            pygame.draw.line(surface, theme.BORDER, rect.topleft, rect.topright, 1)
        elif kind == "value":
            painter.text(surface, cell["text"], rect.center, size=self.px(24), center=True, max_width=rect.width)
        elif kind == "button":
            draw_button(surface, painter, rect, cell["text"], hovered=hovered, active=cell["active"], enabled=cell["enabled"], size=cell["size"])
        elif kind == "slot":
            entry = cell["entry"]
            pygame.draw.rect(surface, theme.PANEL_DARK if not cell["over"] else theme.mix(theme.BAD, theme.PANEL_DARK, 0.7), rect, border_radius=self.px(6))
            pygame.draw.rect(surface, theme.ACCENT if hovered else theme.BORDER, rect, width=2, border_radius=self.px(6))

            if entry is not None:
                color = self.sprite_color(entry["key"]) if entry["kind"] == "pixel" and self.sprite_color is not None else None
                draw_icon(surface, painter, rect, entry["kind"], entry["key"], color)

                if entry["kind"] == "resource" and entry.get("amount", 1) != 1:
                    painter.text(surface, f"{entry['amount']:g}", (rect.right - self.px(4), rect.bottom - self.px(4)), size=self.px(18), color=theme.TEXT, center=True)
        elif kind == "swatch":
            pygame.draw.rect(surface, cell["color"], rect, border_radius=self.px(6))
            pygame.draw.rect(surface, theme.TEXT if cell["active"] else (theme.ACCENT if hovered else theme.BORDER), rect, width=3 if cell["active"] else 2, border_radius=self.px(6))
        elif kind == "field":
            focused = self.focus == cell["action"][1]
            pygame.draw.rect(surface, theme.PANEL_DARK, rect, border_radius=self.px(6))
            pygame.draw.rect(surface, theme.ACCENT if focused or hovered else theme.BORDER, rect, width=2, border_radius=self.px(6))
            text = cell["text"]
            caret = "|" if focused and int(time.monotonic() / CARET_BLINK) % 2 == 0 else ""
            size, pad = self.px(24), self.px(10)

            if text or focused:
                painter.text(surface, text + caret, (rect.x + pad, rect.centery - self.px(8)), size=size, max_width=rect.width - pad * 2)
            else:
                painter.text(surface, cell["placeholder"], (rect.x + pad, rect.centery - self.px(8)), size=size, color=theme.DISABLED, max_width=rect.width - pad * 2)

    def draw_footer(self, surface, painter, panel, mouse):
        margin, model = self.px(MARGIN), self.model
        top = panel.bottom - self.px(FOOTER)
        pygame.draw.rect(surface, theme.PANEL_DARK, pygame.Rect(panel.x, top, panel.width, self.px(FOOTER)))
        pygame.draw.line(surface, theme.BORDER, (panel.x, top), (panel.right, top), 1)
        text, color = (self.status, theme.GOOD if self.status_good else theme.BAD) if self.status else (self.hint, theme.MUTED)
        painter.text(surface, text, (panel.x + margin, top + self.px(8)), size=self.px(20), color=color, max_width=panel.width - margin * 2)
        cancel, save = self.footer_rects(panel)
        if self.editing:
            painter.text(surface, f"Cost {show_number(round(model.upgrade_cost(), 2))}", (panel.x + margin, cancel.y + self.px(2)), size=self.px(24), max_width=cancel.x - panel.x - margin * 2)
            ready = bool(model.changes())
            label = "Applying..." if self.saving else "Apply"
        else:
            painter.text(surface, f"Cost {show_number(round(model.cost(), 2))}", (panel.x + margin, cancel.y + self.px(2)), size=self.px(24))
            ready, label = True, "Saving..." if self.saving else "Save"

        painter.text(surface, "free for now", (panel.x + margin, cancel.y + self.px(21)), size=self.px(18), color=theme.MUTED)
        draw_button(surface, painter, cancel, "Close" if self.editing else "Cancel", hovered=cancel.collidepoint(mouse), size=self.px(24))
        draw_button(surface, painter, save, label, hovered=save.collidepoint(mouse), active=ready and not self.saving, enabled=ready and not self.saving, size=self.px(24))