import json
import math
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.simworld.server import dev_commands as dev
from src.simworld.server.dev_time import init_time
from src.simworld.sim.dev import tools

failures = []
UNITS = 32


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class FakeManager:
    def __init__(self):
        self.things = {}
        self.killed = []

    def get(self, pixel_id):
        return self.things.get(pixel_id)

    def kill(self, pixel_id):
        self.killed.append(pixel_id)
        self.things[pixel_id].alive = False


class FakeSim:
    sandbox = True

    def __init__(self, width=100, height=80):
        self.world = SimpleNamespace(width=width, height=height)
        self.entity_manager = FakeManager()
        self.systems = SimpleNamespace(context="CTX", counters=None)
        self.tick = 0
        self.spawned = []
        self.next_id = 100

    def spawn_pixel(self, blueprint, owner, x, y):
        self.next_id += 1
        pixel = SimpleNamespace(id=self.next_id, name=blueprint.get("name", ""), sprite_id=blueprint.get("sprite_id", ""), owner=owner, x=x, y=y, alive=True)
        self.entity_manager.things[pixel.id] = pixel
        self.spawned.append((blueprint, owner, x, y))
        return pixel


root = Path(tempfile.mkdtemp())
entities, resources = root / "entities", root / "resources"
entities.mkdir()
resources.mkdir()
(entities / "wolf.json").write_text(json.dumps({"name": "Wolf", "owner": 9, "health": 40}))
(entities / "tree.json").write_text(json.dumps({"gallery": False}))
(entities / "broken.json").write_text("{nope")
(entities / "_hidden.json").write_text("{}")
(resources / "wood.json").write_text(json.dumps({"id": "wood", "item": {}, "structure": {}}))
(resources / "ore_file.json").write_text(json.dumps({"id": "ore", "item": {}}))
(resources / "gas.json").write_text(json.dumps({"structure": {}}))
(resources / "bad.json").write_text("[1]")
KW = {"tile_units": UNITS, "entity_dir": entities, "resource_dir": resources}


def spawn(sim, target, x=10.0, y=12.0, owner=3, **extra):
    return tools.spawn_thing(sim, target, x, y, owner, **{**KW, **extra})


def problem(call):
    try:
        call()
    except tools.DevError as error:
        return str(error)
    except Exception as error:
        return f"WRONG {type(error).__name__}: {error}"

    return None


sim = FakeSim()
made = spawn(sim, "wolf", 40.7, 22.2)
blueprint, owner, x, y = sim.spawned[0]
check("a blueprint spawns at the tile centre, for the sender", (made.tile_x, made.tile_y) == (40, 22) and (x, y) == (40.5 * UNITS, 22.5 * UNITS) and owner == 3, str(sim.spawned))
check("the blueprint's own owner is ignored, the sender owns it", blueprint.get("owner") is None and sim.entity_manager.things[made.id].owner == 3)
check("the blueprint gets a name and sprite", blueprint["name"] == "Wolf" and blueprint["sprite_id"] == "wolf" and blueprint["health"] == 40)
check("a hidden-from-gallery blueprint can still be spawned", spawn(sim, "tree").label == "tree")
check("an unknown blueprint names itself", problem(lambda: spawn(sim, "dragon")) == "unknown blueprint 'dragon'")
check("hidden files are not blueprints", problem(lambda: spawn(sim, "_hidden")) == "unknown blueprint '_hidden'")
check("a broken file says why it cannot be used", (problem(lambda: spawn(sim, "broken")) or "").startswith("blueprint 'broken': cannot read it"), str(problem(lambda: spawn(sim, "broken"))))
check("nothing was created by the failures", len(sim.spawned) == 2)

for point in ((-0.5, 5), (5, -0.01), (100, 5), (5, 80), (1000, 1000)):
    wanted = f"{math.floor(point[0])},{math.floor(point[1])} is outside the world (100x80 tiles)"
    check(f"{point} is outside the world", problem(lambda: spawn(sim, "wolf", *point)) == wanted, str(problem(lambda: spawn(sim, "wolf", *point))))

