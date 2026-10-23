import itertools
import sys
from types import SimpleNamespace

from src.simworld.server import dev_commands as dev
from src.simworld.server.dev_time import init_time
from src.simworld.shared.dev_commands import NAME_PATTERN
from src.simworld.sim.dev import tools
from src.simworld.world.sandbox import REGION_SIZE

failures = []
SIZE = REGION_SIZE
ORIGIN = (5, 7)
FEATURES = ["lake", "dunes", "forest"]
MAPS = ["wet", "height"]


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Tile:
    def __init__(self, name):
        self.name = name


TILES = {name: Tile(name) for name in ("grass", "sand", "water", "moss")}


class FakeWorld:
    def __init__(self):
        self.width, self.height = 70, 70
        self.tiles = [[TILES["grass"]] * self.width for _ in range(self.height)]
        self.changes = {}
        self.writes = []
        self.announced = []

    def get_tile(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("outside")

        return self.tiles[y][x]

    def set_tile(self, x, y, tile):
        current = self.get_tile(x, y)
        self.writes.append((x, y))

        if current is tile:
            return False

        self.tiles[y][x] = tile

        if current.name != tile.name:
            self.changes[(x, y)] = tile.name
            self.announced.append((x, y))

        return True


generated = []


def fake_generate(settings, gen):
    generated.append((gen["seed"], frozenset(gen["disabled_features"]), frozenset(gen["disabled_maps"])))
    rows = []

    for y in range(SIZE):
        row = []

        for x in range(SIZE):
            tile = TILES["grass"]

            if "dunes" not in gen["disabled_features"] and (x + y + gen["seed"]) % 4 == 0:
                tile = TILES["sand"]

            if "lake" not in gen["disabled_features"] and x % 7 == 0 and y % 3 == 0:
                tile = TILES["water"]

            if "wet" not in gen["disabled_maps"] and (x * y + gen["seed"]) % 11 == 0:
                tile = TILES["moss"]

            row.append(tile)

        rows.append(row)

    return SimpleNamespace(tiles=rows)


original_regen = tools.regen_section
tools.regen_section = lambda sim, generate=None, origin=None: original_regen(sim, fake_generate, ORIGIN)


def make_sim(sandbox=True, seed=0):
    world = FakeWorld()
    return SimpleNamespace(
        sandbox=sandbox,
        sandbox_gen={"seed": seed, "disabled_features": set(), "disabled_maps": set()},
        generator=SimpleNamespace(features=SimpleNamespace(names=lambda: list(FEATURES)), maps=SimpleNamespace(map_type_names=lambda: list(MAPS))),
        generation_settings=object(),
        world=world,
        tick=0,
        systems=SimpleNamespace(counters=None),
    )


def section(world):
    return [[world.tiles[ORIGIN[1] + y][ORIGIN[0] + x].name for x in range(SIZE)] for y in range(SIZE)]


def outside(world):
    inside = {(ORIGIN[0] + x, ORIGIN[1] + y) for y in range(SIZE) for x in range(SIZE)}
    return [(x, y) for y in range(world.height) for x in range(world.width) if (x, y) not in inside and world.tiles[y][x] is not TILES["grass"]]


def differing(first, second):
    return {(x, y) for y in range(SIZE) for x in range(SIZE) if first[y][x] != second[y][x]}


def problem(call):
    try:
        call()
    except tools.DevError as error:
        return str(error)
    except Exception as error:
        return f"WRONG {type(error).__name__}: {error}"

    return None


sim = make_sim()
world = sim.world
listed = tools.gen_listing(sim)
check("list shows the size and seed, every feature and every map on", listed.text == "section 50x50, seed 0\nfeatures: dunes on, forest on, lake on\nmaps: height on, wet on", listed.text)
check("list data has the seed and the on/off state of each name", listed.data == {"seed": 0, "features": {"forest": True, "dunes": True, "lake": True}, "maps": {"height": True, "wet": True}} and list(listed.data["features"]) == sorted(FEATURES), str(listed.data))
check("listing writes nothing and generates nothing", world.writes == [] and generated == [])

first = tools.regen_section(sim)
base = section(world)
check("a first regenerate fills the section and counts the tiles that differ from grass", first.changed == sum(tile != "grass" for row in base for tile in row) and first.total == SIZE * SIZE and first.changed > 0, str(first))
check("only the section was written, at its origin", outside(world) == [] and base[0][0] == "moss" and len(world.writes) == first.changed)
world.writes.clear()
again = tools.regen_section(sim)
check("regenerating with nothing changed writes nothing at all", again.changed == 0 and world.writes == [], str(again))

before = section(world)
world.writes.clear()
world.announced.clear()
off = tools.set_switch(sim, "feature", "lake", False)
after = section(world)
moved = differing(before, after)
check("turning a feature off removes its tiles", all(before[y][x] == "water" for x, y in moved) and "water" not in {tile for row in after for tile in row} and len(moved) > 0, str(sorted(moved)[:5]))
check("it says how many tiles changed", off.text == f"feature lake off: {len(moved)} of {SIZE * SIZE} tiles changed" and off.data["changed"] == len(moved) and off.data["features"]["lake"] is False and off.data["on"] is False, off.text)
check("only the tiles that differ were written, each once, through set_tile", sorted(world.writes) == sorted((ORIGIN[0] + x, ORIGIN[1] + y) for x, y in moved) and len(set(world.writes)) == len(world.writes))
check("the changes were announced for exactly those tiles", set(world.announced) == {(ORIGIN[0] + x, ORIGIN[1] + y) for x, y in moved})
check("and the latest recorded name of each is its new tile", all(world.changes[(ORIGIN[0] + x, ORIGIN[1] + y)] == after[y][x] for x, y in moved))
check("nothing outside the section changed", outside(world) == [])
check("the generator was asked with that feature disabled", generated[-1] == (0, frozenset({"lake"}), frozenset()), str(generated[-1]))

world.writes.clear()
world.announced.clear()
on = tools.set_switch(sim, "feature", "lake", True)
check("turning it on brings the tiles back exactly", section(world) == before and on.data["changed"] == len(moved), on.text)
check("and writes only those tiles", sorted(world.writes) == sorted((ORIGIN[0] + x, ORIGIN[1] + y) for x, y in moved))

count = len(generated)
world.writes.clear()
same = tools.set_switch(sim, "feature", "lake", True)
check("turning on what is already on says so and regenerates nothing", same.text == "feature lake is already on" and same.data["changed"] == 0 and len(generated) == count and world.writes == [], same.text)
tools.set_switch(sim, "feature", "forest", False)
check("a feature that makes no tiles in the section changes nothing but is still off", sim.sandbox_gen["disabled_features"] == {"forest"} and section(world) == before and tools.gen_listing(sim).data["features"]["forest"] is False)
check("the list shows it off", "forest off" in tools.gen_listing(sim).text)
tools.set_switch(sim, "feature", "forest", True)

check("feature names are matched ignoring case and stored as the generator names them", tools.set_switch(sim, "feature", "LAKE", False).text.startswith("feature lake off") and sim.sandbox_gen["disabled_features"] == {"lake"})
tools.set_switch(sim, "feature", "lake", True)
check("an unknown feature is named and nothing is written", problem(lambda: tools.set_switch(sim, "feature", "volcano", False)) == "unknown feature 'volcano': /gen list shows them" and sim.sandbox_gen["disabled_features"] == set())
check("a map name is not a feature name and the other way round", problem(lambda: tools.set_switch(sim, "feature", "wet", False)) == "unknown feature 'wet': /gen list shows them" and problem(lambda: tools.set_switch(sim, "map", "lake", False)) == "unknown map 'lake': /gen list shows them")

world.writes.clear()
wet = tools.set_switch(sim, "map", "wet", False)
check("turning a map off regenerates with it disabled", generated[-1] == (0, frozenset(), frozenset({"wet"})) and "moss" not in {tile for row in section(world) for tile in row} and wet.data["maps"]["wet"] is False, wet.text)
tools.set_switch(sim, "map", "WET", True)
check("turning it on again restores the section", section(world) == before and sim.sandbox_gen["disabled_maps"] == set())
check("map names are matched ignoring case", tools.set_switch(sim, "map", "Height", False).data["maps"]["height"] is False)
tools.set_switch(sim, "map", "height", True)

world.writes.clear()
seeded = tools.set_seed(sim, 7)
seven = section(world)
check("a new seed regenerates the section with it", generated[-1] == (7, frozenset(), frozenset()) and seeded.data["seed"] == 7 and seeded.data["changed"] == len(differing(before, seven)) and sim.sandbox_gen["seed"] == 7, seeded.text)
check("only the tiles that differ were written", sorted(world.writes) == sorted((ORIGIN[0] + x, ORIGIN[1] + y) for x, y in differing(before, seven)))
check("the seed text says what happened", seeded.text == f"section seed 7: {len(differing(before, seven))} of {SIZE * SIZE} tiles changed", seeded.text)
count = len(generated)
check("the same seed again does nothing", tools.set_seed(sim, 7).text == "the section seed is already 7" and len(generated) == count)
tools.set_seed(sim, 0)
check("going back to the first seed restores the first section", section(world) == before)
check("the list shows the seed", tools.gen_listing(sim).text.splitlines()[0] == "section 50x50, seed 0")

for bad in (-1, 2**32, 1.5, "7", None, True, [1]):
    check(f"a seed of {bad!r} is refused and nothing changes", problem(lambda: tools.set_seed(sim, bad)) == f"the seed must be a whole number from 0 to {2 ** 32 - 1}" and sim.sandbox_gen["seed"] == 0 and section(world) == before)

check("the biggest seed is allowed", tools.set_seed(sim, 2**32 - 1).data["seed"] == 2**32 - 1)
tools.set_seed(sim, 0)


def determined(order, seed):
    other = make_sim(seed=0)

    for step in order:
        step(other)

    return section(other.world)


steps = [lambda s: tools.set_switch(s, "feature", "lake", False), lambda s: tools.set_switch(s, "map", "wet", False), lambda s: tools.set_seed(s, 9), lambda s: tools.set_switch(s, "feature", "dunes", False)]
runs = [determined(steps, 0), determined(steps, 0)]
check("the same toggles and seed give the same tiles in two runs", runs[0] == runs[1])
check("in any order", all(determined(order, 0) == runs[0] for order in itertools.permutations(steps)))
check("and the same as generating that state in one go", runs[0] == [[fake_generate(None, {"seed": 9, "disabled_features": {"lake", "dunes"}, "disabled_maps": {"wet"}}).tiles[y][x].name for x in range(SIZE)] for y in range(SIZE)])

broken = make_sim()


def explode(settings, gen):
    raise RuntimeError("generator failed")


tools.regen_section = lambda sim, generate=None, origin=None: original_regen(sim, explode, ORIGIN)
failed_switch = problem(lambda: tools.set_switch(broken, "feature", "lake", False))
check("a generator that fails leaves the switch as it was", failed_switch == "WRONG RuntimeError: generator failed" and broken.sandbox_gen["disabled_features"] == set())
failed_seed = problem(lambda: tools.set_seed(broken, 5))
check("and the seed as it was", failed_seed == "WRONG RuntimeError: generator failed" and broken.sandbox_gen["seed"] == 0 and broken.world.writes == [])
tools.regen_section = lambda sim, generate=None, origin=None: original_regen(sim, fake_generate, ORIGIN)

for label, damaged in (("no sandbox_gen", None), ("not a map", 5), ("missing keys", {"seed": 0}), ("seed text", {"seed": "0", "disabled_features": set(), "disabled_maps": set()}), ("seed bool", {"seed": True, "disabled_features": set(), "disabled_maps": set()}), ("lists not sets", {"seed": 0, "disabled_features": [], "disabled_maps": set()})):
    odd = make_sim()
    odd.sandbox_gen = damaged
    check(f"{label}: every gen function says there is no section to change", all(problem(call) == tools.NO_SECTION for call in (lambda: tools.gen_listing(odd), lambda: tools.set_switch(odd, "feature", "lake", False), lambda: tools.set_seed(odd, 1), lambda: tools.regen_section(odd))), str(problem(lambda: tools.gen_listing(odd))))

nameless = make_sim()
nameless.generator = SimpleNamespace()
check("a sim without a generator says there is no section to change", problem(lambda: tools.gen_listing(nameless)) == tools.NO_SECTION)

points = tools.section_points(32)
left, top = ORIGIN
real_left, real_top = tools.region_origin()
check("the section points are in world units and cover the section in steps of 8 tiles", len(points) == 49 and points[0] == ((real_left + 0.5) * 32, (real_top + 0.5) * 32) and points[-1] == ((real_left + 48.5) * 32, (real_top + 48.5) * 32), str(points[:2]))
check("every tile of the section is within 4 tiles of a point", all(any(abs((real_left + x + 0.5) * 32 - px) <= 4 * 32 and abs((real_top + y + 0.5) * 32 - py) <= 4 * 32 for px, py in points) for x in range(SIZE) for y in range(SIZE)))


def server_for(flag=True):
    server = SimpleNamespace(sim=make_sim(flag))
    server.sim.systems = SimpleNamespace(counters=SimpleNamespace(values={}, add=lambda name, amount=1: None))
    init_time(server)
    return server


def ask(server, **args):
    return dev.run_dev(server, SimpleNamespace(player_id=3), "gen", args)


server = server_for()
result = ask(server, action="list")
check("dev gen list is ok with the text and the data", result.ok and result.text.startswith("section 50x50, seed 0") and result.data["seed"] == 0, str(result))
result = ask(server, action="feature", name="lake", value="off")
check("dev gen feature off says what it did and returns the new state", result.ok and result.text.startswith("feature lake off: ") and result.data["features"]["lake"] is False and result.data["changed"] > 0, str(result))
check("the world really changed through the handler", "water" not in {tile for row in section(server.sim.world) for tile in row})
result = ask(server, action="map", name="wet", value="off")
check("dev gen map off works", result.ok and result.data["maps"]["wet"] is False, str(result))
result = ask(server, action="seed", value=3)
check("dev gen seed works", result.ok and result.data["seed"] == 3 and result.data["features"]["lake"] is False and result.data["maps"]["wet"] is False, str(result))
check("dev gen on again works", ask(server, action="feature", name="lake", value="on").ok and ask(server, action="map", name="wet", value="on").ok and ask(server, action="seed", value=0).ok)
check("everything on and seed 0 is the first section again", section(server.sim.world) == base)
result = ask(server, action="feature", name="volcano", value="off")
check("dev gen with an unknown feature is ok False naming it", result == dev.DevResult(False, "unknown feature 'volcano': /gen list shows them"), str(result))
result = ask(server, action="seed", value=-5)
check("dev gen with a bad seed is refused before it gets to the world", result.ok is False and "from 0 to" in result.text and server.sim.sandbox_gen["seed"] == 0, str(result))
check("dev gen with bad arguments is refused", all(ask(server, **args).ok is False for args in ({}, {"action": "regen"}, {"action": "feature"}, {"action": "feature", "name": "lake"}, {"action": "feature", "name": "lake", "value": "maybe"}, {"action": "list", "name": "x"}, {"action": "seed", "value": "7"}, {"action": "seed", "value": True})))
check("none of the refused ones changed the section", section(server.sim.world) == base and server.sim.sandbox_gen == {"seed": 0, "disabled_features": set(), "disabled_maps": set()})

server.sim.sandbox_gen = None
result = ask(server, action="list")
check("a sandbox without a section says so instead of failing", result == dev.DevResult(False, tools.NO_SECTION), str(result))

normal = server_for(False)
count = len(generated)
changes = dict(normal.sim.world.changes)
refused = [ask(normal, action="list"), ask(normal, action="feature", name="lake", value="off"), ask(normal, action="map", name="wet", value="off"), ask(normal, action="seed", value=4)]
check("a normal server refuses every gen form", all(result == dev.DevResult(False, "not available") for result in refused), str(refused))
check("and the section, the state and the generator are untouched", normal.sim.world.writes == [] and normal.sim.world.changes == changes and normal.sim.sandbox_gen == {"seed": 0, "disabled_features": set(), "disabled_maps": set()} and len(generated) == count)

# ---- real tree

tools.regen_section = original_regen

from dataclasses import asdict, replace

from src.simworld.server.server import Client, Server
from src.simworld.shared import protocol as proto
from src.simworld.shared.phase import PLAYING
from src.simworld.sim.dev.sandbox_mode import populate_sandbox, prepare_sandbox
from src.simworld.sim.dev.start_units import give_test_units
from src.simworld.sim.simulation import Simulation
from src.simworld.world.generator import NEUTRAL_MAP_VALUE, GenerationSettings, WorldGenerator, generate_section
from src.simworld.world.sandbox import region_origin
from src.simworld.world.tile_types import TILE_TYPES


def real_server(seed=None):
    sim = Simulation()
    sim.start_new_game(prepare_sandbox(sim, seed))
    populate_sandbox(sim)

    for player in (1, 2):
        give_test_units(sim, player)

    return Server(sim, stats_interval=0, start_phase=PLAYING)


real = real_server()
real_sim = real.sim
world = real_sim.world
left, top = region_origin()
gen = real_sim.sandbox_gen
check("prepare_sandbox creates the runtime state: the seed and nothing disabled", gen == {"seed": real_sim.seed, "disabled_features": set(), "disabled_maps": set()}, str(gen))


def real_section():
    return [[world.get_tile(left + x, top + y) for x in range(SIZE)] for y in range(SIZE)]


def names_of(tiles):
    return [[tile.name for tile in row] for row in tiles]


def state(features=(), maps=(), seed=None):
    return {"seed": gen["seed"] if seed is None else seed, "disabled_features": set(features), "disabled_maps": set(maps)}


def differing_tiles(first, second):
    return {(x, y) for y in range(SIZE) for x in range(SIZE) if first[y][x] is not second[y][x]}


settings = real_sim.generation_settings
world_seed = real_sim.seed
original = real_section()
default_world = generate_section(settings, state())
default_tiles = default_world.tiles
check("with nothing disabled the section is exactly what generation made at the start", not differing_tiles(default_tiles, original))
plain = WorldGenerator(replace(settings, mode="normal", width=SIZE, height=SIZE, seed=gen["seed"], debug=False)).generate()
check("and exactly what a generator with no overrides makes", not differing_tiles(plain.tiles, original))
empty = WorldGenerator(replace(settings, mode="normal", width=SIZE, height=SIZE, seed=gen["seed"], debug=False), set(), set()).generate()
check("empty override sets change nothing", not differing_tiles(empty.tiles, original))

listing = real_sim.generator.features.names(), real_sim.generator.maps.map_type_names()
cells = {}

for row in default_world.feature_grid:
    for name in row:
        if name is not None:
            cells[name] = cells.get(name, 0) + 1

check("some feature appears in the section", bool(cells), "no feature owns a single tile of the 50x50 section, the toggles cannot be shown")
feature = max(cells, key=lambda name: (cells[name], name))
absent = [name for name in listing[0] if name not in cells]
print(f"     using feature '{feature}' ({cells[feature]} tiles of the section); features in the section: {sorted(cells)}; not in it: {absent}")

announced = []
original_listener = world.on_tile_change
world.on_tile_change = lambda x, y: (announced.append((x, y)), original_listener(x, y))
writes = []
original_set_tile = world.set_tile
world.set_tile = lambda x, y, tile: (writes.append((x, y)), original_set_tile(x, y, tile))[1]


def add_player(player_id):
    client = Client(websocket=None, player_id=player_id, name=f"p{player_id}")
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


def deltas(messages):
    return {tuple(entry) for message in messages if message["type"] == proto.WORLD_DELTA for entry in message["tiles"]}


clients = {player: add_player(player) for player in (1, 2)}
tick()

for client in clients.values():
    drain(client)


def run(**args):
    return dev.run_dev(real, clients[1], "gen", args)


result = run(action="list")
check("/gen list on the real sandbox shows the seed and every feature and map on", result.ok and result.data["seed"] == gen["seed"] and sorted(result.data["features"]) == sorted(listing[0]) and sorted(result.data["maps"]) == sorted(listing[1]) and all(result.data["features"].values()) and all(result.data["maps"].values()), str(result))
untypeable = [name for name in listing[0] + listing[1] if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name)]
check("every feature and map name can be typed after /gen", not untypeable, f"these cannot be used with /gen: {untypeable}")

