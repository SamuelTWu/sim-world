import os
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.simworld.client.render.camera import Camera
from src.simworld.client.ui.dev.console import Console
from src.simworld.client.ui.dev.dev_panel import DevPanel, TOGGLE_KEY
from src.simworld.shared.dev_commands import NEEDS_SELECTION, parse
from src.simworld.world.sandbox import REGION_LABEL

failures = []
CATALOG = {"blueprints": ["wolf", "tree"], "tiles": ["grass", "stone"], "items": [], "structures": []}
AREA = pygame.Rect(0, 0, 800, 600)


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Host:
    TILE_SIZE = 32

    def __init__(self):
        self.camera = Camera(800, 600, 32)
        self.camera.x, self.camera.y = 400.0, 300.0
        self.console = Console()
        self.console.set_enabled(True)
        self.view_entities = [SimpleNamespace(id=7, position=SimpleNamespace(x=500.0, y=400.0)), SimpleNamespace(id=8, position=SimpleNamespace(x=620.0, y=400.0))]
        self.world_labels = ()
        self.own = None

    def gui_area(self):
        return AREA

    def over_map(self, pos):
        return AREA.collidepoint(pos)

    def entity_radius(self, entity):
        return 14

    def dev_context(self):
        return {"selected": self.own, "cursor": (1.0, 1.0)}

    def screen_to_world(self, pos):
        return self.camera.screen_to_world(*pos)


def make(enabled=True, opened=True, catalog=True):
    host = Host()
    panel = DevPanel(host)
    panel.set_enabled(enabled)

    if catalog:
        panel.set_catalog(CATALOG)

    if opened and enabled:
        panel.handle_event(key(TOGGLE_KEY))

    return host, panel


def key(code):
    return pygame.event.Event(pygame.KEYDOWN, key=code, unicode="", mod=0, scancode=0)


def down(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def up(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def move(pos):
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(1, 0, 0))


def wheel(amount):
    return pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=amount)


def button(panel, name):
    items, _, _, _ = panel.layout()
    return next(rect for key_, _, _, rect in items if key_ == name)


def press(panel, name, now=0.0):
    rect = button(panel, name)
    return panel.handle_event(down(rect.center), now), panel.handle_event(up(rect.center), now)


def log(host):
    return [(line.text, line.kind) for line in host.console.state.log]


host, panel = make(enabled=False)
check("a panel that is not enabled ignores F3", panel.handle_event(key(TOGGLE_KEY)) is False and not panel.is_open)
check("a panel that is not enabled ignores the mouse", panel.handle_event(down((50, 60))) is False and panel.handle_event(up((50, 60))) is False)
check("a panel that is not enabled has nothing to send", panel.take_requests() == [])

host, panel = make(opened=False)
check("an enabled panel starts closed", not panel.is_open)
check("a closed panel ignores the mouse", panel.handle_event(down((50, 60))) is False and panel.take_requests() == [])
check("F3 opens it and the key is taken", panel.handle_event(key(TOGGLE_KEY)) is True and panel.is_open)
check("F3 closes it", panel.handle_event(key(TOGGLE_KEY)) is True and not panel.is_open)
check("other keys are not taken", panel.handle_event(key(pygame.K_a)) is False)
check("Esc with nothing open is not taken, so the menu still opens", panel.handle_event(key(TOGGLE_KEY)) and panel.handle_event(key(pygame.K_ESCAPE)) is False)
panel.set_enabled(False)
check("disabling closes an open panel", not panel.is_open and panel.handle_event(key(TOGGLE_KEY)) is False)

host, panel = make()
items, box, heading, origin = panel.layout()
rects = [rect for _, _, _, rect in items]
check("every button is inside the panel box and the play area", all(box.contains(rect) and AREA.contains(rect) for rect in rects), str(box))
check("no two buttons overlap", all(not a.colliderect(b) for index, a in enumerate(rects) for b in rects[index + 1 :]))
check("the panel is one column on the left of the area", box.x == AREA.x + 4 and box.width == 248 and box.bottom < AREA.bottom)
check("the go to heading sits above the go to row", heading is not None and heading < button(panel, "goto:tiles").y)

