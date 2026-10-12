"""Builds the client's own copy of the world from the server's welcome message."""
from game.world.generator import GenerationSettings, WorldGenerator


def generate_world(welcome):
    settings = GenerationSettings(**{**welcome["settings"], "seed": welcome["seed"]})
    generator = WorldGenerator(settings)
    world = generator.generate()
    world.finish_generation(record=False)
    return generator, world


def tiles_by_name():
    """Tile name -> Tile, used to apply world_delta messages. Loaded when needed so client.py imports nothing from game/."""
    from game.tile.tile_types import TILE_TYPES

    return {tile.name: tile for tile in TILE_TYPES.values()}