writes.clear()
announced.clear()
result = run(action="feature", name=feature, value="off")
off_world = generate_section(settings, state(features=[feature]))
off_tiles = off_world.tiles
check("turning a feature off works", result.ok and result.data["features"][feature] is False, str(result))
check("the section is now what generation makes without that feature", not differing_tiles(real_section(), off_tiles))
check("that feature owns no tile of the regenerated section", all(name != feature for row in off_world.feature_grid for name in row) and cells[feature] > 0)
moved = differing_tiles(original, real_section())
check("some tiles changed", len(moved) > 0 and result.data["changed"] == len(moved), f"{len(moved)} differ, the command says {result.data['changed']}")
check("only the tiles that differ were written through set_tile, each once", sorted(writes) == sorted((left + x, top + y) for x, y in moved), f"{len(writes)} writes for {len(moved)} differing tiles")
by_name = {(x, y) for x, y in moved if original[y][x].name != real_section()[y][x].name}
check("the ones whose name changed were recorded and announced", {(left + x, top + y) for x, y in by_name} == set(world.changes) and {(left + x, top + y) for x, y in by_name} <= set(announced) <= {(left + x, top + y) for x, y in moved}, f"{len(by_name)} {len(world.changes)} {len(announced)}")
check("nothing outside the section was written or recorded", all(left <= x < left + SIZE and top <= y < top + SIZE for x, y in writes + list(world.changes)))

