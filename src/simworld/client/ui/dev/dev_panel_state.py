import math
import random
from collections import namedtuple

from ....shared.dev_commands import NEEDS_SELECTION, SPEEDS, DevSyntaxError, parse, shown
from ....world.sandbox import BLOCK, REGION_LABEL, REGION_SIZE, entity_slots
from .console_state import sources

Result = namedtuple("Result", "requests lines goto", defaults=((), (), None))
Target = namedtuple("Target", "x y span")

GOTO = (("tiles", "Tiles"), ("entities", "Entities"), ("generated", "Generated"), ("start", "Start"))
START_SPAN = 20
START_SHIFT = (2, -3)
MAX_INSPECT = 1000
MAX_SEED = 2**32 - 1
MAX_GEN_ERROR = 60


def is_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def center_of(tile):
    return math.floor(tile[0]) + 0.5, math.floor(tile[1]) + 0.5


def box_target(left, top, right, bottom):
    return Target((left + right) / 2, (top + bottom) / 2, max(right - left, bottom - top))


def goto_target(labels, name):
    labels = [(x, y, text) for x, y, text in labels or ()]
    tiles = [(x, y) for x, y, text in labels if text != REGION_LABEL]
    region = next(((x, y) for x, y, text in labels if text == REGION_LABEL), None)

    if name == "generated":
        return Target(region[0] + REGION_SIZE / 2, region[1] + REGION_SIZE / 2, REGION_SIZE) if region else None

    if not tiles:
        return None

    if name == "tiles":
        return box_target(min(x for x, _ in tiles), min(y for _, y in tiles), max(x for x, _ in tiles) + BLOCK, max(y for _, y in tiles) + BLOCK)

    if name == "start":
        return Target(min(x for x, _ in tiles) + START_SHIFT[0], min(y for _, y in tiles) + START_SHIFT[1], START_SPAN)

    if name == "entities":
        slots = entity_slots(len(tiles))
        return box_target(min(x for x, _ in slots), min(y for _, y in slots), max(x for x, _ in slots) + 1, max(y for _, y in slots) + 1)

    return None


def fit_zoom(span, size, tile_size, low, high):
    zoom = min(size) / (max(span, 1) * tile_size * 1.1)
    return max(low, min(zoom, high))


def entity_at(pos, entities, to_screen, radius):
    best = None

    for entity in entities or ():
        x, y = to_screen(entity.position.x, entity.position.y)
        distance = math.hypot(x - pos[0], y - pos[1])

        if distance <= radius(entity) and (best is None or distance < best[0]):
            best = (distance, entity.id)

    return best[1] if best else None


