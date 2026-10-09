"""Lays a tech tree out on a plain grid. No pygame here, so it can be tested and reused.

One lane per kind (body, sense, action, reaction), stacked top to bottom. Columns are tiers, left to right, so
every requirement is to the left of what needs it. Inside a lane, nodes in the same tier are stacked in the
order they appear in the JSON files, so you control the order by moving a node up or down in its file.
"""
from dataclasses import dataclass, field

from tech.tech import KINDS


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    def contains(self, px, py):
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


@dataclass
class TreeLayout:
    boxes: dict = field(default_factory=dict)
    lanes: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    width: int = 0
    height: int = 0


def layout_tree(tree, node_w=190, node_h=62, gap_x=70, gap_y=14, pad=14, label_w=120, lane_gap=8):
    layout = TreeLayout()
    max_tier = max((tree.tier(node_id) for node_id in tree.nodes), default=0)
    layout.width = label_w + pad * 2 + (max_tier + 1) * node_w + max_tier * gap_x
    y = 0

    for kind in KINDS:
        columns = {}

        for node in tree.by_kind(kind):
            columns.setdefault(tree.tier(node.id), []).append(node)

        if not columns:
            continue

        rows = max(len(column) for column in columns.values())
        lane_h = pad * 2 + rows * node_h + (rows - 1) * gap_y
        layout.lanes[kind] = Box(0, y, layout.width, lane_h)

        for tier, column in columns.items():
            for row, node in enumerate(column):
                layout.boxes[node.id] = Box(label_w + pad + tier * (node_w + gap_x), y + pad + row * (node_h + gap_y), node_w, node_h)

        y += lane_h + lane_gap

    layout.height = max(0, y - lane_gap)
    layout.edges = [(required, node.id) for node in tree.nodes.values() for required in node.requires]
    return layout