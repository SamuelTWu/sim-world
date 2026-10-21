import sys
from types import SimpleNamespace

from src.simworld.server import dev_commands as dev
from src.simworld.server.dev_time import init_time
from src.simworld.sim.dev import tools
from src.simworld.sim.entities.entity import Entity, StatusEffect, Vec3

failures = []
UNITS = 32


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Need:
    def __init__(self, value, urgency):
        self.value, self.urgency = value, urgency

    def get_urgency(self):
        return self.urgency


class BrokenNeed:
    value = 1.0

    def get_urgency(self):
        raise RuntimeError("broken need")


class Task:
    name = "roam"


class Activity:
    def __init__(self):
        self.frozen = set()
        self.unfrozen = []

    def unfreeze(self, pixel_id):
        self.frozen.discard(pixel_id)
        self.unfrozen.append(pixel_id)


class Manager:
    def __init__(self):
        self.things = {}

    def get(self, pixel_id):
        return self.things.get(pixel_id)

    def kill(self, pixel_id):
        self.things[pixel_id].alive = False


def make_sim():
    sim = SimpleNamespace(sandbox=True, tick=0, entity_manager=Manager(), systems=SimpleNamespace(activity=Activity(), counters=None), world=SimpleNamespace(width=100, height=100))
    return sim


def wolf(pixel_id=7):
    entity = Entity(pixel_id, position=Vec3(40.5 * UNITS, 22.25 * UNITS), sprite_id="wolf", name="Wolf", blueprint_name="wolf", owner=3, health=40.0, max_health=50.0, energy=25.0, max_energy=100.0, age=12.5)
    entity.needs = {"hunger": Need(65.0, 0.35), "thirst": Need(90.0, 0.1)}
    entity.inventory = {"wood": 3.0, "stone": 1.0}
    entity.props = {"max_speed": 2.0, "temperature": 20.0}
    entity.tags = {"animal", "wolf"}
    entity.statuses = [StatusEffect("slow", 5.0, 0.5, None, 1.5)]
    entity.task, entity.task_score = Task(), 0.42
    return entity


def problem(call):
    try:
        call()
    except tools.DevError as error:
        return str(error)
    except Exception as error:
        return f"WRONG {type(error).__name__}: {error}"

    return None


def plain(value):
    if isinstance(value, dict):
        return all(isinstance(key, str) and plain(item) for key, item in value.items())

    if isinstance(value, list):
        return all(plain(item) for item in value)

    return value is None or type(value) in (int, float, str, bool)


sim = make_sim()
entity = wolf()
sim.entity_manager.things[7] = entity
found = tools.inspect_pixel(sim, 7, UNITS)
stats = found.data["stats"]

check("inspect returns the base stats as the registry reads them", stats["health"] == 0.8 and stats["energy"] == 0.25 and stats["age"] == 12.5 and stats["carried"] == 4.0, str(stats))
check("needs: urgency and raw value", stats["need:hunger"] == 0.35 and stats["need_value:hunger"] == 65.0 and stats["need:thirst"] == 0.1, str(stats))
check("inventory, props, tags and statuses are listed", stats["inventory:wood"] == 3.0 and stats["inventory:stone"] == 1.0 and stats["prop:max_speed"] == 2.0 and stats["tag:animal"] == 1.0 and stats["tag:wolf"] == 1.0 and stats["status:slow"] == 0.5, str(stats))
check("the task and its score", found.data["task"] == {"name": "roam", "score": 0.42}, str(found.data["task"]))
check("position in tiles, owner, names", (found.data["x"], found.data["y"]) == (40.5, 22.25) and found.data["owner"] == 3 and found.data["name"] == "Wolf" and found.data["sprite"] == "wolf" and found.data["blueprint"] == "wolf" and found.data["id"] == 7)
check("the status detail has its remaining time", found.data["statuses"] == [{"name": "slow", "strength": 0.5, "left": 3.5}], str(found.data["statuses"]))
check("not frozen by default, and no failures line without components['failures']", found.data["frozen"] is False and "failures" not in found.data and "failed" not in found.text)
check("data is plain msgpack-safe values", plain(found.data), str(found.data))
check("the text names it and shows the pieces", all(part in found.text for part in ("Wolf #7 at 40.5,22.25", "owner 3", "health 80%", "energy 25%", "age 12.5s", "hunger 0.35", "wood 3", "max_speed 2", "slow 0.5", "animal, wolf", "task: roam (score 0.42)")), found.text)
check("the text is short", len(found.text) <= 900 and found.text.count("\n") <= 8, found.text)

