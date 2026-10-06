import hashlib
import sys

from game.simulation import Simulation
from game.world.generator import GenerationSettings

SEED = 42
STEPS = 300


def run():
    sim = Simulation(GenerationSettings(width=120, height=120, seed=SEED, debug=False, tag_modifiers={"all": {"scale": 1.3}}))
    sim.start_new_game(SEED)

    for _ in range(STEPS):
        sim.step()

    digest = hashlib.sha256()
    entities = sorted(sim.entity_manager.all(), key=lambda e: e.id)

    for e in entities:
        digest.update(f"{e.id}|{float(e.position.x).hex()}|{float(e.position.y).hex()}|{float(e.health).hex()}|{float(e.energy).hex()}|{e.alive}".encode())

    for position, name in sorted(sim.world.changes.items()):
        digest.update(f"{position}{name}".encode())

    return len(entities), digest.hexdigest()[:16]


first, second = run(), run()
print(sys.version.split()[0], "entities:", first[0], "hash:", first[1], "| same process:", "OK" if first == second else f"MISMATCH ({second[1]})")