unique = {tile.name for row in original for tile in row if tile.name not in {other.name for other_row in off_tiles for other in other_row}}
check("the tiles that only that feature made are gone", all(tile.name not in unique for row in real_section() for tile in row), str(unique))
print(f"     tile names that only '{feature}' made in this section: {sorted(unique) or 'none (its tiles are shared with other features)'}")

tick()

for player, client in clients.items():
    seen = {(x, y) for x, y, name in deltas(drain(client))}
    wanted = set(world.changes)
    check(f"player {player}: the tiles that changed arrive as ordinary deltas", bool(wanted) and wanted <= seen, f"{len(wanted - seen)} of {len(wanted)} changed tiles never reached the client: did you apply the server.py edit (send_terrain sends the sandbox section to every client)?")

writes.clear()
announced.clear()
changes_after_off = dict(world.changes)
result = run(action="feature", name=feature, value="on")
check("turning it on brings the tiles back exactly", result.ok and not differing_tiles(real_section(), original) and result.data["changed"] == len(moved), str(result))
check("and writes only those tiles", sorted(writes) == sorted((left + x, top + y) for x, y in moved))
check("the latest recorded name of every changed tile is what the tile is now", all(world.get_tile(x, y).name == name for (x, y), name in world.changes.items()))

writes.clear()
result = run(action="feature", name=feature, value="on")
check("on when already on writes nothing", result.ok and "already on" in result.text and writes == [])
writes.clear()
check("regenerating again with nothing changed writes nothing", tools.regen_section(real_sim).changed == 0 and writes == [])
check("an unknown feature is refused", run(action="feature", name="no_such_feature", value="off").ok is False and not differing_tiles(real_section(), original))

