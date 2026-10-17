import math
from types import SimpleNamespace

from src.simworld.sim.ai.considerations import CURVES, Consideration, curve_from, linear, logistic, ramp
from src.simworld.sim.ai.decision_system import Action, DecisionSystem
from src.simworld.sim.ai.memory_system import MAX_PER_ENTITY, Memory, MemorySystem
from src.simworld.sim.ai.need_system import DEFAULT_NEEDS, Need, NeedSystem
from src.simworld.sim.ai.relationship_system import MAX_PER_SOURCE, RelationshipSystem
from src.simworld.sim.ai.task import DONE, FAILED, RUNNING, Task

passed = 0


def check(condition, message):
    global passed
    assert condition, message
    passed += 1


def pixel(entity_id):
    return SimpleNamespace(id=entity_id, needs={}, traits={})


def close(a, b, tolerance=1e-9):
    return abs(a - b) <= tolerance


def check_curves():
    for name in CURVES:
        curve = curve_from(name, {"threshold": 0.5} if name == "step" else {"low": 0.2, "high": 0.9} if name == "ramp" else None)
        check(0.0 <= curve(0.0) <= 1.0 and 0.0 <= curve(1.0) <= 1.0, f"{name} stays in 0..1 at the ends")

    check(close(logistic()(0.0), 0.0) and close(logistic()(1.0), 1.0), "logistic reaches exactly 0 and 1")
    check(close(logistic()(0.5), 0.5), "logistic is 0.5 at its midpoint")
    check(logistic(0.5, 0.0) is linear, "zero steepness is linear")
    check(0.0 <= logistic(0.5, 1e9)(0.3) <= 1.0, "a huge steepness does not overflow")
    check(ramp(0.3, 1.0)(0.0) == 0.3 and ramp(0.3, 1.0)(1.0) == 1.0, "ramp keeps its floor")

    for bad in (("nope", None), ("ramp", {"bogus": 1})):
        try:
            curve_from(*bad)
            check(False, f"{bad[0]} is refused")
        except ValueError:
            check(True, f"{bad[0]} is refused")


def check_needs():
    system, entity = NeedSystem(), pixel(1)
    entity.needs["hunger"] = Need("hunger", value=0.0, rate=1.0, maximum=10.0)
    system.update(entity, 4.0)
    check(close(entity.needs["hunger"].value, 4.0), "a need grows by rate times time")
    check(close(system.urgency(entity, "hunger"), 0.4), "urgency is the fraction between minimum and maximum, not the raw value")
    system.update(entity, 100.0)
    check(entity.needs["hunger"].value == 10.0 and system.urgency(entity, "hunger") == 1.0, "a need stops at its maximum")
    system.satisfy(entity, "hunger", 25.0)
    check(entity.needs["hunger"].value == 0.0, "satisfy stops at the minimum")
    system.increase(entity, "hunger", 5.0)
    check(close(system.urgency(entity, "hunger"), 0.5), "increase raises urgency")
    check(system.urgency(entity, "missing", 0.5) == 0.5, "an unknown need gives the caller's default")
    system.satisfy(entity, "missing", 1.0)
    system.increase(entity, "missing", 1.0)
    check("missing" not in entity.needs, "satisfy and increase never create a need")

    shaped = Need("boredom", value=0.5, maximum=1.0, curve="quadratic")
    check(close(shaped.get_urgency(), 0.25), "a named curve shapes the urgency")
    saved = Need.from_dict(Need("boredom", value=0.3, rate=0.1, maximum=2.0, curve="logistic", curve_args={"midpoint": 0.4, "steepness": 6.0}).to_dict())
    check(saved.curve == "logistic" and saved.curve_args == {"midpoint": 0.4, "steepness": 6.0} and saved.maximum == 2.0, "a curve survives to_dict and from_dict")
    check(close(saved.get_urgency(), Need.from_dict(saved.to_dict()).get_urgency()), "a saved need gives the same urgency")
    flat = Need("flat", value=1.0, minimum=1.0, maximum=1.0)
    check(flat.get_urgency() == 0.0, "an empty range gives 0, not a division by zero")

    try:
        Need.from_dict({"name": "x", "curve": "nope"})
        check(False, "a bad curve name in a blueprint is refused")
    except ValueError:
        check(True, "a bad curve name in a blueprint is refused")

    DEFAULT_NEEDS["thirst"] = {"value": 0.2, "rate": 0.01}
    try:
        fresh, owned = pixel(2), pixel(3)
        owned.needs["thirst"] = Need("thirst", value=0.9)
        system.initialize(fresh)
        system.initialize(owned)
        check(fresh.needs["thirst"].value == 0.2 and owned.needs["thirst"].value == 0.9, "default needs are added but never overwrite a declared one")
    finally:
        del DEFAULT_NEEDS["thirst"]


