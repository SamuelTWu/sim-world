import os
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.simworld.client.render.camera import Camera
from src.simworld.client.ui.dev.console import Console
from src.simworld.client.ui.dev.dev_panel import DevPanel, TOGGLE_KEY

failures = []
AREA = pygame.Rect(0, 0, 800, 600)


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Host:
    TILE_SIZE = 32

    def __init__(self, area=AREA):
        self.area = area
        self.camera = Camera(area.width, area.height, 32)
        self.camera.x, self.camera.y = area.width / 2, area.height / 2
        self.console = Console()
        self.view_entities = [SimpleNamespace(id=7, position=SimpleNamespace(x=500.0, y=400.0))]
        self.world_labels = ()

    def gui_area(self):
        return self.area

    def over_map(self, pos):
        return self.area.collidepoint(pos)

    def entity_radius(self, entity):
        return 14

    def dev_context(self):
        return {"selected": None, "cursor": None}

    def screen_to_world(self, pos):
        return self.camera.screen_to_world(*pos)


def painted(surface, rect):
    return any(surface.get_at((x, y))[:3] != (0, 0, 0) for x in range(rect.left, rect.right, 2) for y in range(rect.top, rect.bottom, 2))


def opened(host=None):
    panel = DevPanel(host or Host())
    panel.set_enabled(True)
    panel.set_catalog({"blueprints": ["wolf", "tree"], "tiles": ["grass"], "items": [], "structures": []})
    panel.handle_event(pygame.event.Event(pygame.KEYDOWN, key=TOGGLE_KEY, unicode="", mod=0, scancode=0))
    return panel


pygame.init()
pygame.font.init()
screen = pygame.Surface((800, 600))

panel = DevPanel(Host())
panel.draw(screen, 0.0)
check("a panel that is not enabled draws nothing", not painted(screen, screen.get_rect()))

panel.set_enabled(True)
panel.draw(screen, 0.0)
check("an enabled but closed panel draws nothing", not painted(screen, screen.get_rect()))

panel = opened()
panel.draw(screen, 0.0)
_, box, _, _ = panel.layout()
check("an open panel draws its column", painted(screen, box))
check("and nothing far from it", not painted(screen, pygame.Rect(400, 0, 400, 300)))
items, _, _, _ = panel.layout()
check("every button has a visible face", all(painted(screen, rect) for _, _, _, rect in items))

screen.fill((0, 0, 0))
panel.state.press("spawn")
panel.draw(screen, 0.0)
picker, options = panel.picker_layout(items)
check("the picker draws next to the column", painted(screen, picker) and picker.x >= box.right)

screen.fill((0, 0, 0))
panel.state.pick_option("wolf")
panel.draw(screen, 0.0)
check("the armed hint draws inside the box", painted(screen, pygame.Rect(box.x, box.bottom - 18, box.width, 18)))

screen.fill((0, 0, 0))
panel.state.cancel()
panel.state.select(7)
panel.draw(screen, 0.0)
check("the selected entity gets a ring", painted(screen, pygame.Rect(480, 380, 40, 40)))

screen.fill((0, 0, 0))
panel.note_result("inspect", {"ok": True, "text": "wolf\nhp 3\nspeed 2", "data": {"id": 7}})
panel.draw(screen, 0.0)
check("the inspect text draws next to the entity", painted(screen, pygame.Rect(520, 370, 160, 60)))

panel.note_result("inspect", {"ok": True, "text": "x " * 400, "data": {"id": 7}})
panel.draw(screen, 0.0)
check("a very long inspect text draws without error", True)

panel.host.view_entities = []
panel.draw(screen, 0.0)
check("an entity that is gone is skipped", True)

small = pygame.Surface((640, 400))
panel = opened(Host(pygame.Rect(0, 0, 640, 400)))
panel.draw(small, 0.0)
check("a small window still draws", True)

edge = Host(pygame.Rect(200, 30, 600, 500))
panel = opened(edge)
items, box, _, _ = panel.layout()
check("the panel follows the play area", box.x == 204 and box.y == 70, str(box))
panel.draw(screen, 0.0)
check("and draws there", painted(screen, box.inflate(-8, -8)))

pygame.quit()

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")