edge = spawn(sim, "wolf", 99.99, 79.99)
check("the last tile is inside", (edge.tile_x, edge.tile_y) == (99, 79))
first = spawn(sim, "wolf", 0.0, 0.0)
check("the first tile is inside, and 0.0 floors to 0", (first.tile_x, first.tile_y) == (0, 0))

for bad in (float("nan"), float("inf"), "3", None, True):
    check(f"a point of {bad!r} is refused", problem(lambda: spawn(sim, "wolf", bad, 1.0)) == "the point must be two numbers")

for target, wanted in (("foo:bar", "unknown kind 'foo'"), ("item:", "needs a resource name"), (":wood", "unknown kind ''")):
    check(f"{target!r} is refused", wanted in (problem(lambda: spawn(sim, target)) or ""), str(problem(lambda: spawn(sim, target))))

calls = []


def make_item(ctx, resource, amount, x, y):
    calls.append(("item", ctx, resource, amount, x, y))
    return SimpleNamespace(id=500, name="", sprite_id="wood", alive=True)


def build_structure(ctx, resource, x, y, owner):
    calls.append(("structure", ctx, resource, x, y, owner))
    return SimpleNamespace(id=501, name="", sprite_id="wall", alive=True)


creators = {tools.ITEM: make_item, tools.STRUCTURE: build_structure}
made = spawn(sim, "item:wood", 5.5, 6.5, creators=creators)
check("item:<resource> calls make_item with the context, amount 1 and the tile centre", calls[-1] == ("item", "CTX", "wood", 1, 5.5 * UNITS, 6.5 * UNITS) and made.id == 500 and made.label == "item:wood", str(calls))
made = spawn(sim, "structure:wood", 5.5, 6.5, owner=4, creators=creators)
check("structure:<resource> calls build_structure with the sender as owner", calls[-1] == ("structure", "CTX", "wood", 5.5 * UNITS, 6.5 * UNITS, 4) and made.id == 501, str(calls))
check("a resource is found by its id, not its file name", spawn(sim, "item:ore", creators=creators).id == 500)
check("an unknown resource names itself", problem(lambda: spawn(sim, "item:iron", creators=creators)) == "unknown resource 'iron'")
check("a resource with no item form says so", problem(lambda: spawn(sim, "item:gas", creators=creators)) == "resource 'gas' has no item form")
check("a resource with no structure form says so", problem(lambda: spawn(sim, "structure:ore", creators=creators)) == "resource 'ore' has no structure form")
check("item: is not available yet when there is no make_item", problem(lambda: spawn(sim, "item:wood", creators={})) == "item: spawning is not available yet")
check("structure: is not available yet when there is no build_structure", problem(lambda: spawn(sim, "structure:wood", creators={})) == "structure: spawning is not available yet")
before = len(calls)
check("an item outside the world is refused before anything is made", "outside the world" in (problem(lambda: spawn(sim, "item:wood", -3, 1, creators=creators)) or "") and len(calls) == before)
check("a creator that returns text gives that text", problem(lambda: spawn(sim, "item:wood", creators={tools.ITEM: lambda *a: "the stack is full"})) == "item:wood: the stack is full")
check("a creator that returns nothing is explained", problem(lambda: spawn(sim, "item:wood", creators={tools.ITEM: lambda *a: None})) == "item:wood: nothing was created")


def explode(*args):
    raise RuntimeError("kaboom")


check("a creator that raises becomes a readable error", problem(lambda: spawn(sim, "structure:wood", creators={tools.STRUCTURE: explode})) == "structure:wood: RuntimeError: kaboom")

broken = FakeSim()
broken.spawn_pixel = lambda *args: (_ for _ in ()).throw(ValueError("bad definition"))
check("a blueprint that fails to build becomes a readable error", problem(lambda: spawn(broken, "wolf")) == "wolf: ValueError: bad definition")