consumed, released = press(panel, "pause", 1.0)
check("a button press and release are taken", consumed is True and released is True)
check("pause queues /pause", panel.take_requests() == [("pause", {})])
check("the typed command is echoed into the console log", log(host)[-1] == ("> /pause", "echo"), str(log(host)))
press(panel, "step")
press(panel, "speed:4")
press(panel, "speed:0.25")
requests = panel.take_requests()
check("step and speed queue the typed requests", requests == [("step", {"count": 1}), ("speed", {"factor": 4.0}), ("speed", {"factor": 0.25})], str(requests))
check("each press echoes its typed command", [text for text, kind in log(host) if kind == "echo"][-3:] == ["> /step", "> /speed 4", "> /speed 0.25"])
check("every echoed line parses back to the queued request", all(parse(text[2:], {}) == request for (text, _), request in zip([line for line in log(host) if line[1] == "echo"][-3:], requests)))
check("a click in the gap of the panel is taken and does nothing", panel.handle_event(down((box.x + 2, box.y + 2))) is True and panel.take_requests() == [] and panel.handle_event(up((box.x + 2, box.y + 2))) is True)

press(panel, "wake")
check("wake with nothing selected logs the error and queues nothing", panel.take_requests() == [] and log(host)[-1] == (NEEDS_SELECTION, "error"), str(log(host)[-1]))
host.own = 99
press(panel, "wake")
check("wake falls back to the normal selection", panel.take_requests() == [("wake", {"id": 99})] and log(host)[-1] == ("> /wake 99", "echo"))
press(panel, "inspect")
check("inspect sends /inspect with the selected id", panel.take_requests() == [("inspect", {"id": 99})])
host.own = None

check("a plain click on an entity is not taken, the camera still pans", panel.handle_event(down((500, 400))) is False)
check("releasing without moving selects that entity", panel.handle_event(up((502, 401))) is False and panel.state.selected == 7)
press(panel, "wake")
press(panel, "inspect")
check("wake and inspect use the clicked entity before the normal selection", panel.take_requests() == [("wake", {"id": 7}), ("inspect", {"id": 7})])
panel.handle_event(down((620, 400)))
panel.handle_event(up((700, 400)))
check("a press that moved is a pan, not a selection", panel.state.selected == 7)
panel.handle_event(down((300, 500)))
panel.handle_event(up((300, 500)))
check("a click on empty ground clears the selection", panel.state.selected is None)
host.view_entities = host.view_entities[1:]
panel.state.select(7)
press(panel, "wake")
check("an entity that disappeared is no longer selected", panel.take_requests() == [] and panel.state.selected is None)
host.view_entities = [SimpleNamespace(id=7, position=SimpleNamespace(x=500.0, y=400.0)), SimpleNamespace(id=8, position=SimpleNamespace(x=620.0, y=400.0))]

host, panel = make()
press(panel, "spawn")
items, _, _, _ = panel.layout()
picker, options = panel.picker_layout(items)
check("the spawn button opens a picker next to it listing the catalog", picker is not None and [name for name, _ in options] == ["wolf", "tree"] and picker.x > button(panel, "spawn").right)
check("opening the picker sends nothing", panel.take_requests() == [])
rect = dict(options)["tree"]
check("choosing a blueprint is taken and arms spawn", panel.handle_event(down(rect.center)) is True and panel.handle_event(up(rect.center)) is True and panel.state.mode == "spawn" and panel.state.blueprint == "tree" and panel.take_requests() == [])
check("an armed click on the map is taken", panel.handle_event(down((500, 400))) is True and panel.handle_event(up((500, 400))) is True)
requests = panel.take_requests()
check("it queues /spawn at the middle of that tile", requests == [("spawn", {"blueprint": "tree", "x": 15.5, "y": 12.5})], str(requests))
check("and echoes the typed line", log(host)[-1] == ("> /spawn tree 15.5 12.5", "echo"))
check("the armed tool does not select entities", panel.state.selected is None)
panel.handle_event(down((700, 500)))
panel.handle_event(up((700, 500)))
check("spawn stays armed for another click", len(panel.take_requests()) == 1 and panel.state.mode == "spawn")
check("Esc is taken and disarms it", panel.handle_event(key(pygame.K_ESCAPE)) is True and panel.state.mode is None)
check("an unarmed click on the map no longer spawns", panel.handle_event(down((500, 500))) is False and panel.take_requests() == [])
panel.handle_event(up((500, 500)))

host, panel = make()
press(panel, "spawn")
check("a click outside the picker closes it", panel.handle_event(down((600, 500))) is False and panel.state.picker is None)
panel.handle_event(up((600, 500)))

host, panel = make()
panel.set_catalog({"blueprints": [f"b{index:02d}" for index in range(30)], "tiles": [], "items": [], "structures": []})
press(panel, "spawn")
items, _, _, _ = panel.layout()
picker, options = panel.picker_layout(items)
original = pygame.mouse.get_pos
pygame.mouse.get_pos = lambda: picker.center
check("the wheel scrolls a long picker", panel.handle_event(wheel(-3)) is True and panel.state.scroll == 3 and panel.picker_layout(items)[1][0][0] == "b03")
panel.handle_event(wheel(-100))
check("the scroll stops at the end", panel.state.scroll == 30 - 12)
panel.handle_event(wheel(100))
check("and at the start", panel.state.scroll == 0)
pygame.mouse.get_pos = lambda: (600, 500)
check("the wheel outside the picker is left to the camera", panel.handle_event(wheel(-1)) is False and panel.state.scroll == 0)
pygame.mouse.get_pos = original

