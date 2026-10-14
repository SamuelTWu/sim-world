import traceback
from typing import Callable

from ..entity import Entity
from ..entityManager import EntityManager
from ..behavior.behaviorManager import BehaviorManager
from .needSystem import NeedSystem
from .memorySystem import MemorySystem
from .relationshipSystem import RelationshipSystem
from .decisionSystem import DecisionSystem, Decision, Action
from .eventBus import EventBus
from .activity import Activity
from .counters import Counters, count
from .transientEvents import TransientEventLog
from .simContext import SimContext
from .stimulus import StimulusField
from .orders import ORDER_KEY, follow_orders, order_finished
from .task import Task, RUNNING, FAILED
from .territory import Territory
from .territoryRules import register_territory_rules


class SystemRunner:
    THINK_INTERVAL = 0.25
    SWITCH_MARGIN = 1.3

    def __init__(self, world, entity_manager: EntityManager, behaviors: BehaviorManager, maps=None, rng=None):
        self.world = world
        self.entity_manager = entity_manager
        self.rng = rng
        self.behaviors = behaviors
        self.need_system = NeedSystem()
        self.memory_system = MemorySystem()
        self.relationship_system = RelationshipSystem()
        self.decision_system = DecisionSystem()
        self.events = EventBus()
        self.transient_events = TransientEventLog()  # shots, impacts: noted here, sent to players as events (transientEvents.py)
        self.activity = Activity()  # near / far tiers for the expensive systems (activity.py); Simulation.step refreshes it every tick
        self.counters = Counters()
        self.activity.counters = self.counters  # work done this window (tile checks, attacks...), read by the server's metrics (9.1)
        self.order_notices = []  # orders that failed, for the server to tell the player (see orders.notify)
        self.context = SimContext(world=world, entities=entity_manager, needs=self.need_system, events=self.events, territory=Territory(), stimuli=StimulusField(), maps=maps, rng=self.rng, transient_events=self.transient_events, counters=self.counters, activity=self.activity)
        self.action_generators: list[Callable[[Entity, SimContext], list[Action]]] = []
        self.task_factories: dict[str, Callable[[Entity, Action, SimContext], Task | None]] = {}
        self.think_timers: dict[int, float] = {}
        self.context.spawn = self.spawn_blueprint_at
        self.behaviors.register_all(self)
        register_territory_rules(self)

    def register_action_generator(self, generator: Callable[[Entity, SimContext], list[Action]]):
        self.action_generators.append(generator)

    def register_task(self, action_name: str, factory: Callable[[Entity, Action, SimContext], Task | None]):
        self.task_factories[action_name] = factory

    def spawn_blueprint(self, blueprint: dict, owner: int | None = None) -> Entity:
        entity = self.entity_manager.spawn_blueprint(blueprint, owner)
        self.behaviors.apply(entity)
        self.memory_system.initialize(entity)
        self.events.emit("entity_spawned", entity=entity)
        return entity

    def spawn_blueprint_at(self, blueprint: dict, owner: int | None, x: float, y: float) -> Entity:
        """Default for SimContext.spawn (Simulation replaces it with Simulation.spawn_pixel, which also records who owns the pixel)."""
        entity = self.spawn_blueprint(blueprint, owner)
        entity.position.x, entity.position.y = x, y
        return entity

    def entities(self) -> list[Entity]:
        return self.entity_manager.all()

    def get_available_actions(self, entity: Entity) -> list[Action]:
        actions = []

        for generator in self.action_generators:
            actions.extend(generator(entity, self.context))

        return actions

    def release_snap(self, entity: Entity):
        snap = entity.components.get("snap")

        if snap is not None and (entity.position.x, entity.position.y) == snap["cell"]:
            entity.position.x, entity.position.y = snap["free"]

    def apply_snap(self, entity: Entity):
        size = entity.prop("snap_to_grid")
        free = (entity.position.x, entity.position.y)
        cell = ((free[0] // size + 0.5) * size, (free[1] // size + 0.5) * size)
        entity.components["snap"] = {"free": free, "cell": cell}
        entity.position.x, entity.position.y = cell

    def age_entity(self, entity: Entity, delta_time: float):
        entity.age += delta_time

        if not entity.statuses:
            return

        for status in entity.statuses:
            status.age += delta_time

        expired = [status for status in entity.statuses if status.age >= status.duration]

        if expired:
            entity.statuses = [status for status in entity.statuses if status.age < status.duration]

            for status in expired:
                self.events.emit("status_expired", entity=entity, status=status)

    def run_task(self, entity: Entity, delta_time: float):
        task = entity.task

        if task is None:
            return

        try:
            status = task.tick(entity, self.context, delta_time)
        except Exception:
            # One broken task must not stop the whole simulation (and with it the server): log it, fail the task.
            traceback.print_exc()
            status = FAILED

        if status != RUNNING:
            order_finished(self, entity, task, status)
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
        count(self.context, "thinks")
        if follow_orders(self, entity):
            return

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

    def cleanup_removed(self):
        for removed in self.entity_manager.flush():
            if removed.task is not None:
                removed.task.cancel(removed, self.context)
                removed.task = None

            self.think_timers.pop(removed.id, None)
            self.activity.forget(removed.id)
            self.memory_system.remove(removed)
            self.relationship_system.remove_entity(removed.id)
            self.events.emit("entity_removed", entity=removed)

    def update(self, delta_time: float):
        """One tick. Aging, the current task and removal run for every pixel every tick; the needs, memory and thinking only when the
        pixel is due (see activity.py): always for an ACTIVE pixel, once in a while, with all the time that passed, for a FAR one."""
        entities = self.entities()
        activity = self.activity
        tick = self.context.tick
        due = []

        for entity in entities:
            self.age_entity(entity, delta_time)
            step = activity.due_dt(entity, tick, delta_time)
            due.append(step)

            if step is not None:
                self.need_system.update(entity, step)
                self.memory_system.update(entity, step)

        self.relationship_system.update(delta_time)
        self.context.territory.update(delta_time)
        self.context.stimuli.update(delta_time)
        self.events.emit("frame", delta_time=delta_time)

        for entity, step in zip(entities, due):
            if not entity.alive:
                continue

            snaps = entity.has_prop("snap_to_grid") and entity.prop("snap_to_grid") > 0

            if snaps:
                self.release_snap(entity)

            self.run_task(entity, delta_time)

            if snaps:
                self.apply_snap(entity)

            if entity.alive and (entity.task is not None or entity.id not in activity.cell_of):
                activity.moved(entity)  # a pixel arriving in a new cell, or a new pixel, wakes the sleepers next to it (9.3)

            if step is None:
                count(self.context, "think_deferred")
            elif entity.alive and self.should_think(entity, step):
                self.think(entity)

                if entity.alive:
                    if entity.task is None and ORDER_KEY not in entity.components:
                        activity.idle_think(entity, tick)  # nothing to do: after a few of these in a row it sleeps
                    else:
                        activity.busy_think(entity)

        self.cleanup_removed()
        self.context.tick += 1