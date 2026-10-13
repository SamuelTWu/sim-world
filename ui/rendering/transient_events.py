"""Draws transient events (shots, impacts) that the server only SAID happened (README 8.3). Pure drawing: no game imports.

The server sends "kind, type, from, to" for something that was seen; this animates it here, on the client, for a fraction of a
second, and forgets it. A kind it does not know is ignored. Add a look by adding a function to DRAWERS (kind -> drawer) and, for
different looks of one kind, a row in SHOT_STYLES / HIT_STYLES (type -> style).

An transient event is a plain dict from Client.take_transient_events(): {"kind", "type", "from": (x, y), "to": (x, y)} in world units.
"""
import math

import pygame

MAX_TRANSIENT_EVENTS = 64

# shot type -> (color, speed in world units per second, streak length in world units, thickness in screen pixels)
SHOT_STYLES = {
    "arrow": ((255, 235, 160), 1400.0, 90.0, 2),
    "bolt": ((140, 200, 255), 1800.0, 120.0, 3),
}
DEFAULT_SHOT = ((255, 255, 255), 1200.0, 80.0, 2)

# hit type -> (color, duration in seconds, final radius in world units)
HIT_STYLES = {
    "melee": ((255, 120, 90), 0.25, 26.0),
}
DEFAULT_HIT = ((255, 255, 255), 0.25, 22.0)

MIN_SHOT_SECONDS = 0.06
MAX_SHOT_SECONDS = 0.6


class TransientEvents:
    def __init__(self):
        self.items = []

    def add(self, events, now):
        """Start animating the transient events the client just handed over (see Client.take_transient_events). `now` is the client clock in seconds."""
        for event in events:
            item = start(event, now)

            if item is not None:
                self.items.append(item)

        del self.items[:-MAX_TRANSIENT_EVENTS]

    def draw(self, surface, camera, now):
        """Draw every running transient event and drop the finished ones."""
        self.items = [item for item in self.items if now - item["born"] < item["life"]]

        for item in self.items:
            DRAWERS[item["kind"]](surface, camera, item, (now - item["born"]) / item["life"])

    def clear(self):
        self.items = []


def start(event, now):
    kind = event.get("kind")

    if kind not in DRAWERS:
        return None

    (x0, y0), (x1, y1) = event["from"], event["to"]

    if kind == "fired":
        color, speed, length, width = SHOT_STYLES.get(event.get("type"), DEFAULT_SHOT)
        distance = math.hypot(x1 - x0, y1 - y0)
        life = min(MAX_SHOT_SECONDS, max(MIN_SHOT_SECONDS, distance / speed))
        return {"kind": kind, "born": now, "life": life, "from": (x0, y0), "to": (x1, y1), "color": color, "length": length, "width": width}

    color, life, radius = HIT_STYLES.get(event.get("type"), DEFAULT_HIT)
    return {"kind": kind, "born": now, "life": life, "from": (x0, y0), "to": (x1, y1), "color": color, "radius": radius}


def draw_fired(surface, camera, item, progress):
    """A short streak that flies from the shooter to the target."""
    (x0, y0), (x1, y1) = item["from"], item["to"]
    distance = math.hypot(x1 - x0, y1 - y0)

    if distance <= 0:
        return

    head = progress * (distance + item["length"])
    tail = max(0.0, head - item["length"])
    head = min(head, distance)
    ux, uy = (x1 - x0) / distance, (y1 - y0) / distance
    start_point = camera.world_to_screen(x0 + ux * tail, y0 + uy * tail)
    end_point = camera.world_to_screen(x0 + ux * head, y0 + uy * head)
    pygame.draw.line(surface, item["color"], (round(start_point[0]), round(start_point[1])), (round(end_point[0]), round(end_point[1])), item["width"])


def draw_hit(surface, camera, item, progress):
    """A ring that grows and fades where something was hit."""
    x, y = camera.world_to_screen(*item["to"])
    radius = max(2, round(item["radius"] * camera.zoom * (0.3 + 0.7 * progress)))
    fade = 1.0 - progress
    color = tuple(round(channel * fade) for channel in item["color"])
    pygame.draw.circle(surface, color, (round(x), round(y)), radius, width=max(1, round(3 * fade)))


DRAWERS = {"fired": draw_fired, "hit": draw_hit}