moves = []

for name in listing[1]:
    candidate = generate_section(settings, state(maps=[name]))
    moves.append((len(differing_tiles(default_tiles, candidate.tiles)), name))

check("some map changes the section when it is disabled", any(count > 0 for count, _ in moves), f"{moves}: turning a map off changed no tile")
count, shaping = max(moves)
print(f"     map changes per disabled map: {sorted(moves, reverse=True)}; using '{shaping}'")
generator = WorldGenerator(replace(settings, mode="normal", width=SIZE, height=SIZE, seed=gen["seed"], debug=False), {shaping}, ())
generator.generate()
neutral = generator.maps.get(shaping)
check("a disabled map reads as its neutral value everywhere", all(neutral.get(x, y) == NEUTRAL_MAP_VALUE for y in range(SIZE) for x in range(SIZE)))
baseline = WorldGenerator(replace(settings, mode="normal", width=SIZE, height=SIZE, seed=gen["seed"], debug=False))
baseline.generate()
others = [name for name in listing[1] if name != shaping]
check("the other maps are exactly as before", all(generator.maps.get(name).get(x, y) == baseline.maps.get(name).get(x, y) for name in others for y in range(SIZE) for x in range(SIZE)), f"checked {others}")

writes.clear()
result = run(action="map", name=shaping, value="off")
check("turning a map off works and the section follows it", result.ok and result.data["maps"][shaping] is False and not differing_tiles(real_section(), generate_section(settings, state(maps=[shaping])).tiles), str(result))
check("only the differing tiles were written", sorted(writes) == sorted((left + x, top + y) for x, y in differing_tiles(original, real_section())))
result = run(action="map", name=shaping, value="on")
check("turning it on brings the section back exactly", result.ok and not differing_tiles(real_section(), original))

