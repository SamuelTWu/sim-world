from pathlib import Path
import json

from ..entity import Entity, Sprite, MovementProfile, Physics, Material
from ..entity_systems.needSystem import Need


class EntityFactory:
    def __init__(self, definitions_path: str | Path | None = None):
        self.definitions_path = Path(definitions_path) if definitions_path else Path(__file__).parent
        self.definitions = {}

    def load_definition(self, name: str):
        if name not in self.definitions:
            path = self.definitions_path / f"{name}.json"

            with open(path, "r") as file:
                self.definitions[name] = json.load(file)

        return self.definitions[name]

    def create(self, name: str, entity_id: int) -> Entity:
        definition = self.load_definition(name)

        sprite = definition.get("sprite", {})
        movement = definition.get("movement", {})
        physics = definition.get("physics", {})
        material = definition.get("material", {})

        entity = Entity(
            id=entity_id,
            sprite=Sprite(
                image=sprite.get("image"),
                character=sprite.get("character"),
                color=tuple(sprite.get("color", [255, 255, 255])),
                size=tuple(sprite.get("size", [16, 16])),
                layer=sprite.get("layer", 0),
            ),
            movement=MovementProfile(
                max_speed=movement.get("maxSpeed", 0.0),
                acceleration=movement.get("acceleration", 0.0),
                deceleration=movement.get("deceleration", 0.0),
                jump_impulse=movement.get("jumpImpulse", 0.0),
                air_control=movement.get("airControl", 0.0),
                gravity=movement.get("gravity", 0.0),
                traction=movement.get("traction", 0.0),
                friction=movement.get("friction", 0.0),
                turn_rate=movement.get("turnRate", 0.0),
                reach=movement.get("reach", 0.0),
                grab_reach=movement.get("grabReach", 0.0),
                climb_speed=movement.get("climbSpeed", 0.0),
                can_air_control=movement.get("canAirControl", False),
                can_attach=movement.get("canAttach", False),
                can_climb=movement.get("canClimb", False),
                can_swing=movement.get("canSwing", False),
                anchor=movement.get("anchor", 0.0),
                charge=movement.get("charge", 0.0),
            ),
            physics=Physics(
                mass=physics.get("mass", 1.0),
                rigid=physics.get("rigid", True),
                friction=physics.get("friction", 1.0),
            ),
            material=Material(
                flammable=material.get("flammable", 0.0),
                edible=material.get("edible", 0.0),
                smell_strength=material.get("smellStrength", 0.0),
                conductivity=material.get("conductivity", 0.0),
                absorbency=material.get("absorbency", 0.0),
            ),
            attributes=definition.get("attributes", {}).copy(),
            components=definition.get("components", {}).copy(),
        )

        for name, data in definition.get("needs", {}).items():
            entity.needs[name] = Need(
                name=name,
                value=data.get("value", 0.0),
                rate=data.get("rate", 0.0),
                minimum=data.get("minimum", 0.0),
                maximum=data.get("maximum", 1.0),
            )

        return entity
