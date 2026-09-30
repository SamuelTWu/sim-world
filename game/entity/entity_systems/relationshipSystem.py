from dataclasses import dataclass, field

from ..entity import Entity


@dataclass
class Relationship:
    source: int
    target: int
    trust: float = 0.0
    fear: float = 0.0
    affection: float = 0.0
    resentment: float = 0.0
    familiarity: float = 0.0


@dataclass
class RelationshipSystem:
    relationships: dict[tuple[int, int], Relationship] = field(default_factory=dict)

    def get(self, source: Entity, target: Entity) -> Relationship:
        key = (source.id, target.id)

        if key not in self.relationships:
            self.relationships[key] = Relationship(source.id, target.id)

        return self.relationships[key]

    def set(self, source: Entity, target: Entity, name: str, value: float):
        relationship = self.get(source, target)
        setattr(relationship, name, value)

    def modify(self, source: Entity, target: Entity, name: str, amount: float):
        relationship = self.get(source, target)
        setattr(relationship, name, getattr(relationship, name) + amount)

    def remove(self, source: Entity, target: Entity):
        self.relationships.pop((source.id, target.id), None)

    def all_for(self, source: Entity) -> list[Relationship]:
        return [relationship for relationship in self.relationships.values() if relationship.source == source.id]

    def between(self, source: Entity, target: Entity) -> Relationship | None:
        return self.relationships.get((source.id, target.id))

    def update(self, delta_time: float):
        for relationship in self.relationships.values():
            relationship.familiarity = max(0.0, relationship.familiarity - 0.001 * delta_time)
