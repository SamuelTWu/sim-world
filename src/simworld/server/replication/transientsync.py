"""Which transient events (shots, impacts: entity/system/transientEvents.py) each client is told about, as small wire events. No networking, so it can be tested.

A client gets a transient event when it happens where the client is looking (interest.in_area) and does not involve a pixel hidden from that
client (an invisible pixel or a spy shooting, or being shot, must not show itself through the transient event). Nothing about it names a pixel.
"""
from src.simworld.sim.visibility import is_hidden

from src.simworld.shared import protocol as proto
from .interest import in_area

MAX_TRANSIENT_PER_MESSAGE = 64


def transient_events_for(transients, viewer, own_pixels, view, grid, margin=0.0):
    """The wire events from this tick's transient events that `viewer` (a player id) may see. At most MAX_TRANSIENT_PER_MESSAGE."""
    events = []

    for transient in transients:
        if any(pixel is not None and is_hidden(viewer, pixel) for pixel in (transient["source"], transient["target"])):
            continue

        if in_area(grid, own_pixels, view, *transient["from"], margin=margin) or in_area(grid, own_pixels, view, *transient["to"], margin=margin):
            events.append(proto.transient_event(transient["kind"], transient["type"], transient["from"], transient["to"]))

            if len(events) >= MAX_TRANSIENT_PER_MESSAGE:
                break

    return events