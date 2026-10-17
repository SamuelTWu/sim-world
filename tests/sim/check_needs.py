from types import SimpleNamespace

from src.simworld.sim.ai.considerations import Consideration, ramp
from src.simworld.sim.ai.decision_system import Action, DecisionSystem
from src.simworld.sim.ai.need_system import DEFAULT_NEEDS, SATISFIES, Need, NeedSystem, drive

passed = 0


def check(condition, message):
    global passed
    assert condition, message
    passed += 1


def pixel(*traits):
    return SimpleNamespace(id=1, needs={}, traits={name: {} for name in traits})


def close(a, b):
    return abs(a - b) < 1e-9


def check_table():
    for name, spec in DEFAULT_NEEDS.items():
        need = Need.from_dict({**spec, "name": name})
        check(0.0 <= need.get_urgency() <= 1.0, f"default need {name} builds and gives a urgency in 0..1")

    check(all(name in DEFAULT_NEEDS for needs in SATISFIES.values() for name in needs), "every need an action satisfies is in the table")
    check(all(0.0 < amount <= 1.0 for needs in SATISFIES.values() for amount in needs.values()), "satisfaction amounts are fractions of the range")

    system = NeedSystem()
    walker, rock, fighter = pixel("roam"), pixel(), pixel("attack")
    system.initialize(walker), system.initialize(rock), system.initialize(fighter)
    check(set(walker.needs) == {"hunger", "boredom", "safety"}, "a pixel with a listed behavior gets the default needs")
    check(rock.needs == {}, "a pixel with none of the listed behaviors gets no needs")
    check(set(fighter.needs) == {"safety"}, "each need applies only to its own behaviors")
    owned = pixel("roam")
    owned.needs["hunger"] = Need("hunger", value=0.9, rate=0.0)
    system.initialize(owned)
    check(owned.needs["hunger"].value == 0.9 and owned.needs["hunger"].rate == 0.0, "a declared need is never overwritten")
    system.initialize(walker)
    check(len(walker.needs) == 3, "initializing twice adds nothing")
    check(walker.needs["hunger"] is not DEFAULT_NEEDS["hunger"] and walker.needs["hunger"] is not pixel("roam").needs.get("hunger"), "every pixel gets its own need object")

    system.update(walker, 100.0)
    check(close(system.urgency(walker, "hunger"), 0.4 ** 2) and close(system.urgency(walker, "boredom"), 1.0) and system.urgency(walker, "safety") == 0.0, "needs rise at their table rates, and safety stays at 0 until something raises it")
    system.increase(walker, "safety", 1.0)
    check(system.urgency(walker, "safety") == 1.0, "raising safety makes it urgent")
    system.update(walker, 50.0)
    check(system.urgency(walker, "safety") == 0.0, "safety falls back on its own")


def check_drive():
    system, walker = NeedSystem(), pixel("roam")
    system.initialize(walker)
    eat, roam = drive("eat"), drive("roam")
    check(eat(walker) == 0.0 + walker.needs["hunger"].get_urgency() and eat(walker) == 0.0, "a satisfied pixel has no drive")
    check(drive("fish")(walker) == 1.0 and eat(pixel()) == 1.0, "an action with no related need, or a pixel without it, is not gated")
    walker.needs["hunger"].value = 0.5
    walker.needs["boredom"].value = 0.9
    check(close(eat(walker), 0.25) and close(roam(walker), 0.9), "the drive is the urgency of the need the action satisfies")
    SATISFIES["rest"] = {"hunger": 0.1, "boredom": 0.1}
    try:
        check(close(drive("rest")(walker), 0.9), "with several needs the drive is the most urgent one")
    finally:
        del SATISFIES["rest"]


def check_completed():
    system, walker = NeedSystem(), pixel("roam")
    system.initialize(walker)
    walker.needs["hunger"].value = 0.8
    walker.needs["boredom"].value = 0.05
    system.completed(walker, "eat")
    check(close(walker.needs["hunger"].value, 0.3), "finishing an action lowers its need by that fraction of the range")
    system.completed(walker, "roam")
    check(walker.needs["boredom"].value == 0.0, "a need never goes below its minimum")
    system.completed(walker, "unknown")
    system.completed(pixel(), "eat")
    check(close(walker.needs["hunger"].value, 0.3), "an unknown action or a pixel without the need changes nothing")
    big = pixel()
    big.needs["hunger"] = Need("hunger", value=10.0, maximum=10.0)
    system.completed(big, "eat")
    check(close(big.needs["hunger"].value, 5.0), "the fraction is of the need's own range")


def check_ranking():
    system, decisions, walker = NeedSystem(), DecisionSystem(), pixel("roam")
    system.initialize(walker)
    decisions.register("eat", Consideration(drive("eat"), ramp(0.1, 1.0), "hunger"))
    decisions.register("roam", Consideration(drive("roam"), ramp(0.1, 1.0), "boredom"))
    options = [Action("roam"), Action("eat")]
    walker.needs["hunger"].value, walker.needs["boredom"].value = 0.9, 0.2
    check(decisions.decide(walker, options).action.name == "eat", "a hungry pixel ranks eating first")
    walker.needs["hunger"].value, walker.needs["boredom"].value = 0.1, 0.9
    check(decisions.decide(walker, options).action.name == "roam", "a bored pixel ranks roaming first")
    system.completed(walker, "roam")
    check(walker.needs["boredom"].value < 0.9 and decisions.evaluate(walker, Action("roam")) < 0.9, "finishing the action lowers its score")


def main():
    for part in (check_table, check_drive, check_completed, check_ranking):
        part()
        print(f"{part.__name__}: ok")

    print(f"all {passed} checks passed")


if __name__ == "__main__":
    main()