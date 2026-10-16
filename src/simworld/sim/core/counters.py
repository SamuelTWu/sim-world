"""Cheap named counters the simulation bumps while it works, so the server can report how much work a tick did (README 9.1).

    counters.count(ctx, "tile_checks")        # no-op when the context has no counters (tests, tools)

The server reads and resets them every few seconds (`take()`); nothing in the simulation reads them, so they cannot change what happens.
Names in use: tile_checks (a pixel's step was tested against the terrain), blocked_moves (that test said no), attacks (an attack landed).
Add a name wherever something expensive happens (projectile segment tests, structure lookups); no registration needed.
"""


class Counters:
    def __init__(self):
        self.values = {}

    def add(self, name, amount=1):
        self.values[name] = self.values.get(name, 0) + amount

    def take(self):
        """The counts since the last call, then start again from zero."""
        values, self.values = self.values, {}
        return values


def count(ctx, name, amount=1):
    counters = getattr(ctx, "counters", None)

    if counters is not None:
        counters.add(name, amount)