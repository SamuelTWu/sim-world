import traceback
from typing import Callable

from ..entities.entity import Entity
from ..entities.entity_manager import EntityManager
from ..behaviors.behavior_manager import BehaviorManager
from ..ai.need_system import NeedSystem
from ..ai.memory_system import MemorySystem
from ..ai.relationship_system import RelationshipSystem
from ..ai.decision_system import DecisionSystem, Decision, Action
from .event_bus import EventBus
from .activity import Activity
from ..perception.proximity import ProximityIndex
from .counters import Counters, count
from .transient_events import TransientEventLog
from .sim_context import SimContext
from ..perception.stimulus import StimulusField
from ..ai.orders import ORDER_KEY, follow_orders, order_finished
from ..ai.task import Task, RUNNING, FAILED, DONE
from ..territory.territory import Territory
from ..territory.territory_rules import register_territory_rules
from .limits import Limits



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
        self.context.proximity = ProximityIndex(entity_manager)
        self.limits = Limits()
        self.limits.counters = self.counters
        self.context.limits = self.limits
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
        self.need_system.initialize(entity)
        self.entity_manager.touch(entity)
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
            self.entity_manager.set_statuses(entity, [status for status in entity.statuses if status.age < status.duration])

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
            count(self.context, "task_errors")
            status = FAILED

        if status != RUNNING:
            order_finished(self, entity, task, status)
            task.finish(entity, self.context, status)
            if status == DONE:
                self.need_system.completed(entity, task.name)

            self.entity_manager.set_task(entity, None, 0.0)
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

    def would_think(self, entity, delta_time):
        if entity.task is None:
            return True

        return self.think_timers.get(entity.id, (entity.id * 0.037) % self.THINK_INTERVAL) - delta_time <= 0.0

    def over_think_budget(self, entities, thinks, tick):
        budget = self.limits.max_thinks

        if budget <= 0:
            return ()

        wanting = [index for index, step in enumerate(thinks) if step is not None and entities[index].alive and self.would_think(entities[index], step)]

        if len(wanting) <= budget:
            return ()

        priority = self.limits.think_priority
        wanting.sort(key=lambda index: priority(entities[index].id, tick))
        return set(wanting[budget:])

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

        self.entity_manager.set_task(entity, task, decision.score)
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
        """One tick. Only the roster is visited (sim/core/roster.py): entities with traits, a task, needs, statuses, a snap size or an owner; items, blocks and trees that have none of those cost nothing here. Aging, the current task (with its terrain and collision tests) and removal run for every pixel every tick, always. The
        needs, memory and thinking of a pixel, and the relationships, territory and stimuli of the world, run at the rates in activity.RATES
        (every tick unless the table says otherwise), with all the time that passed handed over when they do."""
        entities = [entity for entity in self.entity_manager.roster.active_list() if entity.alive]
        activity = self.activity
        tick = self.context.tick
        thinks = []

        for entity in entities:
            self.age_entity(entity, delta_time)
            state = activity.state(entity, tick)
            step = activity.due("needs", entity, state, delta_time, tick)

            if step is not None:
                self.need_system.update(entity, step)

            step = activity.due("memory", entity, state, delta_time, tick)

            if step is not None:
                self.memory_system.update(entity, step)

            thinks.append(activity.due("think", entity, state, delta_time, tick))

        step = activity.global_due("relationships", tick, delta_time)

        if step is not None:
            self.relationship_system.update(step)

        step = activity.global_due("territory", tick, delta_time)

        if step is not None:
            self.context.territory.update(step)

        step = activity.global_due("stimuli", tick, delta_time)

        if step is not None:
            self.context.stimuli.update(step)

        self.events.emit("frame", delta_time=delta_time)

        denied = self.over_think_budget(entities, thinks, tick)
        budget = self.limits.max_thinks
        thought = 0
        for index, (entity, step) in enumerate(zip(entities, thinks)):
            if not entity.alive:
                continue
            if entity.id in activity.frozen:
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
            
            elif index in denied or (budget > 0 and thought >= budget and entity.alive and self.would_think(entity, step)):
                activity.defer("think", entity, step)
                count(self.context, "think_capped")
            
            elif entity.alive and self.should_think(entity, step):
                thought+=1
                self.think(entity)

                if entity.alive:
                    if entity.task is None and ORDER_KEY not in entity.components:
                        activity.idle_think(entity, tick)  # nothing to do: after a few of these in a row it sleeps
                    else:
                        activity.busy_think(entity)

        self.cleanup_removed()
        self.context.tick += 1