sim.systems.activity.frozen.add(7)
check("a frozen entity says so", tools.inspect_pixel(sim, 7, UNITS).data["frozen"] is True and "frozen" in tools.inspect_pixel(sim, 7, UNITS).text.splitlines()[0])

entity.task = None
check("no task is shown as none", tools.inspect_pixel(sim, 7, UNITS).data["task"] is None and "task: none" in tools.inspect_pixel(sim, 7, UNITS).text)

entity.components["failures"] = [f"reason {i}" for i in range(8)]
failed = tools.inspect_pixel(sim, 7, UNITS)
check("failures: the last five, once components['failures'] exists", failed.data["failures"] == [f"reason {i}" for i in range(3, 8)] and "reason 7" in failed.text and "failed:" in failed.text, str(failed.data.get("failures")))
entity.components["failures"] = "not a list"
check("a malformed failures value is left out", "failures" not in tools.inspect_pixel(sim, 7, UNITS).data)
entity.components["failures"] = []
check("an empty failures list is left out", "failures" not in tools.inspect_pixel(sim, 7, UNITS).data)

entity.needs["bad name!"] = Need(1.0, 1.0)
entity.needs["broken"] = BrokenNeed()
entity.inventory["x" * 40] = 1.0
entity.props["strange key"] = 1.0
survived = tools.inspect_pixel(sim, 7, UNITS)
check("names the registry cannot read, and needs that raise, are skipped without failing", "need:hunger" in survived.data["stats"] and not any(" " in key or "bad" in key for key in survived.data["stats"]) and "need:broken" not in survived.data["stats"], str(sorted(survived.data["stats"])))
check("a need whose value works but urgency raises still shows the value", survived.data["stats"].get("need_value:broken") == 1.0)

crowd = wolf(8)
crowd.inventory = {f"res{i}": float(i) for i in range(200)}
crowd.props = {f"prop{i}": float(i) for i in range(200)}
crowd.tags = {f"tag{i}" for i in range(200)}
crowd.components["failures"] = ["a very long reason " * 20] * 9
sim.entity_manager.things[8] = crowd
big = tools.inspect_pixel(sim, 8, UNITS)
check("a crowded entity still gives a short text and a full data dict", len(big.text) <= 900 and "(+" in big.text and len(big.data["stats"]) > 400 and all(len(line) <= 120 for line in big.data["failures"]), f"{len(big.text)} {len(big.data['stats'])}")
check("and the data is still plain", plain(big.data))

odd = wolf(9)
odd.health = float("nan")
odd.age = float("inf")
odd.owner = None
sim.entity_manager.things[9] = odd
odd_info = tools.inspect_pixel(sim, 9, UNITS)
check("non-finite stats are left out of the data", "health" not in odd_info.data["stats"] and "age" not in odd_info.data["stats"] and plain(odd_info.data))
check("an entity with no owner shows none", odd_info.data["owner"] is None and "owner" not in odd_info.text)

dead = wolf(10)
dead.alive = False
sim.entity_manager.things[10] = dead
check("inspecting an unknown or dead id says there is no such entity", problem(lambda: tools.inspect_pixel(sim, 99, UNITS)) == "no entity #99" and problem(lambda: tools.inspect_pixel(sim, 10, UNITS)) == "no entity #10")

sim.systems.activity.frozen.add(7)
woke = tools.wake_pixel(sim, 7)
check("wake unfreezes a frozen entity with the activity call", woke.was_frozen and sim.systems.activity.unfrozen == [7] and 7 not in sim.systems.activity.frozen and woke.label == "Wolf", str(woke))
check("wake of an entity that is not frozen does nothing", tools.wake_pixel(sim, 7).was_frozen is False and sim.systems.activity.unfrozen == [7])
check("wake of an unknown or dead id says there is no such entity", problem(lambda: tools.wake_pixel(sim, 99)) == "no entity #99" and problem(lambda: tools.wake_pixel(sim, 10)) == "no entity #10")
nothing = make_sim()
nothing.entity_manager.things[7] = wolf()
nothing.systems = SimpleNamespace()
check("wake without an activity system is a readable error", problem(lambda: tools.wake_pixel(nothing, 7)) == "the activity system is not available")