def check_decisions():
    system, entity = DecisionSystem(), pixel(1)
    system.register("a", Consideration(lambda e, a, c: a.data["v"], name="v"))
    system.register("b", Consideration(lambda e, a, c: 0.5, ramp(0.0, 1.0), "half"))
    system.register("b", Consideration(lambda e, a, c: 1.0, name="one"))
    system.register("zero", Consideration(lambda e, a, c: 0.0, name="zero"))
    check(system.evaluate(entity, Action("a", {"v": 0.7})) == 0.7, "one consideration scores its value")
    check(system.evaluate(entity, Action("b")) > 0.5, "several considerations get the compensation bonus")
    check(system.evaluate(entity, Action("zero")) == 0.0, "a zero consideration zeroes the action")
    check(system.evaluate(entity, Action("unknown")) == 0.0, "an action with no considerations scores 0")
    decision = system.decide(entity, [Action("a", {"v": 0.2}), Action("a", {"v": 0.9}), Action("zero"), Action("a", {"v": 0.9})])
    check(decision.action.data["v"] == 0.9 and decision.score == 0.9, "decide picks the best action")
    first, second = Action("a", {"v": 0.9, "n": 1}), Action("a", {"v": 0.9, "n": 2})
    check(system.decide(entity, [first, second]).action is first, "ties go to the first candidate")
    check(system.decide(entity, [Action("zero"), Action("unknown")]) is None and system.decide(entity, []) is None, "nothing worth doing gives None")
    rows = system.explain(entity, Action("b"))
    check([row[0] for row in rows] == ["half", "one"] and rows[0][1] == 0.5, "explain lists each consideration with its raw and curved value")


def check_memory():
    system, entity = MemorySystem(), pixel(1)
    system.remember(entity, Memory("place", {"x": 10, "y": 10, "kind": "water"}, key="water:1"))
    again = system.remember(entity, Memory("place", {"x": 10, "y": 11, "kind": "water"}, strength=1.0, importance=0.5, key="water:1"))
    check(len(system.recall(entity)) == 1 and again.importance == 0.5, "remembering the same key reinforces instead of adding")
    system.remember(entity, Memory("place", {"x": 100, "y": 100, "kind": "water"}, key="water:2"))
    system.remember(entity, Memory("place", {"x": 50, "y": 50, "kind": "storage"}, key="storage:1"))
    check(system.nearest(entity, "place", 90, 90).key == "water:2", "nearest finds the closest remembered place")
    check(system.nearest(entity, "place", 90, 90, kind="storage").key == "storage:1", "nearest can filter by kind")
    check(system.nearest(entity, "enemy", 0, 0) is None, "nearest of an unknown type is None")
    check(system.recall(entity, "place", 1)[0].importance == 0.5, "recall puts the important memory first")

    for index in range(MAX_PER_ENTITY * 2):
        system.remember(entity, Memory("noise", {"i": index}, strength=0.5))

    check(len(system.recall(entity)) == MAX_PER_ENTITY, "memories are capped per pixel")
    check(len(system.recall(entity, "place")) == 3, "the cap drops the weakest, not the places")

    slow, fast = MemorySystem(decay_rate=0.01), MemorySystem(decay_rate=0.01)
    one, two = pixel(1), pixel(1)
    slow.remember(one, Memory("t")), fast.remember(two, Memory("t"))

    for _ in range(100):
        slow.update(one, 1.0)

    fast.update(two, 100.0)
    check(close(slow.recall(one)[0].strength, fast.recall(two)[0].strength, 1e-9), "decay gives the same result whatever the step size")
    fast.update(two, 10000.0)
    check(fast.recall(two) == [], "faded memories are forgotten")

    system.update(entity, 1.0)
    restored = MemorySystem.from_dict(system.to_dict())
    check(restored.to_dict() == system.to_dict() and restored.nearest(entity, "place", 90, 90).key == "water:2", "memory round-trips through to_dict")
    system.remove(entity)
    check(system.recall(entity) == [] and system.to_dict() == {}, "removing a pixel clears its memory")


