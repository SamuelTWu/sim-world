"""Client-side appearance data.

The simulation only knows `entity.sprite_id` (a string). This file maps that
string to how it is drawn. Only the renderer should import this module, and the
server never needs it.
"""
from dataclasses import dataclass


@dataclass
class Sprite:
    shape: list | None = None
    image: str | None = None
    character: str | None = None
    color: tuple[int, int, int] = (255, 255, 255)
    size: tuple[int, int] = (16, 16)
    layer: int = 0


DEFAULT_SPRITE = Sprite()

SPRITES: dict[str, Sprite] = {
    "pixel": Sprite(),
}


def register_sprite(sprite_id: str, sprite: Sprite) -> None:
    SPRITES[sprite_id] = sprite


def get_sprite(sprite_id: str) -> Sprite:
    return SPRITES.get(sprite_id, DEFAULT_SPRITE)