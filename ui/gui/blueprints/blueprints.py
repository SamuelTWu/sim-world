"""Reads the saved blueprints (entity definition JSON files) and turns one into rows for the sidebar.

No pygame here, so it can be tested on its own. A blueprint is any JSON object in game/entity/entities/ (the same
folder EntityFactory loads from). The fields EntityFactory understands get proper sections; anything else in the
file still shows up under its own heading, so new attributes appear without touching this file.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FOLDER = Path(__file__).resolve().parent.parent / "entity" / "entities"

LEGACY_SECTIONS = {"movement": "Movement", "physics": "Physics", "material": "Material"}
HANDLED = {"name", "kind", "tags", "sprite", "sprite_id", "components", "visible", "owner", "maxHealth", "health", "currentHealth", "maxEnergy", "energy", "currentEnergy", "props", "needs", "traits", "inventory", "home", "slots", "size", *LEGACY_SECTIONS}
DEFAULT_COLOR = (140, 146, 160)


@dataclass
class Blueprint:
    id: str
    name: str
    kind: str
    color: tuple
    data: dict = field(default_factory=dict, repr=False)
    source: str = ""


def prettify(key):
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(key)).replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def format_value(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, float):
        return f"{value:.3g}"

    if isinstance(value, (list, tuple)):
        return ", ".join(format_value(item) for item in value) or "none"

    if value is None:
        return "none"

    return str(value)


def flatten(data, prefix=""):
    """Rows (label, text) for a dict, one per leaf; nested keys read "Outer: inner"."""
    rows = []

    for key, value in data.items():
        label = f"{prefix}: {key}" if prefix else prettify(key)

        if isinstance(value, dict):
            rows.extend(flatten(value, label) if value else [(label, "none")])
        else:
            rows.append((label, format_value(value)))

    return rows


def sprite_color(data):
    sprite = data.get("sprite")
    color = sprite.get("color") if isinstance(sprite, dict) else None

    if isinstance(color, (list, tuple)) and len(color) >= 3 and all(isinstance(part, (int, float)) for part in color[:3]):
        return tuple(max(0, min(255, int(part))) for part in color[:3])

    return DEFAULT_COLOR


def load_blueprints(folder=None):
    """Returns (blueprints, problems). Files that are not JSON objects are reported, not fatal."""
    folder = Path(folder) if folder else DEFAULT_FOLDER
    blueprints, problems = [], []

    if not folder.is_dir():
        return blueprints, [f"No blueprint folder at {folder}"]

    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as problem:
            problems.append(f"{path.name}: {problem}")
            continue

        if not isinstance(data, dict):
            problems.append(f"{path.name}: not a JSON object")
            continue

        blueprints.append(Blueprint(path.stem, str(data.get("name", prettify(path.stem))), str(data.get("kind", "pixel")), sprite_color(data), data, path.name))

    return blueprints, problems


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def describe(blueprint):
    """The blueprint's attributes as [(section title, [(label, text), ...]), ...], skipping empty sections."""
    data = blueprint.data
    sections = []

    overview = [("File", blueprint.source), ("Kind", blueprint.kind)]

    if data.get("tags"):
        overview.append(("Tags", format_value(sorted(data["tags"]) if isinstance(data["tags"], list) else data["tags"])))

    if data.get("visible") is False:
        overview.append(("Visible", "No"))

    if data.get("owner") is not None:
        overview.append(("Owner", format_value(data["owner"])))

    sections.append(("Overview", overview))

    vitals = []
    max_health = number(data.get("maxHealth", data.get("health")))
    max_energy = number(data.get("maxEnergy", data.get("energy")))

    if max_health is not None:
        vitals.append(("Health", f"{format_value(number(data.get('currentHealth', max_health)))} / {format_value(max_health)}"))

    if max_energy is not None:
        vitals.append(("Energy", f"{format_value(number(data.get('currentEnergy', max_energy)))} / {format_value(max_energy)}"))

    sections.append(("Vitals", vitals))

    for key, title in LEGACY_SECTIONS.items():
        if isinstance(data.get(key), dict):
            sections.append((title, flatten(data[key])))

    if isinstance(data.get("props"), dict):
        sections.append(("Properties", flatten(data["props"])))

    needs = data.get("needs")

    if isinstance(needs, dict):
        rows = []

        for name, need in needs.items():
            if isinstance(need, dict):
                rows.append((prettify(name), f"{format_value(need.get('value', 0.0))}  ({format_value(need.get('rate', 0.0))}/s, {format_value(need.get('minimum', 0.0))} to {format_value(need.get('maximum', 1.0))})"))
            else:
                rows.append((prettify(name), format_value(need)))

        sections.append(("Needs", rows))

    if isinstance(data.get("traits"), dict):
        rows = []

        for name, value in data["traits"].items():
            if name == "command" and isinstance(value, dict):
                rows.append(("Commands", ", ".join(command for command, allowed in value.items() if allowed) or "none"))
            elif isinstance(value, dict):
                rows.extend(flatten(value, prettify(name)))
            else:
                rows.append((prettify(name), format_value(value)))

        sections.append(("Traits", rows))

    capacity = []

    if number(data.get("slots")) is not None:
        capacity.append(("Slots (holds)", format_value(data["slots"])))

    if number(data.get("size")) is not None:
        capacity.append(("Size (takes up)", format_value(data["size"])))

    sections.append(("Capacity", capacity))

    if isinstance(data.get("inventory"), dict):
        sections.append(("Inventory", flatten(data["inventory"])))

    if "home" in data:
        sections.append(("Home", [("Position", format_value(data["home"]))]))

    for key, value in data.items():
        if key not in HANDLED:
            sections.append((prettify(key), flatten(value) if isinstance(value, dict) else [("Value", format_value(value))]))

    return [(title, rows) for title, rows in sections if rows]


def summary(blueprint):
    """A short line for the tray card, e.g. "Health 10   Energy 5"."""
    data, parts = blueprint.data, []
    health, energy = number(data.get("maxHealth", data.get("health"))), number(data.get("maxEnergy", data.get("energy")))

    if health is not None:
        parts.append(f"Health {format_value(health)}")

    if energy is not None:
        parts.append(f"Energy {format_value(energy)}")

    return "   ".join(parts)