class PanelState:
    def __init__(self):
        self.catalog = None
        self.reset()

    def reset(self):
        self.catalog = None
        self.enabled = False
        self.paused = False
        self.speed = 1.0
        self.selected = None
        self.inspect = None
        self.blueprint = None
        self.tile = None
        self.gen = None
        self.gen_error = None
        self.gen_asked = False
        self.gen_scroll = 0
        self.next_seed = lambda: random.randrange(MAX_SEED + 1)
        self.close()

    def close(self):
        self.open = False
        self.mode = None
        self.picker = None
        self.scroll = 0
        self.painting = False
        self.last_tile = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

        if not self.enabled:
            self.close()

    def set_catalog(self, data):
        self.catalog = data if isinstance(data, dict) else None

    def toggle(self):
        if not self.enabled:
            return False

        if self.open:
            self.close()
        else:
            self.open = True

        return True

    def options(self, kind):
        return sources("blueprint" if kind == "spawn" else "tile", self.catalog)

    def rows(self):
        return [
            [("pause", "Resume" if self.paused else "Pause", self.paused)],
            [("step", "Step", False)],
            [(f"speed:{shown(factor)}", f"{shown(factor)}x", factor == self.speed) for factor in SPEEDS],
            [("spawn", f"Spawn: {self.blueprint or 'pick'}", self.mode == "spawn")],
            [("delete", "Delete", self.mode == "delete")],
            [("wake", "Wake", False)],
            [("inspect", "Inspect", False)],
            [("paint", f"Paint: {self.tile or 'pick'}", self.mode == "paint")],
            [(f"goto:{name}", label, False) for name, label in GOTO],
        ]

    def gen_request(self):
        if not self.enabled or not self.open or self.gen is not None or self.gen_asked:
            return None

        self.gen_asked = True
        return ("gen", {"action": "list"}, True)

    def gen_rows(self):
        if self.gen is None:
            return [("seed", None, "Seed ?", False), ("heading", None, self.gen_error or "loading...", False)]

        rows = [("seed", "gen:seed", f"Seed {self.gen['seed']}", False), ("heading", None, "Features", False)]
        rows += [("check", f"gen:feature:{name}", name, on) for name, on in self.gen["features"].items()]
        rows += [("heading", None, "Maps", False)]
        rows += [("check", f"gen:map:{name}", name, on) for name, on in self.gen["maps"].items()]
        return rows

    def press_gen(self, key):
        if self.gen is None:
            return Result()

        if key == "gen:seed":
            seed = self.next_seed()

            if seed == self.gen["seed"]:
                seed = (seed + 1) % (MAX_SEED + 1)

            return self.send(f"/gen seed {seed}")

        kind, _, name = key[4:].partition(":")
        known = self.gen["features"] if kind == "feature" else self.gen["maps"] if kind == "map" else None

        if known is None or name not in known:
            return Result()

        return self.send(f"/gen {kind} {name} {'off' if known[name] else 'on'}")

    def send(self, text):
        lines = [(f"> {text}", "echo")]

        try:
            request = parse(text, {})
        except DevSyntaxError as problem:
            return Result(lines=tuple(lines + [(str(problem), "error")]))

        return Result(requests=(request,), lines=tuple(lines))

    def press(self, key, context=None):
        if key.startswith("goto:"):
            return Result(goto=key[5:])

        if key.startswith("gen:"):
            return self.press_gen(key)

        if key in ("spawn", "paint"):
            return self.toggle_tool(key)

        if key == "delete":
            self.mode = None if self.mode == "delete" else "delete"
            self.picker = None
            return Result()

        if key in ("wake", "inspect"):
            selected = (context or {}).get("selected")

            if not is_id(selected):
                return Result(lines=((NEEDS_SELECTION, "error"),))

            return self.send(f"/{key} {selected}")

        if key in ("pause", "step"):
            return self.send(f"/{key}")

        if key.startswith("speed:"):
            return self.send(f"/speed {key[6:]}")

        return Result()

    def toggle_tool(self, kind):
        if self.mode == kind:
            self.mode = None
            self.picker = None
        elif self.picker == kind:
            self.picker = None
        else:
            self.mode = None
            self.picker = kind
            self.scroll = 0

        return Result()

    def pick_option(self, name):
        if self.picker is None:
            return Result()

        if self.picker == "spawn":
            self.blueprint = name
        else:
            self.tile = name

        self.mode = self.picker
        self.picker = None
        return Result()

    def click(self, tile, entity_id=None):
        if self.mode == "spawn" and self.blueprint:
            x, y = center_of(tile)
            return self.send(f"/spawn {self.blueprint} {shown(x)} {shown(y)}")

        if self.mode == "paint" and self.tile:
            return self.paint(tile, True)

        if self.mode == "delete" and is_id(entity_id):
            return self.send(f"/delete {entity_id}")

        return Result()

    def paint(self, tile, start=False):
        cell = (math.floor(tile[0]), math.floor(tile[1]))

        if cell[0] < 0 or cell[1] < 0 or (not start and (not self.painting or cell == self.last_tile)):
            return Result()

        self.painting = True
        self.last_tile = cell
        x, y = center_of(tile)
        return self.send(f"/tile {self.tile} {shown(x)} {shown(y)}")

    def drag(self, tile):
        if self.mode == "paint" and self.tile and self.painting:
            return self.paint(tile)

        return Result()

    def release(self):
        self.painting = False
        self.last_tile = None

    def cancel(self):
        changed = self.mode is not None or self.picker is not None or self.inspect is not None
        self.mode = None
        self.picker = None
        self.inspect = None
        self.release()
        return changed

    def select(self, entity_id):
        if entity_id != self.selected:
            self.inspect = None

        self.selected = entity_id

    def current_selected(self, alive_ids, fallback=None):
        if self.selected is not None and self.selected not in alive_ids:
            self.select(None)

        return self.selected if self.selected is not None else fallback

    def take_gen(self, data):
        features, maps, seed = data.get("features"), data.get("maps"), data.get("seed")

        if not isinstance(features, dict) or not isinstance(maps, dict) or not is_id(seed):
            return

        clean = lambda values: {name: value for name, value in values.items() if isinstance(name, str) and isinstance(value, bool)}
        self.gen = {"seed": seed, "features": clean(features), "maps": clean(maps)}
        self.gen_error = None

    def hint(self):
        if self.mode == "spawn":
            return f"Click the map to place {self.blueprint}. Esc stops."

        if self.mode == "paint":
            return f"Click or drag to paint {self.tile}. Esc stops."

        if self.mode == "delete":
            return "Click an entity to delete it. Esc stops."

        return ""

    def note_result(self, what, message):
        data = message.get("data") if isinstance(message, dict) else None

        if what == "gen" and isinstance(message, dict) and not message.get("ok") and self.gen is None:
            self.gen_error = str(message.get("text", "no section"))[:MAX_GEN_ERROR]
            return

        if not isinstance(message, dict) or not message.get("ok") or not isinstance(data, dict):
            return

        if what == "gen":
            self.take_gen(data)
            return

        if what in ("pause", "step", "speed"):
            if "paused" in data:
                self.paused = bool(data["paused"])

            speed = data.get("speed")

            if isinstance(speed, (int, float)) and not isinstance(speed, bool):
                self.speed = float(speed)
        elif what == "inspect" and is_id(data.get("id")):
            self.inspect = (data["id"], str(message.get("text", ""))[:MAX_INSPECT])