def server_for(flag=True):
    server = SimpleNamespace(sim=make_sim())
    server.sim.sandbox = flag
    server.sim.entity_manager.things[7] = wolf()
    init_time(server)
    return server


def ask(server, what, **args):
    return dev.run_dev(server, SimpleNamespace(player_id=3), what, args)


server = server_for()
result = ask(server, "inspect", id=7)
check("dev inspect: text is the summary and data the full dict", result.ok and result.text.startswith("Wolf #7") and result.data["stats"]["health"] == 0.8 and result.data["id"] == 7, str(result))
check("dev inspect of an unknown id is ok False", ask(server, "inspect", id=99) == dev.DevResult(False, "no entity #99"))
check("dev inspect needs an id on the wire", ask(server, "inspect").ok is False)
server.sim.systems.activity.frozen.add(7)
result = ask(server, "wake", id=7)
check("dev wake says it woke it", result.ok and result.text == "woke Wolf #7" and result.data == {"id": 7, "was_frozen": True}, str(result))
result = ask(server, "wake", id=7)
check("dev wake of one that is awake says so", result.ok and result.text == "Wolf #7 was not frozen" and result.data["was_frozen"] is False, str(result))
check("dev wake of an unknown id is ok False", ask(server, "wake", id=99) == dev.DevResult(False, "no entity #99"))

normal = server_for(False)
normal.sim.systems.activity.frozen.add(7)
check("a normal server refuses wake and inspect and changes nothing", ask(normal, "wake", id=7).text == "not available" and ask(normal, "inspect", id=7).text == "not available" and 7 in normal.sim.systems.activity.frozen)

from src.simworld.server.server import Server
from src.simworld.shared.phase import PLAYING
from src.simworld.sim.dev.sandbox_mode import populate_sandbox, prepare_sandbox
from src.simworld.sim.dev.start_units import give_test_units
from src.simworld.sim.simulation import Simulation

real_sim = Simulation()
real_sim.start_new_game(prepare_sandbox(real_sim, None))
populate_sandbox(real_sim)
give_test_units(real_sim, 1)
real = Server(real_sim, stats_interval=0, start_phase=PLAYING)
activity = real_sim.systems.activity
units = [real_sim.entity_manager.get(pixel_id) for pixel_id in real_sim.owned_ids(1)]
check("the sandbox gave player 1 test units", bool(units))

if units:
    result = dev.run_dev(real, None, "inspect", {"id": units[0].id})
    check("inspecting a real unit shows its stats", result.ok and "health" in result.data["stats"] and "energy" in result.data["stats"] and result.data["owner"] == 1 and result.text.startswith(units[0].name), f"{result}")
    print(result.text)

frozen = [entity for entity in real_sim.entity_manager.all() if entity.id in activity.frozen]
check("the sandbox has frozen gallery entities", bool(frozen))
deciders = [entity for entity in frozen if entity.traits]
check("one of them has traits, so it can decide", bool(deciders), "no frozen gallery entity has any traits")

if deciders:
    target = max(deciders, key=lambda entity: len(entity.traits))
    inspected = dev.run_dev(real, None, "inspect", {"id": target.id})
    check("a frozen entity can be inspected and says it is frozen", inspected.ok and inspected.data["frozen"] is True and "frozen" in inspected.text.splitlines()[0], str(inspected))

    systems = real_sim.systems
    thinkers = set()
    original_think = systems.think

    def spy(entity):
        thinkers.add(entity.id)
        return original_think(entity)

    systems.think = spy

    for _ in range(40):
        real.advance()

    check("other entities do think, so the spy works", bool(thinkers), "the spy saw no entity think in 40 ticks")
    check("while frozen it does not decide", target.id not in thinkers and target.task is None, f"{target.task} {sorted(thinkers)}")
    woke = dev.run_dev(real, None, "wake", {"id": target.id})
    check("a real wake works", woke.ok and woke.text.startswith("woke") and target.id not in activity.frozen, str(woke))

    for _ in range(80):
        real.advance()

    check("a woken entity starts deciding", target.id in thinkers, f"traits {sorted(target.traits)}, thinkers {sorted(thinkers)}")
    check("and is no longer frozen when inspected", dev.run_dev(real, None, "inspect", {"id": target.id}).data["frozen"] is False)

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")