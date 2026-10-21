import math
import sys
from types import SimpleNamespace

from src.simworld.server import dev_commands as dev
from src.simworld.server.dev_time import init_time
from src.simworld.shared import dev_commands as table
from src.simworld.sim.dev import tools

failures = []
UNITS = 32


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Tile:
    def __init__(self, name):
        self.name = name


class FakeWorld:
    def __init__(self, width=20, height=10):
        self.width, self.height = width, height
        self.grass = Tile("grass")
        self.tiles = [[self.grass] * width for _ in range(height)]
        self.changes = {}
        self.calls = []
        self.on_tile_change = lambda x, y: self.calls.append((x, y))

    def get_tile(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("outside")

        return self.tiles[y][x]

    def set_tile(self, x, y, tile):
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("outside")

        current = self.tiles[y][x]

        if current is tile:
            return False

        self.tiles[y][x] = tile

        if current.name != tile.name:
            self.changes[(x, y)] = tile.name
            self.on_tile_change(x, y)

        return True


def problem(call):
    try:
        call()
    except tools.DevError as error:
        return str(error)
    except Exception as error:
        return f"WRONG {type(error).__name__}: {error}"

    return None


stone, water = Tile("stone"), Tile("water")
TILES = {"grass": FakeWorld().grass, "stone": stone, "water": water}


def sim_with(world):
    return SimpleNamespace(sandbox=True, tick=0, world=world, systems=SimpleNamespace(counters=None), entity_manager=SimpleNamespace(get=lambda pixel_id: None))


world = FakeWorld()
TILES["grass"] = world.grass
sim = sim_with(world)
painted = tools.paint_tile(sim, "stone", 4.7, 2.2, TILES)
check("paint sets the floored tile through world.set_tile", world.tiles[2][4] is stone and (painted.tile_x, painted.tile_y) == (4, 2) and painted.changed and painted.before == "grass" and painted.name == "stone", str(painted))
check("only that tile changed, and the change was recorded and announced once", sum(tile is stone for row in world.tiles for tile in row) == 1 and world.changes == {(4, 2): "stone"} and world.calls == [(4, 2)], f"{world.changes} {world.calls}")
again = tools.paint_tile(sim, "stone", 4.0, 2.99, TILES)
check("painting the same tile again changes nothing and is not announced", again.changed is False and world.calls == [(4, 2)] and again.before == "stone")
check("painting over it replaces it", tools.paint_tile(sim, "water", 4.5, 2.5, TILES).before == "stone" and world.tiles[2][4] is water and world.changes == {(4, 2): "water"})
check("painting the original tile back is a change from the world's point of view", tools.paint_tile(sim, "grass", 4.5, 2.5, TILES).changed and world.changes == {(4, 2): "grass"})
check("the first and last tile can be painted", tools.paint_tile(sim, "stone", 0.0, 0.0, TILES).changed and tools.paint_tile(sim, "stone", 19.99, 9.99, TILES).changed and world.tiles[9][19] is stone)

before = [list(row) for row in world.tiles]
check("an unknown tile is refused with its name", problem(lambda: tools.paint_tile(sim, "lava", 1.0, 1.0, TILES)) == "unknown tile 'lava'")
check("tile names are case sensitive and not guessed", problem(lambda: tools.paint_tile(sim, "Stone", 1.0, 1.0, TILES)) == "unknown tile 'Stone'")
check("an unknown tile is refused before the point is looked at", problem(lambda: tools.paint_tile(sim, "lava", -5.0, 1.0, TILES)) == "unknown tile 'lava'")

for point in ((-0.5, 1), (1, -0.01), (20, 1), (1, 10), (1000, 1000)):
    wanted = f"{math.floor(point[0])},{math.floor(point[1])} is outside the world (20x10 tiles)"
    check(f"{point} is outside the world", problem(lambda: tools.paint_tile(sim, "stone", *point, TILES)) == wanted, str(problem(lambda: tools.paint_tile(sim, "stone", *point, TILES))))

for bad in (float("nan"), float("inf"), "3", None, True):
    check(f"a point of {bad!r} is refused", problem(lambda: tools.paint_tile(sim, "stone", bad, 1.0, TILES)) == "the point must be two numbers")

check("nothing changed by the refused ones", world.tiles == before)


def server_for(flag=True):
    world = FakeWorld()
    server = SimpleNamespace(sim=sim_with(world))
    server.sim.sandbox = flag
    init_time(server)
    return server


def ask(server, **args):
    return dev.run_dev(server, SimpleNamespace(player_id=3), "tile", args)


original = tools.tiles_by_name
tools.tiles_by_name = lambda: TILES

try:
    server = server_for()
    result = ask(server, name="stone", x=4.7, y=2.2)
    check("dev tile says what it painted and what was there", result.ok and result.text == "painted stone at 4,2 (was grass)" and result.data == {"x": 4, "y": 2, "tile": "stone", "changed": True}, str(result))
    result = ask(server, name="stone", x=4.0, y=2.0)
    check("dev tile on a tile that already is that says so", result.ok and result.text == "4,2 is already stone" and result.data["changed"] is False, str(result))
    result = ask(server, name="lava", x=1.0, y=1.0)
    check("dev tile with an unknown name is ok False naming it", result == dev.DevResult(False, "unknown tile 'lava'"), str(result))
    result = ask(server, name="stone", x=50.0, y=1.0)
    check("dev tile outside the world is ok False", result.ok is False and "outside the world" in result.text, str(result))
    check("dev tile needs a point on the wire", ask(server, name="stone").ok is False and ask(server, name="stone", x=1.0).ok is False and ask(server).ok is False)
    check("dev tile refuses a name with spaces or slashes before it gets to the world", all(ask(server, name=name, x=1.0, y=1.0).ok is False for name in ("a b", "a/b", "", "x" * 100, 5, None)))
    check("an item: name is just an unknown tile", ask(server, name="item:wood", x=1.0, y=1.0).text == "unknown tile 'item:wood'")

    normal = server_for(False)
    result = ask(normal, name="stone", x=4.0, y=2.0)
    check("a normal server refuses it and the world is untouched", result.text == "not available" and normal.sim.world.changes == {} and normal.sim.world.calls == [])
finally:
    tools.tiles_by_name = original

from dataclasses import asdict

from src.simworld.server.server import Client, Server
from src.simworld.shared import protocol as proto
from src.simworld.shared.phase import PLAYING
from src.simworld.sim.core.sim_context import TILE_UNITS
from src.simworld.sim.dev.sandbox_mode import populate_sandbox, prepare_sandbox
from src.simworld.sim.dev.start_units import give_test_units
from src.simworld.sim.simulation import Simulation
from src.simworld.world.generator import GenerationSettings, WorldGenerator
from src.simworld.world.tile_types import TILE_TYPES

names = sorted({tile.name for tile in TILE_TYPES.values()})
untypeable = [name for name in names if not isinstance(name, str) or not table.NAME_PATTERN.fullmatch(name)]
check("every tile name can be typed as a dev name", not untypeable, f"these cannot be used with /tile: {untypeable}")
check("there are at least two tiles to paint with", len(names) >= 2, str(names))

real_sim = Simulation()
real_sim.start_new_game(prepare_sandbox(real_sim, None))
populate_sandbox(real_sim)

for player in (1, 2):
    give_test_units(real_sim, player)

real = Server(real_sim, stats_interval=0, start_phase=PLAYING)
world = real_sim.world
announced = []
original_listener = world.on_tile_change
world.on_tile_change = lambda x, y: (announced.append((x, y)), original_listener(x, y))


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
    return [tuple(entry) for message in messages if message["type"] == proto.WORLD_DELTA for entry in message["tiles"]]


clients = {player: add_player(player) for player in (1, 2)}
tick()

for client in clients.values():
    drain(client)

painted = {}

for player, client in clients.items():
    unit = real_sim.entity_manager.get(real_sim.owned_ids(player)[0])
    tile_x, tile_y = math.floor(unit.position.x / TILE_UNITS), math.floor(unit.position.y / TILE_UNITS)
    current = world.get_tile(tile_x, tile_y).name
    new = next(name for name in names if name != current)
    result = dev.run_dev(real, client, "tile", {"name": new, "x": tile_x + 0.5, "y": tile_y + 0.5})
    check(f"player {player}: a real paint works", result.ok and result.data["changed"] is True, str(result))
    painted[player] = (tile_x, tile_y, new)
    check(f"player {player}: the world tile really changed", world.get_tile(tile_x, tile_y).name == new)
    check(f"player {player}: the tile change woke the neighbours (on_tile_change fired)", (tile_x, tile_y) in announced, str(announced))

tick()

for player, client in clients.items():
    seen = deltas(drain(client))
    check(f"player {player}: the tile changes on the client", painted[player] in seen, f"{painted[player]} not in {seen}")

for player in (1, 2):
    replacement = add_player(player)
    tick()
    seen = deltas(drain(replacement))
    check(f"player {player}: a client that reconnects gets the paint replayed", painted[player] in seen, f"{painted[player]} not in {seen}")

settings = GenerationSettings(**asdict(real_sim.generation_settings))
fresh = WorldGenerator(settings).generate()
fresh.finish_generation(record=False)
check("the generation checksum a joining client compares is unchanged by painting", fresh.generation_checksum == world.generation_checksum)
check("the painted world differs from the generated one", world.checksum() != world.generation_checksum)
tiles = {tile.name: tile for tile in TILE_TYPES.values()}

for (x, y), name in world.changes.items():
    fresh.set_tile(x, y, tiles[name])

check("replaying the recorded changes on a fresh world gives the same world", fresh.checksum() == world.checksum())

real_sim.sandbox = False
x, y, name = painted[1]
other = next(tile for tile in names if tile != name)
result = dev.run_dev(real, clients[1], "tile", {"name": other, "x": x + 0.5, "y": y + 0.5})
check("on a normal server a real paint is refused and the tile stays", result.text == "not available" and world.get_tile(x, y).name == name)

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")