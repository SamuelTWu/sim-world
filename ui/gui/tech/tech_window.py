import pygame

from tech.tech import TechTreeError, load_tree
from .. import theme
from ..tree_layout import layout_tree
from ..window import Window

DETAIL_HEIGHT = 92
DRAG_THRESHOLD = 4


def cost_text(node):
    if not node.cost:
        return "Free"

    return ", ".join(f"{int(amount) if float(amount).is_integer() else amount} {currency}" for currency, amount in node.cost.items())


class TechWindow(Window):
    """Shows the whole tech tree: one lane per kind, one column per tier, arrows from requirement to unlock.

    Drag the background to pan, use the mouse wheel to scroll (hold Shift to scroll sideways). The Reload button
    re-reads the JSON files, so you can edit a node and see it without restarting. Nodes are only drawn for now;
    `on_node_clicked` is where buying a tech will go.
    """

    title = "Tech Tree"
    size = (1100, 720)
    extra_header = (("reload", "Reload"),)

    def __init__(self):
        super().__init__()
        self.scale = 1.0
        self.tree = None
        self.error = None
        self.owned = set()
        self.layout = None
        self.layout_scale = None
        self.scroll = [0, 0]
        self.hover = None
        self.pan = None
        self.load()

    def load(self):
        self.layout = None

        try:
            self.tree = load_tree()
            self.error = None
        except TechTreeError as problem:
            self.tree, self.error = None, str(problem)
        except Exception as problem:
            self.tree, self.error = None, f"Could not load the tech tree: {problem}"

        self.owned = {node.id for node in self.tree.starting()} if self.tree else set()
        self.hover = None
        self.pan = None

    def px(self, value):
        return max(1, round(value * self.scale))

    def current_layout(self):
        if self.layout is None or self.layout_scale != self.scale:
            s = self.px
            self.layout = layout_tree(self.tree, node_w=s(190), node_h=s(62), gap_x=s(70), gap_y=s(14), pad=s(14), label_w=s(110), lane_gap=s(8))
            self.layout_scale = self.scale

        return self.layout

    def view_rect(self):
        content = self.content_rect()
        return pygame.Rect(content.x, content.y, content.width, content.height - self.px(DETAIL_HEIGHT))

    def clamp_scroll(self):
        if not self.tree:
            return

        layout, view = self.current_layout(), self.view_rect()
        margin = self.px(14)
        min_x = min(0, view.width - layout.width - margin)
        min_y = min(0, view.height - layout.height - margin)
        self.scroll[0] = max(min_x, min(0, self.scroll[0]))
        self.scroll[1] = max(min_y, min(0, self.scroll[1]))

    def origin(self):
        view = self.view_rect()
        return view.x + self.px(6) + self.scroll[0], view.y + self.px(8) + self.scroll[1]

    def node_at(self, pos):
        if not self.tree or not self.view_rect().collidepoint(pos):
            return None

        ox, oy = self.origin()
        x, y = pos[0] - ox, pos[1] - oy

        for node_id, box in self.current_layout().boxes.items():
            if box.contains(x, y):
                return self.tree.get(node_id)

        return None

    def on_node_clicked(self, node):
        """Called when a tech is clicked (not dragged). Does nothing yet: buying goes here."""

    def on_action(self, action):
        if action == "reload":
            self.load()
            self.scroll = [0, 0]

    def on_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.view_rect().collidepoint(event.pos):
                self.pan = {"start": event.pos, "scroll": tuple(self.scroll), "moved": False}

            return True

        if event.type == pygame.MOUSEMOTION:
            self.hover = self.node_at(event.pos) if self.rect.collidepoint(event.pos) else None

            if self.pan is None:
                return False

            dx, dy = event.pos[0] - self.pan["start"][0], event.pos[1] - self.pan["start"][1]

            if self.pan["moved"] or abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD:
                self.pan["moved"] = True
                self.scroll = [self.pan["scroll"][0] + dx, self.pan["scroll"][1] + dy]
                self.clamp_scroll()

            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pan, self.pan = self.pan, None

            if pan is not None and not pan["moved"]:
                node = self.node_at(event.pos)

                if node is not None:
                    self.on_node_clicked(node)

            return True

        if event.type == getattr(pygame, "MOUSEWHEEL", None):
            if not self.view_rect().collidepoint(pygame.mouse.get_pos()):
                return False

            step = self.px(48)
            sideways = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
            self.scroll[0] += event.x * step + (event.y * step if sideways else 0)
            self.scroll[1] += 0 if sideways else event.y * step
            self.clamp_scroll()
            return True

        return False

    def reset_input(self):
        self.pan = None
        self.pressed = False
        self.drag_offset = None

    def draw_content(self, surface, painter, rect):
        if self.tree is None:
            self.draw_error(surface, painter, rect)
            return

        self.clamp_scroll()
        view = self.view_rect()
        surface.set_clip(view)
        self.draw_tree(surface, painter, view)
        surface.set_clip(None)
        self.draw_details(surface, painter, pygame.Rect(rect.x, view.bottom, rect.width, rect.bottom - view.bottom))

    def draw_error(self, surface, painter, rect):
        y = rect.y + self.px(16)
        painter.text(surface, "The tech tree has problems. Fix the JSON files, then press Reload.", (rect.x + self.px(16), y), size=self.px(26), color=theme.BAD, max_width=rect.width - self.px(32))
        y += self.px(40)

        for line in (self.error or "").splitlines():
            for part in painter.wrap(line, self.px(22), rect.width - self.px(32)) or [""]:
                if y > rect.bottom - self.px(24):
                    return

                painter.text(surface, part, (rect.x + self.px(16), y), size=self.px(22), color=theme.TEXT)
                y += self.px(24)

    def draw_tree(self, surface, painter, view):
        layout, tree = self.current_layout(), self.tree
        ox, oy = self.origin()
        wide = max(layout.width, view.width - self.px(12))

        for kind, lane in layout.lanes.items():
            color = theme.KIND_COLORS[kind]
            area = pygame.Rect(ox + lane.x, oy + lane.y, wide, lane.h)
            pygame.draw.rect(surface, theme.mix(color, theme.PANEL_DARK, 0.9), area, border_radius=self.px(8))
            painter.text(surface, kind.capitalize(), (area.x + self.px(14), area.y + self.px(12)), size=self.px(26), color=color)
            count = sum(1 for node in tree.by_kind(kind) if node.id in self.owned)
            painter.text(surface, f"{count}/{len(tree.by_kind(kind))}", (area.x + self.px(14), area.y + self.px(40)), size=self.px(20), color=theme.MUTED)

        for required, node_id in layout.edges:
            self.draw_edge(surface, layout.boxes[required], layout.boxes[node_id], tree.get(node_id), ox, oy)

        for node_id, box in layout.boxes.items():
            node = tree.get(node_id)
            self.draw_node(surface, painter, node, pygame.Rect(ox + box.x, oy + box.y, box.w, box.h))

    def draw_edge(self, surface, start, end, node, ox, oy):
        color = theme.KIND_COLORS[node.kind]
        owned = node.id in self.owned
        line = theme.mix(color, theme.PANEL, 0.15 if owned else 0.6)
        x1, y1 = ox + start.x + start.w, oy + start.y + start.h // 2
        x2, y2 = ox + end.x, oy + end.y + end.h // 2
        bend = x2 - self.px(35)
        pygame.draw.lines(surface, line, False, [(x1, y1), (bend, y1), (bend, y2), (x2 - self.px(2), y2)], max(2, self.px(2)))
        size = self.px(6)
        pygame.draw.polygon(surface, line, [(x2, y2), (x2 - size * 2, y2 - size), (x2 - size * 2, y2 + size)])

    def draw_node(self, surface, painter, node, rect):
        color = theme.KIND_COLORS[node.kind]
        owned = node.id in self.owned
        hovered = self.hover is not None and self.hover.id == node.id
        fill = theme.mix(color, theme.PANEL, 0.55) if owned else theme.PANEL_LIGHT
        border = theme.ACCENT if hovered else (color if owned else theme.mix(color, theme.PANEL, 0.5))
        pygame.draw.rect(surface, fill, rect, border_radius=self.px(8))
        pygame.draw.rect(surface, border, rect, width=self.px(3) if hovered else 2, border_radius=self.px(8))
        pad = self.px(10)
        painter.text(surface, node.name, (rect.x + pad, rect.y + self.px(9)), size=self.px(26), color=theme.TEXT if owned else theme.mix(theme.TEXT, theme.PANEL, 0.2), max_width=rect.width - pad * 2)
        status, status_color = ("Unlocked", theme.GOOD) if owned else (cost_text(node), theme.MUTED)
        painter.text(surface, status, (rect.x + pad, rect.y + self.px(36)), size=self.px(21), color=status_color, max_width=rect.width - pad * 2)

    def draw_details(self, surface, painter, rect):
        pygame.draw.rect(surface, theme.PANEL_DARK, rect)
        pygame.draw.line(surface, theme.BORDER, rect.topleft, rect.topright, 2)
        x, y, width = rect.x + self.px(14), rect.y + self.px(8), rect.width - self.px(28)
        node = self.hover

        if node is None:
            painter.text(surface, "Hover a tech for details. Drag to move around, scroll wheel to scroll (Shift for sideways).", (x, y + self.px(4)), size=self.px(22), color=theme.MUTED, max_width=width)
            return

        color = theme.KIND_COLORS[node.kind]
        size = self.px(26)
        painter.text(surface, node.name, (x, y), size=size, color=color)
        meta_x = x + painter.measure(node.name, size)[0] + self.px(16)
        meta = f"{node.kind}  |  " + ("Unlocked" if node.id in self.owned else "Cost: " + cost_text(node))
        painter.text(surface, meta, (meta_x, y + self.px(5)), size=self.px(21), color=theme.MUTED, max_width=max(40, x + width - meta_x))
        y += painter.measure(node.name, size)[1]
        lines = painter.wrap(node.description, self.px(21), width)[:1] if node.description else []
        requires = ", ".join(self.tree.get(required).name for required in node.requires) or "nothing"
        provides = "; ".join(f"{category}: {', '.join(names)}" for category, names in node.provides.items()) or "nothing"
        lines += [f"Requires: {requires}", f"Provides: {provides}"]

        for line in lines:
            y += painter.text(surface, line, (x, y), size=self.px(21), color=theme.TEXT, max_width=width)