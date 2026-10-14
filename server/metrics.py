"""What the server measures about itself and logs every few seconds (README 9.1). Measure first, then optimize the real bottleneck.

Nothing here imports the game or the network, and nothing here changes what the simulation does: the tick loop hands in numbers and
`Metrics` adds them up. Every few seconds `snapshot()` returns the window as a plain dict (tests and later tools can read it, it is also
kept as `metrics.last`) and `format_lines()` turns it into the log lines.

Per window it reports:
  tick time: average, 95th percentile, max, and the budget; overruns (ticks whose work took longer than the budget); behind resets
             (the loop was so late it gave up catching up, see MAX_BEHIND in server.py)
  phases:    where the time went (inbox, step, grid, notices, replicate): the average ms per tick of each part of a tick
  pixels / projectiles: how many are active now (a projectile system does not exist yet, so 0 until it registers `systems.projectiles`)
  counters:  work done per second, from entity/system/counters.py (tile_checks, blocked_moves, attacks, and what is added later)
  network:   bytes per second sent in total, by message type, and per client (with messages per second, the largest outbox backlog seen, and the
             size of the biggest single message)
"""
import time

PHASES = ("inbox", "step", "grid", "notices", "replicate")
MAX_CLIENT_LINES = 8


class Metrics:
    def __init__(self, budget):
        self.budget = budget  # seconds per tick (TICK_DT)
        self.totals = {"ticks": 0, "overruns": 0, "behind_resets": 0}
        self.last = None
        self.start(time.monotonic())

    def start(self, now):
        """Begin a new window."""
        self.window_start = now
        self.durations = []
        self.phase_time = dict.fromkeys(PHASES, 0.0)
        self.overruns = 0
        self.behind_resets = 0
        self.by_type = {}  # message type -> [bytes, messages]
        self.by_client = {}  # player id -> {"name", "bytes", "messages", "backlog", "biggest"}

    def tick(self, elapsed, phases=None):
        """One tick took `elapsed` seconds of work. `phases` is {name: seconds} for the parts listed in PHASES."""
        self.durations.append(elapsed)
        self.totals["ticks"] += 1

        if elapsed > self.budget:
            self.overruns += 1
            self.totals["overruns"] += 1

        for name, seconds in (phases or {}).items():
            self.phase_time[name] = self.phase_time.get(name, 0.0) + seconds

    def behind(self):
        self.behind_resets += 1
        self.totals["behind_resets"] += 1

    def sent(self, player_id, name, kind, nbytes, backlog=0):
        """A message of `nbytes` was queued for a client. `backlog` is how many messages were already waiting in its outbox."""
        by_type = self.by_type.setdefault(kind, [0, 0])
        by_type[0] += nbytes
        by_type[1] += 1
        entry = self.by_client.get(player_id)

        if entry is None:
            entry = self.by_client[player_id] = {"name": name, "bytes": 0, "messages": 0, "backlog": 0, "biggest": 0}

        entry["name"] = name
        entry["bytes"] += nbytes
        entry["messages"] += 1
        entry["backlog"] = max(entry["backlog"], backlog)
        entry["biggest"] = max(entry["biggest"], nbytes)

    def snapshot(self, now, pixels=0, projectiles=0, counters=None, players=0, tick=0):
        """The finished window as a dict, then start the next one. Rates are per second over the real length of the window."""
        seconds = max(now - self.window_start, 1e-9)
        ticks = len(self.durations)
        ordered = sorted(self.durations)
        average = sum(ordered) / ticks if ticks else 0.0
        p95 = ordered[min(ticks - 1, int(ticks * 0.95))] if ticks else 0.0
        snap = {
            "tick": tick,
            "seconds": seconds,
            "players": players,
            "pixels": pixels,
            "projectiles": projectiles,
            "ticks": ticks,
            "tick_ms": {"avg": average * 1000, "p95": p95 * 1000, "max": (ordered[-1] if ticks else 0.0) * 1000, "budget": self.budget * 1000},
            "overruns": self.overruns,
            "behind_resets": self.behind_resets,
            "phase_ms": {name: (total / ticks * 1000 if ticks else 0.0) for name, total in self.phase_time.items()},
            "counters_per_s": {name: value / seconds for name, value in sorted((counters or {}).items())},
            "bytes_per_s": sum(entry[0] for entry in self.by_type.values()) / seconds,
            "by_type_per_s": {kind: {"bytes": entry[0] / seconds, "messages": entry[1] / seconds} for kind, entry in sorted(self.by_type.items())},
            "clients": [
                {"id": player_id, "name": entry["name"], "bytes_per_s": entry["bytes"] / seconds, "messages_per_s": entry["messages"] / seconds, "backlog": entry["backlog"], "biggest": entry["biggest"]}
                for player_id, entry in sorted(self.by_client.items())
            ],
            "totals": dict(self.totals),
        }
        self.last = snap
        self.start(now)
        return snap


def kb(value):
    return f"{value / 1024:.1f} KB/s"


def format_lines(snap):
    """The log lines for one snapshot (without the "[server]" prefix)."""
    tick = snap["tick_ms"]
    lines = [
        f"tick {snap['tick']} | players {snap['players']} | active pixels {snap['pixels']} | active projectiles {snap['projectiles']}",
        f"  tick ms: avg {tick['avg']:.1f}, p95 {tick['p95']:.1f}, max {tick['max']:.1f} (budget {tick['budget']:.0f}) | overruns {snap['overruns']}/{snap['ticks']} | behind resets {snap['behind_resets']}",
        "  phases ms/tick: " + " ".join(f"{name} {value:.2f}" for name, value in snap["phase_ms"].items()),
    ]

    if snap["counters_per_s"]:
        lines.append("  work/s: " + " ".join(f"{name} {value:.0f}" for name, value in snap["counters_per_s"].items()))

    lines.append(f"  network: {kb(snap['bytes_per_s'])} out" + "".join(f" | {kind} {kb(entry['bytes'])} ({entry['messages']:.1f}/s)" for kind, entry in snap["by_type_per_s"].items()))
    clients = snap["clients"]

    for client in sorted(clients, key=lambda c: -c["bytes_per_s"])[:MAX_CLIENT_LINES]:
        lines.append(f"    client {client['id']} '{client['name']}': {kb(client['bytes_per_s'])}, {client['messages_per_s']:.1f} msg/s, biggest {client['biggest']} B, outbox backlog max {client['backlog']}")

    if len(clients) > MAX_CLIENT_LINES:
        lines.append(f"    ... and {len(clients) - MAX_CLIENT_LINES} more clients")

    return lines