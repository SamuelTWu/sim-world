from .entity import Entity
from .entities.entityFactory import EntityFactory


class EntityManager:
    def __init__(self):
        self.entities = {}
        self.entity_factory = EntityFactory()
        self.next_id = 1
        self.pending_removal = set()

    def spawn(self, name: str, owner: int | None = None) -> Entity:
        return self.register(self.entity_factory.create(name, self.next_id, owner))

    def spawn_blueprint(self, blueprint: dict, owner: int | None = None) -> Entity:
        return self.register(self.entity_factory.create_from_blueprint(blueprint, self.next_id, owner))

    def register(self, entity: Entity) -> Entity:
        self.entities[entity.id] = entity
        self.next_id += 1
        return entity

    def kill(self, entity_id: int):
        entity = self.entities.get(entity_id)

        if entity is not None and entity.alive:
            entity.alive = False
            self.pending_removal.add(entity_id)

    def destroy(self, entity_id: int):
        self.entities.pop(entity_id, None)
        self.pending_removal.discard(entity_id)

    def flush(self) -> list[Entity]:
        removed = [self.entities[i] for i in self.pending_removal if i in self.entities]

        for entity_id in list(self.pending_removal):
            self.entities.pop(entity_id, None)

        self.pending_removal.clear()

        return removed

    def get(self, entity_id: int) -> Entity | None:
        return self.entities.get(entity_id)

    def all(self) -> list[Entity]:
        return [entity for entity in self.entities.values() if entity.alive]

    def owned_by(self, owner: int) -> list[Entity]:
        return [entity for entity in self.all() if entity.owner == owner]

    def with_tag(self, tag: str) -> list[Entity]:
        return [entity for entity in self.all() if tag in entity.tags]

    def count(self) -> int:
        return len(self.entities)