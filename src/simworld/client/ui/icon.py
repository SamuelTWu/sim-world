"""Pictures for things held in an inventory.

PLACEHOLDERS for now: a resource is a coloured tile with its first letter, a pixel is a tile in its sprite colour with a dot.
This is the one place to change when real pictures exist: `draw_icon(surface, painter, rect, kind, key, color)` is called with
kind "resource" (key = the resource name) or "pixel" (key = the pixel's sprite id), and should draw inside `rect`. Later it can
draw the item's sprite (resources and pixels alike) instead.
"""
import hashlib

import pygame

from src.simworld.client.ui import theme


def placeholder_color(name):
    """The same name always gets the same colour: a muted tone picked from a hash."""
    digest = hashlib.md5(str(name).encode("utf-8")).digest()
    return tuple(90 + digest[index] % 130 for index in range(3))


def draw_icon(surface, painter, rect, kind, key, color=None):
    tile = color if color is not None else placeholder_color(key)
    inner = rect.inflate(-max(4, rect.width // 6), -max(4, rect.height // 6))
    pygame.draw.rect(surface, tile, inner, border_radius=max(3, inner.width // 5))
    pygame.draw.rect(surface, theme.mix(tile, theme.TEXT, 0.45), inner, width=2, border_radius=max(3, inner.width // 5))

    if kind == "pixel":
        pygame.draw.circle(surface, theme.mix(tile, theme.PANEL_DARK, 0.65), inner.center, max(3, inner.width // 5))
    else:
        painter.text(surface, str(key)[:1].upper() or "?", inner.center, size=max(14, inner.height), color=theme.PANEL_DARK, center=True)