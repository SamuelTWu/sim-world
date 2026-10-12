"""The data behind the blueprint editor: what the player has chosen so far, and how it becomes a blueprint file.

No pygame here, so it can be tested on its own. The editor (blueprint_editor.py) only draws this and calls its methods.
The finished blueprint (`definition()`) is sent to the server's `save_blueprint` command, which checks it again: nothing
here is trusted, it just keeps the player from making choices the server would refuse.
"""
import copy
import math
import re

NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")
MAX_NAME = 40
MAX_TEXT = 40

COLORS = [
    (236, 122, 112), (232, 154, 72), (236, 210, 96), (120, 200, 130), (92, 176, 104), (86, 192, 200),
    (96, 146, 235), (140, 120, 232), (192, 104, 204), (255, 120, 200), (200, 170, 130), (200, 204, 214),
]
SHAPES = {
    "Square": [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]],
    "Diamond": [[0.0, -0.6], [0.6, 0.0], [0.0, 0.6], [-0.6, 0.0]],
    "Triangle": [[0.0, -0.6], [0.55, 0.5], [-0.55, 0.5]],
    "Hexagon": [[-0.3, -0.5], [0.3, -0.5], [0.6, 0.0], [0.3, 0.5], [-0.3, 0.5], [-0.6, 0.0]],
}
ITEMS = ("iron", "seeds", "wood", "stone", "food", "water")

# name -> (label, default, minimum, maximum, whole number?)
STATS = {
    "health": ("Health", 1.0, 1.0, 1000.0, False),
    "energy": ("Energy", 1.0, 1.0, 1000.0, False),
    "slots": ("Slots (can hold)", 0, 0, 99, True),
    "size": ("Size (takes up)", 1, 1, 99, True),
}
SPRITE_SIZE = (8, 64, 4)  # minimum, maximum, step (pixels)


