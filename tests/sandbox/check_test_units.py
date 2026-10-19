import contextlib
import io
import sys
import traceback
from types import SimpleNamespace

from src.simworld.sim.dev import start_units
from src.simworld.sim.dev.catalog import ENTITY, ITEM
from src.simworld.sim.dev.start_units import UNITS_PER_PLAYER, give_test_units, pick_unit, start_spots
from src.simworld.world.generator import GenerationSettings, WorldGenerator
from src.simworld.world.sandbox import BLOCK, tile_blocks

failures = 0
UNITS = 32


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


class FakeSim:
    def __init__(self):
        self.world = WorldGenerator(GenerationSettings(mode="sandbox", seed=1)).generate()
        self.spawned = []

    def spawn_pixel(self, definition, owner, x, y):
        entity = SimpleNamespace(id=len(self.spawned) + 1, definition=definition, owner=owner, position=SimpleNamespace(x=x, y=y), alive=True)
        self.spawned.append(entity)
        return entity


def quiet(function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = function(*args, **kwargs)

    return result, out.getvalue()


def tile_of(entity):
    return int(entity.position.x // UNITS), int(entity.position.y // UNITS)


FIRST, SECOND = start_units.UNIT_BLUEPRINTS[0], start_units.UNIT_BLUEPRINTS[1]
entries = [(ENTITY, SECOND, {"name": "Second"}), (ENTITY, FIRST, {"name": "First"}), (ENTITY, "tree", {}), (ITEM, "wood", {"resource": "wood", "amount": 1})]
check("the preferred unit blueprint is chosen", pick_unit(entries)[0] == FIRST)
check("the next preference is used when it is missing", pick_unit([entries[0], entries[2]])[0] == SECOND)
check("otherwise the first entity blueprint is used", pick_unit([entries[2], (ENTITY, "zebra", {})])[0] == "tree")
check("items and structures are never picked", pick_unit([entries[3]]) == (None, None))
check("no catalog entries means no unit", pick_unit([]) == (None, None))

sim = FakeSim()
units, out = quiet(give_test_units, sim, 1, entries, tile_units=UNITS)
check("a joining player gets 3 units", len(units) == UNITS_PER_PLAYER == 3 and len(sim.spawned) == 3)
check("they are owned by that player", all(unit.owner == 1 for unit in units))
check("they use the chosen blueprint", all(unit.definition["name"] == "First" for unit in units))
spots = [tile_of(unit) for unit in units]
covered = {(x, y) for _, x0, y0 in tile_blocks() for y in range(y0, y0 + BLOCK) for x in range(x0, x0 + BLOCK)}
check("they are inside the world, apart, and off the tile blocks", all(0 <= x < sim.world.width and 0 <= y < sim.world.height for x, y in spots) and len(set(spots)) == 3 and not any(spot in covered for spot in spots))
check("they are near the start corner", all(x < 16 and y < 8 for x, y in spots), str(spots))
check("they are centred in their tile", all(unit.position.x % UNITS == UNITS / 2 for unit in units))
check("giving units to the same player twice does nothing", quiet(give_test_units, sim, 1, entries, tile_units=UNITS)[0] == [] and len(sim.spawned) == 3)

sim = FakeSim()
every = []

for player in range(1, 40):
    every.append(quiet(give_test_units, sim, player, entries, tile_units=UNITS)[0])

given = [units for units in every if units]
check("many players each get their own spots with no overlap", len({tile_of(unit) for units in given for unit in units}) == 3 * len(given) and len(given) >= 16, f"{len(given)} players")
check("players past the start area get none, and are told", every[-1] == [] and "full" in quiet(give_test_units, sim, 99, entries, tile_units=UNITS)[1])
check("start spots fill a row of the margin per player, four rows, then the next column", start_spots(0) == [(2, 1), (4, 1), (6, 1)] and start_spots(1)[0][1] == 3 and start_spots(4)[0][0] > start_spots(0)[2][0])

none_sim = FakeSim()
result, out = quiet(give_test_units, none_sim, 1, [(ITEM, "wood", {})], tile_units=UNITS)
check("with no blueprint the player gets none and a message", result == [] and "no entity blueprint" in out)

first, second = FakeSim(), FakeSim()
quiet(give_test_units, first, 1, entries, tile_units=UNITS)
quiet(give_test_units, second, 1, entries, tile_units=UNITS)
check("two runs give identical units", [(u.owner, u.position.x, u.position.y) for u in first.spawned] == [(u.owner, u.position.x, u.position.y) for u in second.spawned])

try:
    from src.simworld.sim.simulation import Simulation
    from src.simworld.server.server import Client, Server
    from src.simworld.shared.phase import PLAYING
except ImportError:
    traceback.print_exc()
    check("the real simulation and server can be imported", False, "see the traceback above")
else:
    real = Simulation(GenerationSettings(mode="sandbox", seed=1))
    real.start_new_game(1)
    units, out = quiet(give_test_units, real, 1)
    check("real simulation: the player owns 3 living units", len(real.owned_ids(1)) == 3 and all(unit.alive and unit.owner == 1 for unit in units), out)
    check("real simulation: they count as that player's pixels", real.count_owned(1) == 3)

    other = Simulation(GenerationSettings(mode="sandbox", seed=1))
    other.start_new_game(1)
    server = Server(other, start_phase=PLAYING)
    calls = []
    server.on_new_player = calls.append

    for player in (1, 2, 3):
        server.sessions[player] = f"token{player}"

    quiet(server.admit, Client(websocket=None), 1, "alice", False)
    quiet(server.admit, Client(websocket=None), 1, "alice", True)
    quiet(server.admit, Client(websocket=None), 2, "bob", False)
    check("real server: the new-player hook runs once for each new player and not for a rejoin", calls == [1, 2], str(calls))
    server.on_new_player = lambda player_id: give_test_units(other, player_id)
    quiet(server.admit, Client(websocket=None), 3, "cara", False)
    check("real server: a joining player ends up with 3 units", len(other.owned_ids(3)) == 3)

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)