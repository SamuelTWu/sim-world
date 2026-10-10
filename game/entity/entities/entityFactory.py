from copy import deepcopy
from pathlib import Path
import json

from ..entity import Entity, Vec3
from ..system.needSystem import Need

LEGACY_PROPS = {
    "movement": {"maxSpeed": "max_speed", "reach": "reach", "grabReach": "grab_reach", "climbSpeed": "climb_speed"},
    "physics": {"mass": "mass", "friction": "friction"},
    "material": {"flammable": "flammable", "edible": "edible", "smellStrength": "smell", "conductivity": "conductivity", "absorbency": "absorbency"},
}


def whole(value, default, minimum=0):
    """A whole number at least `minimum`; anything else (missing, text, negative, a fraction) falls back to the default."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return default

    return value


class EntityFactory:
    def __init__(self, definitions_path: str | Path | None = None):
        self.definitions_path = Path(definitions_path) if definitions_path else Path(__file__).parent
        self.definitions = {}

    def load_definition(self, name: str):
        if name not in self.definitions:
            with open(self.definitions_path / f"{name}.json", "r") as file:
                definition = json.load(file)

            # Every definition gets a sprite_id (default: its file name). The "sprite"
            # block in the JSON is visual data that only the client reads (rendering/sprites.py).
            definition.setdefault("sprite_id", name)
            self.definitions[name] = definition

        return self.definitions[name]

    def create(self, name: str, entity_id: int, owner: int | None = None) -> Entity:
        return self.build(self.load_definition(name), entity_id, blueprint_name=name, owner=owner)

    def create_from_blueprint(self, blueprint: dict, entity_id: int, owner: int | None = None) -> Entity:
        return self.build(blueprint, entity_id, blueprint_name=blueprint.get("name"), owner=owner)

    def build(self, definition: dict, entity_id: int, blueprint_name: str | None = None, owner: int | None = None) -> Entity:
        max_health = definition.get("maxHealth", definition.get("health", 1.0))
        max_energy = definition.get("maxEnergy", definition.get("energy", 1.0))

        props = {name: definition[section][key] for section, keys in LEGACY_PROPS.items() for key, name in keys.items() if key in definition.get(section, {})}
        props.update(definition.get("props", {}))

        entity = Entity(
            id=entity_id,
            sprite_id=definition.get("sprite_id", blueprint_name or "pixel"),
            props=props,
            components=deepcopy(definition.get("components", {})),
            name=definition.get("name", blueprint_name or "pixel"),
            kind=definition.get("kind", "pixel"),
            blueprint_name=blueprint_name,
            owner=owner if owner is not None else definition.get("owner"),
            traits=deepcopy(definition.get("traits", {})),
            tags=set(definition.get("tags", [])),
            inventory=dict(definition.get("inventory", {})),
            slots=whole(definition.get("slots", 0), 0),
            size=whole(definition.get("size", 1), 1, minimum=1),
            health=definition.get("currentHealth", max_health),
            max_health=max_health,
            energy=definition.get("currentEnergy", max_energy),
            max_energy=max_energy,
            visible=definition.get("visible", True),
        )

        if "home" in definition:
            entity.home = Vec3(*definition["home"])

        for need_name, data in definition.get("needs", {}).items():
            entity.needs[need_name] = Need(
                name=need_name,
                value=data.get("value", 0.0),
                rate=data.get("rate", 0.0),
                minimum=data.get("minimum", 0.0),
                maximum=data.get("maximum", 1.0),
            )

        return entity