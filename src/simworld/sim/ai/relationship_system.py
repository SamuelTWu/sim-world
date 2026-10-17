from dataclasses import dataclass, field
from typing import Any

MAX_PER_SOURCE = 64
DECAY = {"familiarity": 0.001}
FIELDS = ("trust", "fear", "affection", "resentment", "familiarity")


@dataclass
class Relationship:
    source: int
    target: int
    trust: float = 0.0
    fear: float = 0.0
    affection: float = 0.0
    resentment: float = 0.0
    familiarity: float = 0.0

    def strength(self) -> float:
        return sum(abs(getattr(self, name)) for name in FIELDS)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, **{name: getattr(self, name) for name in FIELDS}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relationship":
        return cls(source=int(data["source"]), target=int(data["target"]), **{name: float(data.get(name, 0.0)) for name in FIELDS})


@dataclass
class RelationshipSystem:
    outgoing: dict[int, dict[int, Relationship]] = field(default_factory=dict)
    incoming: dict[int, set[int]] = field(default_factory=dict)

    def between(self, source, target) -> Relationship | None:
        return self.outgoing.get(source.id, {}).get(target.id)

    def get(self, source, target) -> Relationship:
        return self.between(source, target) or Relationship(source.id, target.id)

    def stored(self, source, target) -> Relationship:
        known = self.outgoing.setdefault(source.id, {})
        relationship = known.get(target.id)

        if relationship is None:
            relationship = known[target.id] = Relationship(source.id, target.id)
            self.incoming.setdefault(target.id, set()).add(source.id)

            if len(known) > MAX_PER_SOURCE:
                weakest = min((other for other in known.values() if other is not relationship), key=Relationship.strength)
                self.drop(weakest.source, weakest.target)

        return relationship

    def set(self, source, target, name: str, value: float):
        setattr(self.stored(source, target), name, value)

    def modify(self, source, target, name: str, amount: float):
        relationship = self.stored(source, target)
        setattr(relationship, name, getattr(relationship, name) + amount)

    def all_for(self, source) -> list[Relationship]:
        return list(self.outgoing.get(source.id, {}).values())

    def drop(self, source_id: int, target_id: int):
        known = self.outgoing.get(source_id)

        if known is not None and known.pop(target_id, None) is not None:
            sources = self.incoming.get(target_id)

            if sources is not None:
                sources.discard(source_id)

                if not sources:
                    del self.incoming[target_id]

            if not known:
                del self.outgoing[source_id]

    def remove(self, source, target):
        self.drop(source.id, target.id)

    def remove_entity(self, entity_id: int):
        for source_id in list(self.incoming.pop(entity_id, ())):
            self.drop(source_id, entity_id)

        for target_id in list(self.outgoing.get(entity_id, ())):
            self.drop(entity_id, target_id)

    def update(self, delta_time: float):
        for source_id, known in list(self.outgoing.items()):
            for target_id, relationship in list(known.items()):
                for name, rate in DECAY.items():
                    value = getattr(relationship, name)
                    setattr(relationship, name, max(0.0, value - rate * delta_time) if value > 0.0 else min(0.0, value + rate * delta_time))

                if relationship.strength() == 0.0:
                    self.drop(source_id, target_id)

    def to_dict(self) -> list[dict[str, Any]]:
        return [relationship.to_dict() for known in self.outgoing.values() for relationship in known.values()]

    @classmethod
    def from_dict(cls, data: list[dict[str, Any]]) -> "RelationshipSystem":
        system = cls()

        for item in data:
            relationship = Relationship.from_dict(item)
            system.outgoing.setdefault(relationship.source, {})[relationship.target] = relationship
            system.incoming.setdefault(relationship.target, set()).add(relationship.source)

        return system