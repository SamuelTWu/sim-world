"""Builds the client's own copy of the world from the server's welcome message."""
from game.world.generator import GenerationSettings, WorldGenerator


def generate_world(welcome):
    settings = GenerationSettings(**{**welcome["settings"], "seed": welcome["seed"]})
    generator = WorldGenerator(settings)
    world = generator.generate()
    world.finish_generation(record=False)
    return generator, world