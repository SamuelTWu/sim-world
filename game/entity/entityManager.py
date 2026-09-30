from pathlib import Path

from .entity import Entity
from .entities.entityFactory import EntityFactory

class EntityManager:
    def __init__(self):
        self.entities = {}
        self.entity_factory = EntityFactory()
        self.next_id = 1

    def spawn(self, name: str) -> Entity:
        entity = self.entity_factory.create(name, self.next_id)
        self.entities[entity.id] = entity
        self.next_id += 1
        return entity

    def destroy(self, entity_id: int):
        self.entities.pop(entity_id, None)

    def get(self, entity_id: int) -> Entity | None:
        return self.entities.get(entity_id)

    def all(self) -> list[Entity]:
        return list(self.entities.values())

    def count(self) -> int:
        return len(self.entities)
