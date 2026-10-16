"""Client-side appearance data.

The simulation only knows `entity.sprite_id` (a string). This file maps that
string to how it is drawn. Only the renderer / client should import this module,
and the server never needs it.
"""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Sprite:
    shape: list | None = None
    image: str | None = None
    character: str | None = None
    color: tuple[int, int, int] = (255, 255, 255)
    size: tuple[int, int] = (16, 16)
    layer: int = 0


DEFAULT_SPRITE = Sprite()

# sprite_id -> how to draw it. Filled by load_sprites() (or register_sprite()).
SPRITES: dict[str, Sprite] = {
    "pixel": Sprite(),
}


def register_sprite(sprite_id: str, sprite: Sprite) -> None:
    SPRITES[sprite_id] = sprite


def get_sprite(sprite_id: str) -> Sprite:
    return SPRITES.get(sprite_id, DEFAULT_SPRITE)


def load_sprites(definitions_path) -> int:
    """Register the visual "sprite" block of every entity definition JSON in a folder.

    Each one is stored under the definition's "sprite_id" (default: the file name,
    which matches what EntityFactory.load_definition assigns). Files that aren't
    definitions, or have no sprite block, are skipped. Returns how many were registered.
    """
    count = 0

    for path in sorted(Path(definitions_path).glob("*.json")):
        try:
            with open(path, "r") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue

        block = data.get("sprite") if isinstance(data, dict) else None
        if not isinstance(block, dict):
            continue

        register_sprite(
            data.get("sprite_id", path.stem),
            Sprite(
                shape=block.get("shape"),
                image=block.get("image"),
                character=block.get("character"),
                color=tuple(block.get("color", [255, 255, 255])),
                size=tuple(block.get("size", [16, 16])),
                layer=block.get("layer", 0),
            ),
        )
        count += 1

    return count