"""Optimistic hints: what the player just asked for, drawn at once, before the server has answered.

The server is the only authority, so a hint is a guess that is corrected as soon as the truth arrives:
    place   a faint copy of the blueprint at the drop spot ("placing..."). It goes away when the new pixel shows up in the
            server's updates (the correction: the real pixel replaces the guess), when the server refuses (the notice says why),
            or after TIMEOUT seconds if nothing came back.
    orders  (move, spawn, drop, ...) a ring at the clicked spot with the action's name. It turns green when the server accepts
            the command, and fades. If the server refuses, it vanishes. If the pixel later gives up, the game shows a notice.
Hints are keyed by the command's seq: `add(seq, ...)` when it is sent, `result(seq, ok)` when the server answers.
They never change the game, only what is drawn.
"""
import math
import time

import pygame

from src.simworld.client.ui.gui import theme
from .sprites import get_sprite

TIMEOUT = 5.0
ACCEPTED_SECONDS = 0.8
MAX_HINTS = 32


class Hints:
    def __init__(self):
        self.items = []
        self.known = None

    def clear(self):
        self.items.clear()
        self.known = None

    def add(self, seq, kind, point, key=None, label="", now=None):
        """kind "place" (key = blueprint id) or "order" (label = what to show next to the ring). point is in world units."""
        now = time.monotonic() if now is None else now

        if len(self.items) >= MAX_HINTS:
            self.items.pop(0)

        self.items.append({"seq": seq, "kind": kind, "point": tuple(point), "key": key, "label": label, "born": now, "accepted": None})

    def result(self, seq, ok, now=None):
        """The server answered command `seq`. Accepted orders turn green and fade; a refused one vanishes; an accepted place waits for its pixel."""
        now = time.monotonic() if now is None else now

        for item in list(self.items):
            if item["seq"] == seq:
                if not ok:
                    self.items.remove(item)
                elif item["kind"] == "order":
                    item["accepted"] = now
                else:
                    item["born"] = now  # the pixel is on its way: wait for it again

    def update(self, entities, now=None, player_id=None):
        """Drop what has been answered or has run out of time. `entities` are the pixels the client knows: a NEW one of the player's own settles the oldest place hint (other players' pixels come into view too)."""
        now = time.monotonic() if now is None else now
        ids = {entity.id for entity in entities if player_id is None or entity.owner == player_id}

        if self.known is not None:
            for _ in ids - self.known:
                placed = next((item for item in self.items if item["kind"] == "place"), None)

                if placed is not None:
                    self.items.remove(placed)

        self.known = ids
        self.items = [item for item in self.items if now - item["born"] < TIMEOUT and (item["accepted"] is None or now - item["accepted"] < ACCEPTED_SECONDS)]

    def draw(self, surface, camera, gui, now=None):
        now = time.monotonic() if now is None else now
        painter, px = gui.painter, gui.px

        for item in self.items:
            x, y = camera.world_to_screen(*item["point"])
            x, y = round(x), round(y)

            if item["kind"] == "place":
                sprite = get_sprite(item["key"])
                half = max(px(8), round(max(sprite.size) * camera.zoom / 2))
                ghost = pygame.Surface((half * 2, half * 2), pygame.SRCALPHA)
                ghost.fill((*sprite.color, 110))
                surface.blit(ghost, (x - half, y - half))
                pygame.draw.rect(surface, theme.ACCENT, pygame.Rect(x - half, y - half, half * 2, half * 2), width=max(1, px(2)))
                painter.text(surface, "placing...", (x, y + half + px(12)), size=px(20), color=theme.MUTED, center=True)
                continue

            accepted = item["accepted"] is not None
            color = theme.GOOD if accepted else theme.ACCENT
            radius = px(12) + (0 if accepted else round(px(4) * (1 + math.sin((now - item["born"]) * 8))))
            pygame.draw.circle(surface, color, (x, y), radius, width=max(1, px(2)))
            pygame.draw.circle(surface, color, (x, y), max(2, px(3)))

            if item["label"]:
                painter.text(surface, item["label"], (x, y + px(26)), size=px(20), color=color, center=True)