import sys

from game.world.generator import WorldGenerator, GenerationSettings

SEED = 12345
print("started")
world = WorldGenerator(GenerationSettings(width=200, height=200, seed=SEED, tag_modifiers={"all": {"scale": 1.3}})).generate()
world.finish_generation()

print(sys.version.split()[0], "seed", SEED, "checksum", world.generation_checksum)