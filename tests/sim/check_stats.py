from src.simworld.sim.ai import stats
from src.simworld.sim.ai.considerations import Consideration
from src.simworld.sim.ai.decision_system import Action, DecisionSystem
from src.simworld.sim.ai.need_system import Need
from src.simworld.sim.ai.stats import STATS, names, read, reader, resolve, valid

passed = 0


def check(condition, message):
    global passed
    assert condition, message
    passed += 1


class Pixel:
    def __init__(self):
        self.health, self.max_health, self.energy, self.max_energy, self.age = 5.0, 10.0, 1.0, 4.0, 12.5
        self.needs = {"hunger": Need("hunger", value=5.0, maximum=10.0), "boredom": Need("boredom", value=0.5, curve="quadratic")}
        self.inventory = {"fish": 3.0, "wood": 1.5}
        self.tags = {"fisher"}
        self.props = {"max_speed": 2.0}

    def carried(self):
        return sum(self.inventory.values())

    def prop(self, name, default=None):
        return self.props.get(name, 0.0)


def check_reading():
    pixel = Pixel()
    check(read(pixel, "health") == 0.5 and read(pixel, "energy") == 0.25, "health and energy are fractions of their maximum")
    check(read(pixel, "age") == 12.5 and read(pixel, "carried") == 4.5, "age and carried are raw")
    check(read(pixel, "need:hunger") == 0.5, "need:<name> is the normalized urgency, not the raw value")
    check(abs(read(pixel, "need:boredom") - 0.25) < 1e-9, "need:<name> includes the need's curve")
    check(read(pixel, "need_value:hunger") == 5.0, "need_value:<name> is the raw value")
    check(read(pixel, "need:thirst") == 0.0 and read(pixel, "need_value:thirst") == 0.0, "a need the pixel does not have reads 0")
    check(read(pixel, "inventory:fish") == 3.0 and read(pixel, "inventory:stone") == 0.0, "inventory:<resource> reads the amount, 0 when none")
    check(read(pixel, "prop:max_speed") == 2.0, "prop:<name> reads a property")
    check(read(pixel, "tag:fisher") == 1.0 and read(pixel, "tag:miner") == 0.0, "tag:<name> is 1 or 0")
    pixel.needs["hunger"].value = 10.0
    check(read(pixel, "need:hunger") == 1.0, "readings follow the live value")


def check_names():
    for good in ("health", "need:hunger", "inventory:raw-fish", "need_value:a_b"):
        check(valid(good), f"{good} is a valid name")

    for bad in ("", "nope", "need:", ":hunger", "need:a b", "Health", "need:" + "x" * 40, "bogus:thing", "a:b:c", None, 5, ["health"]):
        check(not valid(bad), f"{bad!r} is not a valid name")
        check(read(Pixel(), bad, default=-1.0) == -1.0, f"reading {bad!r} gives the default")

    check(names()[0] == "health" and "need:<name>" in names(), "names lists every stat and family for the editor")
    check(set(STATS) <= set(names()) and set(stats.DESCRIPTIONS) >= set(STATS), "every static stat has a description")
    check(resolve("health") is resolve("health"), "resolving is cached")


def check_reader():
    pixel = Pixel()
    check(reader("need:hunger")(pixel) == 0.5, "a reader returns the stat")
    check(reader("age", 0.0, 25.0)(pixel) == 0.5, "a reader scales a raw stat into 0..1")
    check(reader("age", 0.0, 10.0)(pixel) == 1.0 and reader("age", 20.0, 30.0)(pixel) == 0.0, "a reader clamps to 0..1")

    for bad in (("nope",), ("age", 5.0, 5.0)):
        try:
            reader(*bad)
            check(False, f"reader{bad} is refused")
        except ValueError:
            check(True, f"reader{bad} is refused")

    system = DecisionSystem()
    system.register("eat", Consideration(reader("need:hunger"), name="hunger"))
    check(system.evaluate(pixel, Action("eat")) == 0.5, "a stat reader works as a consideration")


def main():
    for part in (check_reading, check_names, check_reader):
        part()
        print(f"{part.__name__}: ok")

    print(f"all {passed} checks passed")


if __name__ == "__main__":
    main()