gone = tools.delete_pixel(sim, first.id)
check("delete uses the manager's kill", gone.id == first.id and sim.entity_manager.killed == [first.id] and sim.entity_manager.things[first.id].alive is False, str(gone))
check("delete says what it removed", gone.label == "Wolf")
check("deleting it again, or an unknown id, says there is no such entity", problem(lambda: tools.delete_pixel(sim, first.id)) == f"no entity #{first.id}" and problem(lambda: tools.delete_pixel(sim, 99999)) == "no entity #99999")


def server_for(flag=True, sim=None):
    server = SimpleNamespace(sim=sim or FakeSim())
    server.sim.sandbox = flag
    init_time(server)
    return server


def ask(server, what, **args):
    return dev.run_dev(server, SimpleNamespace(player_id=3), what, args)


original_tools = (tools.ENTITY_DIR, tools.RESOURCE_DIR, tools.find_function)
tools.ENTITY_DIR, tools.RESOURCE_DIR = entities, resources

try:
    server = server_for()
    result = ask(server, "spawn", blueprint="wolf", x=40.7, y=22.2)
    wolf_id = server.sim.next_id
    check("dev spawn says what it made", result.ok and result.text == f"spawned wolf #{wolf_id} at 40,22" and result.data == {"id": wolf_id, "x": 40, "y": 22}, str(result))
    check("dev spawn made it for the sender", server.sim.spawned[0][1] == 3)
    result = ask(server, "spawn", blueprint="dragon", x=1.0, y=1.0)
    check("dev spawn of an unknown blueprint is ok False with the name", result.ok is False and "dragon" in result.text, str(result))
    result = ask(server, "spawn", blueprint="wolf", x=500.0, y=1.0)
    check("dev spawn outside the world is ok False", result.ok is False and "outside the world" in result.text, str(result))
    tools.find_function = lambda kind: None
    result = ask(server, "spawn", blueprint="item:wood", x=1.0, y=1.0)
    check("dev spawn item: says not available yet while make_item does not exist", result == dev.DevResult(False, "item: spawning is not available yet"), str(result))
    tools.find_function = lambda kind: make_item if kind == tools.ITEM else build_structure
    result = ask(server, "spawn", blueprint="item:wood", x=1.2, y=1.7)
    check("dev spawn item:wood works once make_item exists", result.ok and result.text == "spawned item:wood #500 at 1,1", str(result))
    result = ask(server, "spawn", blueprint="structure:wood", x=2.0, y=3.0)
    check("dev spawn structure:wood works once build_structure exists", result.ok and result.text == "spawned structure:wood #501 at 2,3", str(result))
    result = ask(server, "spawn", blueprint="wolf")
    check("dev spawn needs a point on the wire", result.ok is False and "missing argument" in result.text, str(result))
    result = ask(server, "delete", id=wolf_id)
    check("dev delete says what it removed", result.ok and result.text == f"deleted Wolf #{wolf_id}" and result.data == {"id": wolf_id}, str(result))
    check("dev delete of an unknown id is ok False", ask(server, "delete", id=77777).ok is False)
    check("dev delete needs an id on the wire", ask(server, "delete").ok is False)

    normal = server_for(False)
    results = [ask(normal, "spawn", blueprint="wolf", x=1.0, y=1.0), ask(normal, "delete", id=101)]
    check("a normal server refuses spawn and delete and creates nothing", all(r.text == "not available" for r in results) and normal.sim.spawned == [] and normal.sim.entity_manager.killed == [])
finally:
    tools.ENTITY_DIR, tools.RESOURCE_DIR, tools.find_function = original_tools

from src.simworld.server.server import Client, Server
from src.simworld.shared import protocol as proto
from src.simworld.shared.phase import PLAYING
from src.simworld.sim.core.sim_context import TILE_UNITS
from src.simworld.sim.dev.catalog import ENTITY_DIR, entity_entries
from src.simworld.sim.dev.sandbox_mode import populate_sandbox, prepare_sandbox
from src.simworld.sim.simulation import Simulation

names = [name for _, name, _ in entity_entries(ENTITY_DIR, [])]
check("the content folder has at least one entity blueprint to spawn", bool(names), str(ENTITY_DIR))