def check_relationships():
    system, a, b, c = RelationshipSystem(), pixel(1), pixel(2), pixel(3)
    check(system.between(a, b) is None and system.get(a, b).trust == 0.0, "reading a relationship does not create one")
    check(system.outgoing == {}, "nothing is stored by reading")
    system.modify(a, b, "trust", 0.5)
    system.modify(a, b, "trust", 0.25)
    system.set(a, c, "familiarity", 0.002)
    check(system.between(a, b).trust == 0.75 and len(system.all_for(a)) == 2 and system.all_for(b) == [], "modify and set store, all_for lists what a pixel has")
    system.update(1.0)
    check(close(system.between(a, c).familiarity, 0.001), "familiarity fades")
    system.update(10.0)
    check(system.between(a, c) is None and system.between(a, b) is not None, "a relationship that fades to nothing is deleted")
    system.modify(b, a, "fear", 0.3)
    system.remove_entity(1)
    check(system.between(a, b) is None and system.between(b, a) is None and system.outgoing == {} and system.incoming == {}, "removing a pixel removes both directions and the index")
    system.modify(a, b, "resentment", 0.4)
    copy = RelationshipSystem.from_dict(system.to_dict())
    check(copy.to_dict() == system.to_dict() and copy.incoming == system.incoming, "relationships round-trip through to_dict")

    crowded, source = RelationshipSystem(), pixel(1)

    for index in range(MAX_PER_SOURCE + 20):
        crowded.modify(source, pixel(100 + index), "trust", 0.01 * (index + 1))

    kept = crowded.all_for(source)
    check(len(kept) == MAX_PER_SOURCE and max(item.target for item in kept) == 100 + MAX_PER_SOURCE + 19, "relationships are capped per pixel, keeping the strongest")
    check(all(len(sources) == 1 for sources in crowded.incoming.values()) and len(crowded.incoming) == MAX_PER_SOURCE, "the reverse index stays in step with the cap")


def check_tasks():
    class Walk(Task):
        name = "walk"

        def step(self, entity, context, delta_time):
            self.state["steps"] = self.state.get("steps", 0) + 1
            return self.fail("blocked") if self.data["blocked"] else RUNNING if self.elapsed < 1.0 else DONE

    task = Walk(blocked=False)
    check(task.tick(None, None, 0.5) == RUNNING and task.tick(None, None, 0.6) == DONE and task.state["steps"] == 2, "a task runs until done and keeps its state")
    restored = Walk.from_dict(task.to_dict())
    check(restored.elapsed == task.elapsed and restored.state == {"steps": 2} and restored.data == {"blocked": False}, "state and elapsed survive to_dict and from_dict")
    blocked = Walk(blocked=True)
    check(blocked.tick(None, None, 0.1) == FAILED and blocked.reason == "blocked" and Walk.from_dict(blocked.to_dict()).reason == "blocked", "fail records a reason that is saved")
    check(Task().finish(None, None, DONE) is None, "finish exists and does nothing by default")


def main():
    for part in (check_curves, check_needs, check_decisions, check_memory, check_relationships, check_tasks):
        part()
        print(f"{part.__name__}: ok")

    print(f"all {passed} checks passed")


if __name__ == "__main__":
    main()