host, panel = make()
panel.set_catalog(None)
press(panel, "paint")
items, _, _, _ = panel.layout()
check("without a catalog the picker is empty and still opens", panel.picker_layout(items)[0] is not None and panel.picker_layout(items)[1] == [])

host, panel = make()
press(panel, "paint")
items, _, _, _ = panel.layout()
rect = dict(panel.picker_layout(items)[1])["stone"]
panel.handle_event(down(rect.center))
panel.handle_event(up(rect.center))
check("choosing a tile arms paint", panel.state.mode == "paint" and panel.state.tile == "stone")
check("a press on the map paints and is taken", panel.handle_event(down((500, 400))) is True)
check("dragging inside the same tile sends nothing more", panel.handle_event(move((505, 405))) is True and len(panel.take_requests()) == 1)
check("dragging to new tiles paints each one", panel.handle_event(move((540, 405))) is True and panel.handle_event(move((540, 440))) is True)
requests = panel.take_requests()
check("those are /tile requests for the new tiles", requests == [("tile", {"name": "stone", "x": 16.5, "y": 12.5}), ("tile", {"name": "stone", "x": 16.5, "y": 13.5})], str(requests))
check("each paint echoes its typed line", [text for text, kind in log(host) if kind == "echo"][-3:] == ["> /tile stone 15.5 12.5", "> /tile stone 16.5 12.5", "> /tile stone 16.5 13.5"], str(log(host)[-3:]))
check("releasing ends the stroke and is taken", panel.handle_event(up((540, 440))) is True and not panel.state.painting)
check("moving after the release paints nothing", panel.handle_event(move((600, 440))) is False and panel.take_requests() == [])

host, panel = make()
press(panel, "delete")
check("an armed delete click on empty ground sends nothing", panel.handle_event(down((300, 500))) is True and panel.take_requests() == [])
panel.handle_event(up((300, 500)))
panel.handle_event(down((620, 402)))
panel.handle_event(up((620, 402)))
check("an armed delete click on an entity sends /delete <id>", panel.take_requests() == [("delete", {"id": 8})] and log(host)[-1] == ("> /delete 8", "echo"))

host, panel = make()
host.world_labels = [(8 + index * 5, 8, f"tile{index}") for index in range(5)] + [(60, 8, REGION_LABEL)]
before = (host.camera.x, host.camera.y, host.camera.zoom)
press(panel, "goto:generated")
check("go to generated moves the camera to the middle of the section", (host.camera.x, host.camera.y) == ((60 + 25) * 32, (8 + 25) * 32), str((host.camera.x, host.camera.y)))
check("and zooms to fit it inside the limits", host.camera.min_zoom <= host.camera.zoom <= host.camera.max_zoom and host.camera.zoom != before[2])
check("go to sends nothing to the server and echoes nothing", panel.take_requests() == [] and all(kind != "echo" for _, kind in log(host)))
for name in ("tiles", "entities", "start"):
    host.camera.x = host.camera.y = -1.0
    press(panel, f"goto:{name}")
    check(f"go to {name} moves the camera", (host.camera.x, host.camera.y) != (-1.0, -1.0))
host.world_labels = ()
host.camera.x = host.camera.y = 5.0
press(panel, "goto:tiles")
check("go to with no labels leaves the camera and says so", (host.camera.x, host.camera.y) == (5.0, 5.0) and log(host)[-1][1] == "error" and panel.take_requests() == [])

host, panel = make()
press(panel, "delete")
panel.set_enabled(False)
check("disabling drops the armed tool and its clicks", panel.handle_event(down((620, 402))) is False and panel.take_requests() == [])
panel.reset()
check("reset forgets the catalog and the queue", panel.state.catalog is None and panel.take_requests() == [] and not panel.enabled)

host, panel = make()
panel.note_result("pause", {"ok": True, "text": "paused", "data": {"paused": True, "speed": 1.0}})
items, _, _, _ = panel.layout()
check("a pause result relabels the button", next(label for key_, label, _, _ in items if key_ == "pause") == "Resume")
panel.note_result("inspect", {"ok": True, "text": "wolf\nhp 3", "data": {"id": 8}})
check("an inspect result is kept for drawing", panel.state.inspect == (8, "wolf\nhp 3"))

pygame.quit()

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")