def blueprint_id(name):
    """The file name a blueprint gets (the same rule as the server's): "Fast Runner!" -> "fast_runner"."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48]


def prettify(key):
    return str(key).replace("_", " ").strip().capitalize()


def nice(raw):
    base = 10 ** math.floor(math.log10(raw))

    for factor in (1, 2, 5, 10):
        if factor * base >= raw:
            return factor * base

    return 10 * base


def is_whole(spec):
    return isinstance(spec["default"], int) and not isinstance(spec["default"], bool)


def is_number(spec):
    return spec["choices"] is None and not isinstance(spec["default"], bool) and (isinstance(spec["default"], (int, float)) or (spec["default"] is None and spec["maximum"] is not None))


def kind_of(spec):
    """How a parameter is edited: "toggle", "choice", "number" or "text"."""
    if isinstance(spec["default"], bool):
        return "toggle"

    if spec["choices"] is not None:
        return "choice"

    return "number" if is_number(spec) else "text"


def step_for(spec):
    """How much one click changes a number: about a twentieth of its range, but small when the default is small (a cooldown of 200 steps by 50, not 5000)."""
    low, high, default = spec["minimum"], spec["maximum"], spec["default"]
    raw = (high - low) / 20 if low is not None and high is not None else None
    anchor = abs(default) / 4 if isinstance(default, (int, float)) and not isinstance(default, bool) and default else None

    if raw is None and anchor is None:
        raw = 1.0
    elif raw is None or (anchor is not None and anchor < raw):
        raw = anchor

    step = nice(max(raw, 1e-6))
    return max(1, round(step)) if is_whole(spec) else step


def show_number(value):
    if value is None:
        return "default"

    if isinstance(value, float) and value == int(value) and abs(value) < 1e6:
        return str(int(value))

    return f"{value:.3g}" if isinstance(value, float) else str(value)


class EditorModel:
    """One blueprint being designed. `catalog` is gui/catalog.py's data."""

    def __init__(self, catalog, taken=()):
        self.catalog = catalog
        self.taken = set(taken)  # blueprint ids already used (file names without .json)
        self.name = ""
        self.color = COLORS[6]
        self.shape = "Square"
        self.sprite_size = 32
        self.stats = {key: spec[1] for key, spec in STATS.items()}
        self.behaviors = {}
        self.inventory = {}
        self._linked = set()
        self.pixel = None  # the server's description of the pixel being edited (see from_info); None when designing a new blueprint
        self.original = None

    @classmethod
    def from_info(cls, catalog, info):
        """Editing a pixel that exists: `info` is the server's "entity_info" (edit_property.describe). Behaviors the catalog does not know are left out."""
        model = cls(catalog)
        model.pixel = info
        model.name = info.get("name", "pixel")
        model.stats = {key: info["stats"][key] for key in STATS}
        model.behaviors = {name: {key: values.get(key, spec["default"]) for key, spec in catalog[name]["params"].items()} for name, values in info["traits"].items() if name in catalog and isinstance(values, dict)}
        model.inventory = dict(info.get("inventory", {}))
        model.original = copy.deepcopy((model.stats, model.behaviors))
        model._linked = set(model.behaviors)
        return model

    @property
    def editing(self):
        return self.pixel is not None

    def removable(self, name):
        """In a new blueprint everything can be removed; on an existing pixel only what was added in this session."""
        return self.original is None or name not in self.original[1]

    def stat_limits(self, key):
        label, default, low, high, whole = STATS[key]

        if self.pixel is not None:
            low, high = self.pixel.get("limits", {}).get(key, (low, high))

            if key == "slots":
                low = max(low, self.pixel.get("slots_used", 0))

        return low, high

    def stat_locked(self, key):
        return self.pixel is not None and key == "size" and bool(self.pixel.get("carried"))

    def stat_price(self, key):
        return float(self.pixel.get("prices", {}).get(key, 0.0)) if self.pixel is not None else 0.0

    def changes(self):
        """What differs from the pixel as it is, as the paths `edit_property` takes."""
        stats, behaviors = self.original
        changes = {key: value for key, value in self.stats.items() if value != stats[key]}

        for name, values in self.behaviors.items():
            if name not in behaviors:
                changes[f"traits.{name}"] = dict(values)
                continue

            for key, value in values.items():
                if value != behaviors[name].get(key):
                    changes[f"traits.{name}.{key}"] = value

        return changes

    def upgrade_cost(self):
        """What the server will charge for changes(): new behavior prices minus old (never negative), plus the stat prices per unit raised."""
        stats, behaviors = self.original
        cost = max(0.0, self.traits_cost(self.behaviors) - self.traits_cost(behaviors))

        for key, value in self.stats.items():
            cost += max(0.0, value - stats[key]) * self.stat_price(key)

        return cost

    # --- name ---------------------------------------------------------------------------------------------------

    def clean_name(self):
        return " ".join(self.name.split())

    def type_name(self, text):
        for character in text:
            if character in NAME_CHARS and len(self.name) < MAX_NAME:
                self.name += character

    def name_problem(self):
        if not self.clean_name():
            return "Give it a name first"

        if not any(character.isalnum() for character in self.name):
            return "The name needs a letter or a digit"

        if blueprint_id(self.name) in self.taken:
            return "That name is taken: pick another"

        return None

    # --- look and stats ------------------------------------------------------------------------------------------

    def nudge_stat(self, key, direction, factor=1):
        label, default, _, _, whole = STATS[key]
        low, high = self.stat_limits(key)
        step = 1 if whole else 0.5

        if self.stat_locked(key):
            return

        value = self.stats[key] + direction * step * factor
        value = max(low, min(high, value))
        self.stats[key] = int(value) if whole else round(value, 3)

    def nudge_size(self, direction, factor=1):
        low, high, step = SPRITE_SIZE
        self.sprite_size = max(low, min(high, self.sprite_size + direction * step * factor))

    # --- behaviors -----------------------------------------------------------------------------------------------

    def spec(self, name, key):
        return self.catalog[name]["params"][key]

    def addable(self):
        """Behaviors not added yet, simplest first."""
        return sorted((name for name in self.catalog if name not in self.behaviors), key=lambda name: (self.catalog[name]["tier"], name))

    def add_behavior(self, name):
        """Adds a behavior with its default settings, and anything it requires. Returns the names added."""
        if name not in self.catalog or name in self.behaviors:
            return []

        added = []

        for required in self.catalog[name]["requires"]:
            added += self.add_behavior(required)

        self.behaviors[name] = {key: spec["default"] for key, spec in self.catalog[name]["params"].items()}
        added.append(name)
        self.link_commands()
        return added

    def link_commands(self):
        """Having "command" and a behavior it can order means the player can order it, until the player turns that off. Done once, when either is added."""
        command = self.behaviors.get("command")

        if command is None:
            return

        for name in self.behaviors:
            if name != "command" and name in command and name not in self._linked:
                command[name] = True
                self._linked.add(name)

    def remove_behavior(self, name):
        """Removes a behavior and everything that requires it. Returns the names removed."""
        if name not in self.behaviors:
            return []

        removed = [name]

        for other in list(self.behaviors):
            if other != name and name in self.catalog[other]["requires"]:
                removed += self.remove_behavior(other)

        self.behaviors.pop(name, None)
        self._linked.discard(name)
        return removed

    def required_by(self, name):
        return [other for other in self.behaviors if name in self.catalog[other]["requires"]]

    def toggle(self, name, key):
        self.behaviors[name][key] = not self.behaviors[name][key]

    def cycle(self, name, key, direction=1):
        choices = self.spec(name, key)["choices"]
        current = self.behaviors[name][key]
        index = choices.index(current) if current in choices else -1
        self.behaviors[name][key] = choices[(index + direction) % len(choices)]

    def nudge(self, name, key, direction, factor=1):
        """A click on - or +. A number that may be left blank goes blank again when you step down past its minimum."""
        spec = self.spec(name, key)
        value = self.behaviors[name][key]
        low, high = spec["minimum"], spec["maximum"]
        step = step_for(spec) * factor

        if value is None:
            if direction < 0:
                return

            value = low if low is not None else 0

        else:
            value += direction * step

            if spec["default"] is None and low is not None and value < low:
                self.behaviors[name][key] = None
                return

        if low is not None:
            value = max(low, value)

        if high is not None:
            value = min(high, value)

        self.behaviors[name][key] = int(round(value)) if is_whole(spec) else round(value, 6)

    def type_param(self, name, key, text):
        for character in text:
            if character in NAME_CHARS and len(str(self.behaviors[name][key] or "")) < MAX_TEXT:
                self.behaviors[name][key] = (self.behaviors[name][key] or "") + character

    def backspace_param(self, name, key):
        self.behaviors[name][key] = str(self.behaviors[name][key] or "")[:-1]

    def cost(self):
        return self.traits_cost(self.behaviors)

    def traits_cost(self, behaviors):
        total = 0.0

        for name, values in behaviors.items():
            entry = self.catalog[name]
            total += entry["base_cost"]

            for key, spec in entry["params"].items():
                value = values.get(key)

                if spec["weight"] and isinstance(value, (int, float)) and not isinstance(value, bool):
                    total += spec["weight"] * max(0.0, value - (spec["minimum"] or 0.0))

        return total

    # --- inventory -----------------------------------------------------------------------------------------------

    def items_left(self):
        return [item for item in ITEMS if item not in self.inventory]

    def add_item(self, item):
        if item not in self.inventory:
            self.inventory[item] = 1

    def nudge_item(self, item, direction, factor=1):
        count = self.inventory.get(item, 0) + direction * factor

        if count <= 0:
            self.inventory.pop(item, None)
        else:
            self.inventory[item] = min(9999, count)

    # --- result --------------------------------------------------------------------------------------------------

    def problems(self):
        problem = self.name_problem()
        return [problem] if problem else []

    def definition(self):
        """The blueprint as sent to the server (and saved as JSON)."""
        definition = {
            "name": self.clean_name(),
            "tags": ["pixel", "custom"],
            "maxHealth": self.stats["health"],
            "maxEnergy": self.stats["energy"],
            "slots": self.stats["slots"],
            "size": self.stats["size"],
            "sprite": {"shape": [list(point) for point in SHAPES[self.shape]], "color": list(self.color), "size": [self.sprite_size, self.sprite_size], "layer": 2},
            "traits": {name: dict(values) for name, values in self.behaviors.items()},
        }

        if self.inventory:
            definition["inventory"] = dict(self.inventory)

        return definition