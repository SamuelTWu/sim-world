import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.simworld.client.render.world_renderer import WorldRenderer
from src.simworld.world.sandbox import layout_for, region_origin
from src.simworld.world.tile_types import TILE_TYPES

failures = []


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Camera:
    scaled_tile_size = 32

    def world_to_screen(self, x, y):
        return x, y

    def get_visible_tile_bounds(self, obj):
        return 0, 99, 0, 99


class Map:
    width = height = 4

    def get(self, x, y):
        return 1.0


class Maps:
    def get(self, name):
        return Map()


class Feature:
    def get_debug_data(self):
        return [[1.0] * 4 for _ in range(4)]


class Features:
    def get(self, name):
        return Feature()


class World:
    width = height = 100


pygame.init()
screen = pygame.Surface((3200, 3200))
renderer = WorldRenderer(screen, Camera(), pygame.font.Font(None, 18), 32)

renderer.render_map(Maps(), "m", World(), (10, 5))
check("the map is drawn at the offset", screen.get_at((10 * 32 + 4, 5 * 32 + 4))[:3] == (255, 255, 255) and screen.get_at((100, 100))[:3] == (0, 0, 0))
check("the map covers its own size only", screen.get_at((14 * 32 + 4, 5 * 32 + 4))[:3] == (0, 0, 0) and screen.get_at((13 * 32 + 4, 8 * 32 + 4))[:3] == (255, 255, 255))

screen.fill((0, 0, 0))
renderer.render_feature(World(), Features(), "f", (10, 5))
check("the feature is drawn at the offset", screen.get_at((10 * 32 + 4, 5 * 32 + 4))[:3] != (0, 0, 0) and screen.get_at((100, 100))[:3] == (0, 0, 0))

screen.fill((0, 0, 0))
renderer.render_map(Maps(), "m")
check("with no offset it draws from the corner as before", screen.get_at((4, 4))[:3] == (255, 255, 255))

x, y = region_origin()
layout = layout_for(len(TILE_TYPES))
check("region_origin matches the layout", (x, y) == (layout.region_x, layout.region_y))

pygame.quit()

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)
print("OK")