new_seed = gen["seed"] + 1
writes.clear()
result = run(action="seed", value=new_seed)
check("a new seed regenerates the section", result.ok and gen["seed"] == new_seed and not differing_tiles(real_section(), generate_section(settings, state(seed=new_seed)).tiles) and len(differing_tiles(original, real_section())) > 0, str(result))
check("only the differing tiles were written for the seed", sorted(writes) == sorted((left + x, top + y) for x, y in differing_tiles(original, real_section())))
check("the world's own seed is not touched", real_sim.seed == world_seed and settings.seed == world_seed and world_seed != new_seed)

run(action="feature", name=feature, value="off")
run(action="map", name=shaping, value="off")
tick()

for client in clients.values():
    drain(client)

final = names_of(real_section())
other_real = real_server()
other_real_sim = other_real.sim
other_dev = lambda **args: dev.run_dev(other_real, SimpleNamespace(player_id=1), "gen", args)
other_dev(action="map", name=shaping, value="off")
other_dev(action="seed", value=new_seed)
other_dev(action="feature", name=feature, value="off")
other_world = other_real_sim.world
check("the same toggles and seed give the same tiles in a second server, in a different order", [[other_world.get_tile(left + x, top + y).name for x in range(SIZE)] for y in range(SIZE)] == final)

