MAX_PIXELS_PER_PLAYER = 500
MAX_PIXELS_IN_WORLD = 5000
MAX_SPAWNS_PER_TICK = 64
MAX_SPAWNS_PER_PLAYER_PER_TICK = 16
MAX_THINKS_PER_TICK = 1000


class LimitReached(Exception):
    pass


def bound(value):
    return int(value) if value > 0 else float("inf")


class Limits:
    def __init__(self):
        self.max_per_player = MAX_PIXELS_PER_PLAYER
        self.max_in_world = MAX_PIXELS_IN_WORLD
        self.max_spawns = MAX_SPAWNS_PER_TICK
        self.max_spawns_per_owner = MAX_SPAWNS_PER_PLAYER_PER_TICK
        self.max_thinks = MAX_THINKS_PER_TICK
        self.counters = None
        self.tick = None
        self.spawned = 0
        self.spawned_by = {}
        self.world_alive = None
        self.owner_alive = {}

    def configure(self, max_per_player=None, max_in_world=None, max_spawns=None, max_spawns_per_owner=None, max_thinks=None):
        if max_per_player is not None:
            self.max_per_player = bound(max_per_player)

        if max_in_world is not None:
            self.max_in_world = bound(max_in_world)

        if max_spawns is not None:
            self.max_spawns = bound(max_spawns)

        if max_spawns_per_owner is not None:
            self.max_spawns_per_owner = bound(max_spawns_per_owner)

        if max_thinks is not None:
            self.max_thinks = max(0, int(max_thinks))

    def count(self, name, amount=1):
        if self.counters is not None:
            self.counters.add(name, amount)

    def new_tick(self, tick):
        if tick != self.tick:
            self.tick = tick
            self.spawned = 0
            self.spawned_by = {}
            self.world_alive = None
            self.owner_alive = {}

    def check_spawn(self, tick, owner, count_world, count_owner):
        self.new_tick(tick)

        if self.spawned >= self.max_spawns:
            self.refuse(f"too many pixels were created at once (at most {self.max_spawns} per tick): try again")

        if self.spawned_by.get(owner, 0) >= self.max_spawns_per_owner:
            self.refuse(f"too many pixels created at once (at most {self.max_spawns_per_owner} per tick): try again")

        if self.world_alive is None:
            self.world_alive = count_world()

        if self.world_alive >= self.max_in_world:
            self.refuse(f"the world is full ({self.max_in_world} pixels)")

        if owner is not None:
            if owner not in self.owner_alive:
                self.owner_alive[owner] = count_owner(owner)

            if self.owner_alive[owner] >= self.max_per_player:
                self.refuse(f"you already have the most pixels allowed ({self.max_per_player})")

    def refuse(self, reason):
        self.count("spawn_refused")
        raise LimitReached(reason)

    def note_spawn(self, owner):
        self.spawned += 1
        self.spawned_by[owner] = self.spawned_by.get(owner, 0) + 1

        if self.world_alive is not None:
            self.world_alive += 1

        if owner in self.owner_alive:
            self.owner_alive[owner] += 1

    def think_priority(self, entity_id, tick):
        value = (entity_id * 2654435761 + tick * 2246822519) & 0xFFFFFFFF
        value ^= value >> 15
        value = (value * 2246822519) & 0xFFFFFFFF
        value ^= value >> 13
        value = (value * 3266489917) & 0xFFFFFFFF
        return value ^ (value >> 16)