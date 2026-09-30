from typing import Any, Callable

from ..entity import Entity
from ..entityManager import EntityManager
from .attributeSystem import AttributeSystem
from .needSystem import NeedSystem
from .memorySystem import MemorySystem
from .relationshipSystem import RelationshipSystem
from .decisionSystem import DecisionSystem, Decision, Action
from .eventBus import EventBus
from .simContext import SimContext
from .task import Task, RUNNING
from .territory import Territory


class SystemRunner:
    THINK_INTERVAL = 0.25
    SWITCH_MARGIN = 1.3

    def __init__(self, world, entity_manager: EntityManager):
        self.world = world
        self.entity_manager = entity_manager

        self.attribute_system = AttributeSystem()
        self.need_system = NeedSystem()
        self.memory_system = MemorySystem()
        self.relationship_system = RelationshipSystem()
        self.decision_system = DecisionSystem()

        self.events = EventBus()
        self.context = SimContext(world=world, entities=entity_manager, needs=self.need_system, events=self.events, territory=Territory())

        self.action_generators: list[Callable[[Entity, SimContext], list[Action]]] = []
        self.task_factories: dict[str, Callable[[Entity, Action, SimContext], Task | None]] = {}
        self.think_timers: dict[int, float] = {}

    def register_action_generator(self, generator: Callable[[Entity, SimContext], list[Action]]):
        self.action_generators.append(generator)

    def register_task(self, action_name: str, factory: Callable[[Entity, Action, SimContext], Task | None]):
        self.task_factories[action_name] = factory

    def initialize_entity(self, entity: Entity):
        self.attribute_system.initialize(entity)
        self.memory_system.initialize(entity)

    def initialize(self):
        for entity in self.entities():
            self.initialize_entity(entity)

    def entities(self) -> list[Entity]:
        return self.entity_manager.all()

    def get_available_actions(self, entity: Entity) -> list[Action]:
        actions = []

        for generator in self.action_generators:
            actions.extend(generator(entity, self.context))

        return actions

    def run_task(self, entity: Entity, delta_time: float):
        task = entity.task

        if task is None:
            return

        status = task.tick(entity, self.context, delta_time)

        if status != RUNNING:
            entity.task = None
            entity.task_score = 0.0
            self.events.emit("task_finished", entity=entity, task=task, status=status)

    def should_think(self, entity: Entity, delta_time: float) -> bool:
        if entity.task is None:
            return True

        remaining = self.think_timers.get(entity.id, (entity.id * 0.037) % self.THINK_INTERVAL) - delta_time

        if remaining > 0.0:
            self.think_timers[entity.id] = remaining
            return False

        self.think_timers[entity.id] = self.THINK_INTERVAL

        return True

    def think(self, entity: Entity):
        actions = self.get_available_actions(entity)
        decision = self.decision_system.decide(entity, actions, self.context) if actions else None

        if decision is None:
            return

        current = entity.task

        if current is not None and (decision.action.name == current.name or decision.score <= entity.task_score * self.SWITCH_MARGIN):
            return

        self.start_task(entity, decision)

    def start_task(self, entity: Entity, decision: Decision):
        factory = self.task_factories.get(decision.action.name)
        task = factory(entity, decision.action, self.context) if factory else None

        if task is None:
            return

        if entity.task is not None:
            entity.task.cancel(entity, self.context)
            self.events.emit("task_interrupted", entity=entity, task=entity.task)

        entity.task = task
        entity.task_score = decision.score
        self.events.emit("task_started", entity=entity, task=task)

    def update(self, delta_time: float):
        entities = self.entities()

        for entity in entities:
            self.attribute_system.update(entity)
            self.need_system.update(entity, delta_time)
            self.memory_system.update(entity, delta_time)

        self.relationship_system.update(delta_time)
        self.context.territory.update(delta_time)

        for entity in entities:
            self.run_task(entity, delta_time)

            if self.should_think(entity, delta_time):
                self.think(entity)