for player in (1, 2):
    replacement = add_player(player)
    tick()
    seen = {(x, y, name) for x, y, name in deltas(drain(replacement))}
    wanted = {(x, y, name) for (x, y), name in world.changes.items()}
    check(f"player {player}: a client that reconnects gets every change replayed, section included", wanted <= seen, f"{len(wanted - seen)} of {len(wanted)} missing: did you apply the server.py edit (send_terrain)?")

fresh = WorldGenerator(GenerationSettings(**asdict(settings))).generate()
fresh.finish_generation(record=False)
check("the generation checksum a joining client compares is unchanged by all of this", fresh.generation_checksum == world.generation_checksum)
check("the section really differs from the generated one now", world.checksum() != world.generation_checksum)
tiles = {tile.name: tile for tile in TILE_TYPES.values()}

for (x, y), name in world.changes.items():
    fresh.set_tile(x, y, tiles[name])

check("replaying the recorded changes on a client's own generation gives the same world, checksum included", fresh.checksum() == world.checksum() and names_of(real_section()) == [[fresh.get_tile(left + x, top + y).name for x in range(SIZE)] for y in range(SIZE)])

normal_settings = GenerationSettings(width=40, height=40, seed=5)
first = WorldGenerator(normal_settings).generate()
first.finish_generation(record=False)
second = WorldGenerator(normal_settings, set(), set()).generate()
second.finish_generation(record=False)
third = WorldGenerator(normal_settings).generate()
third.finish_generation(record=False)
check("a normal world is the same with or without the overrides, and after all the toggles above", first.generation_checksum == second.generation_checksum == third.generation_checksum, f"{first.generation_checksum} {second.generation_checksum} {third.generation_checksum}")
check("a normal world never reads sandbox_gen", not hasattr(first, "sandbox_gen") and "sandbox_gen" not in asdict(normal_settings))

real_sim.sandbox = False
before_state = {"seed": gen["seed"], "disabled_features": set(gen["disabled_features"]), "disabled_maps": set(gen["disabled_maps"])}
writes.clear()
refused = [dev.run_dev(real, clients[1], "gen", args) for args in ({"action": "list"}, {"action": "feature", "name": feature, "value": "on"}, {"action": "map", "name": shaping, "value": "on"}, {"action": "seed", "value": 1})]
check("on a normal server every gen form is refused", all(result.text == "not available" and result.ok is False for result in refused), str(refused))
check("and nothing was regenerated or written", writes == [] and gen == before_state and names_of(real_section()) == final)

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")