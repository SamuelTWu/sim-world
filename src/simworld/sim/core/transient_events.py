"""Transient events: things that are SEEN but are not pixels (README 8.3).

A bullet, a flash, an explosion lasts a fraction of a second and moves too fast to stream like a pixel. So the simulation
only notes that it HAPPENED ("A fired at B", "something hit B here") and the server sends that note, a few small numbers,
to the players who can see it. Their clients animate it on their own (rendering/transient_events.py). The simulation never creates a
projectile pixel for it: the damage is decided at once on the server and the animation is decoration.

Emit from anywhere that has the SimContext:

    transientEvents.fired(ctx, attacker, target, "arrow")      # a shot from attacker to target
    transientEvents.hit(ctx, attacker, target, "melee")        # an impact on target
    transientEvents.emit(ctx, "explosion", point=(x, y), type="small")   # at a place, nobody involved

`kind` and `type` are free words the renderer may know; one it does not know is ignored.
"""


class TransientEventLog:
    """The transient events of the current tick. The server takes them once per tick (`take()`)."""

    MAX_PER_TICK = 256

    def __init__(self):
        self.items = []

    def add(self, kind, type="", source=None, target=None, point=None, to_point=None):
        """Note one transient event. `source` / `target` are pixels (their positions are copied now; they are also used to decide who may see it)."""
        if len(self.items) >= self.MAX_PER_TICK:
            return

        start = point if point is not None else ((source.position.x, source.position.y) if source is not None else None)
        end = to_point if to_point is not None else ((target.position.x, target.position.y) if target is not None else None)

        if start is None and end is None:
            return

        self.items.append({"kind": kind, "type": type, "from": start or end, "to": end or start, "source": source, "target": target})

    def take(self):
        items, self.items = self.items, []
        return items


def emit(ctx, kind, type="", source=None, target=None, point=None, to_point=None):
    """Note a transient event if this context records them (it does not in tests that build a bare context)."""
    log = getattr(ctx, "transient_events", None)

    if log is not None:
        log.add(kind, type, source, target, point, to_point)


def fired(ctx, source, target, type=""):
    emit(ctx, "fired", type, source=source, target=target)


def hit(ctx, source, target, type=""):
    emit(ctx, "hit", type, source=source, target=target, point=(target.position.x, target.position.y))