sim = Simulation()
sim.start_new_game(prepare_sandbox(sim, None))
populate_sandbox(sim)
real = Server(sim, stats_interval=0, start_phase=PLAYING)


def add_player(player_id):
    client = Client(websocket=None, player_id=player_id, name=f"p{player_id}")
    client.view = (18 * TILE_UNITS, 0.0, 42 * TILE_UNITS, 15 * TILE_UNITS)
    real.players[player_id] = client
    real.sessions[player_id] = "token"
    return client


def tick():
    real.advance()
    real.grid.sync(real.sim.entity_manager.all())
    real.replicate()


def drain(client):
    items = [client.outbox.get_nowait() for _ in range(client.outbox.qsize())]
    return [proto.decode(item, proto.SERVER_TYPES) for item in items if isinstance(item, bytes)]


def ids(messages, key):
    found = set()

    for message in messages:
        if message["type"] == proto.TICK_UPDATE:
            for entry in message.get(key, []):
                found.add(entry["id"] if isinstance(entry, dict) else entry)

    return found


sender, watcher = add_player(1), add_player(2)
tick()
drain(sender)
drain(watcher)

if names:
    result = dev.run_dev(real, sender, "spawn", {"blueprint": names[0], "x": 30.5, "y": 3.5})
    check("a real spawn of a catalog blueprint works", result.ok and result.text.startswith(f"spawned {names[0]} #") and result.text.endswith("at 30,3"), str(result))
    spawned = result.data["id"] if result.data else None
    entity = real.sim.entity_manager.get(spawned)
    check("it is owned by the sender and stands on the tile centre", entity is not None and entity.owner == 1 and (entity.position.x, entity.position.y) == (30.5 * TILE_UNITS, 3.5 * TILE_UNITS), str(entity))
    check("it is in the sender's owned list", spawned in real.sim.owned_ids(1))
    tick()
    check("the spawned entity appears for the sender", spawned in ids(drain(sender), "enter"))
    check("and for another client looking at that spot", spawned in ids(drain(watcher), "enter"))

    result = dev.run_dev(real, watcher, "delete", {"id": spawned})
    check("a real delete works (any client may delete)", result.ok and result.text.startswith("deleted"), str(result))
    tick()
    check("the deleted entity leaves the sender's view", spawned in ids(drain(sender), "leave"))
    check("and the other client's", spawned in ids(drain(watcher), "leave"))
    check("it is gone from the simulation after the tick", real.sim.entity_manager.get(spawned) is None and spawned not in [e.id for e in real.sim.entity_manager.all()])
    check("deleting it again says there is no such entity", dev.run_dev(real, sender, "delete", {"id": spawned}).text == f"no entity #{spawned}")

    frozen = next((entity for entity in real.sim.entity_manager.all() if entity.owner is None), None)
    check("the sandbox has a gallery entity to delete", frozen is not None)

    if frozen is not None:
        result = dev.run_dev(real, sender, "delete", {"id": frozen.id})
        tick()
        check("a gallery (frozen) entity can be deleted too", result.ok and real.sim.entity_manager.get(frozen.id) is None, str(result))

result = dev.run_dev(real, sender, "spawn", {"blueprint": "no_such_blueprint_x", "x": 30.5, "y": 3.5})
check("a real unknown blueprint is ok False and names it", result.ok is False and "no_such_blueprint_x" in result.text, str(result))
result = dev.run_dev(real, sender, "spawn", {"blueprint": names[0] if names else "x", "x": -1.0, "y": 3.5})
check("a real spawn outside the world is ok False", result.ok is False and "outside the world" in result.text, str(result))

real.sim.sandbox = False
before = len(real.sim.entity_manager.all())
result = dev.run_dev(real, sender, "spawn", {"blueprint": names[0] if names else "x", "x": 30.5, "y": 3.5})
check("on a normal server a spawn is refused and creates nothing", result.text == "not available" and len(real.sim.entity_manager.all()) == before)

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")