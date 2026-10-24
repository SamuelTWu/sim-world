from .entity import Entity
from .entity_factory import EntityFactory
from ..core.roster import Roster


class EntityManager:
    def __init__(self):
        self.entities: dict[int, Entity] = {}
        self.entity_factory = EntityFactory()
        self.next_id = 1
        self.pending_removal: set[int] = set()
        self.roster = Roster()

    def allocate_id(self) -> int:
        entity_id = self.next_id
        self.next_id += 1
        return entity_id

    def spawn(self, name: str, owner: int | None = None) -> Entity:
        return self.register(self.entity_factory.create(name, self.allocate_id(), owner))

    def spawn_blueprint(self, blueprint: dict, owner: int | None = None) -> Entity:
        return self.register(self.entity_factory.create_from_blueprint(blueprint, self.allocate_id(), owner))

    def register(self, entity: Entity) -> Entity:
        if entity.id <= 0:
            raise ValueError(f"Entity ID must be positive, got {entity.id}")

        if entity.id in self.entities:
            raise ValueError(f"Entity ID already exists: {entity.id}")

        self.entities[entity.id] = entity
        self.next_id = max(self.next_id, entity.id + 1)
        self.roster.sync(entity)
        return entity

    def restore(self, data: dict) -> Entity:
        entity = Entity.from_dict(data)
        return self.register(entity)

    def touch(self, entity: Entity):
        self.roster.sync(entity)

    def add_status(self, entity: Entity, status):
        entity.statuses = [other for other in entity.statuses if other.name != status.name]
        entity.statuses.append(status)
        self.roster.sync(entity)

    def set_statuses(self, entity: Entity, statuses: list):
        entity.statuses = statuses
        self.roster.sync(entity)

    def set_trait(self, entity: Entity, name: str, values: dict):
        entity.traits[name] = values
        self.roster.sync(entity)

    def drop_trait(self, entity: Entity, name: str):
        entity.traits.pop(name, None)
        self.roster.sync(entity)

    def set_task(self, entity: Entity, task, score: float = 0.0):
        entity.task = task
        entity.task_score = score
        self.roster.sync(entity)

    def kill(self, entity_id: int):
        entity = self.entities.get(entity_id)

        if entity is not None and entity.alive:
            entity.alive = False
            self.pending_removal.add(entity_id)
            self.roster.drop(entity)

    def destroy(self, entity_id: int):
        entity = self.entities.pop(entity_id, None)

        if entity is not None:
            self.roster.drop(entity)

        self.pending_removal.discard(entity_id)

    def flush(self) -> list[Entity]:
        removed = [self.entities[i] for i in self.pending_removal if i in self.entities]

        for entity in removed:
            self.roster.drop(entity)
            self.entities.pop(entity.id, None)

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