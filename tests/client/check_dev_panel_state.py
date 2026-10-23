import sys
from types import SimpleNamespace

from src.simworld.client.ui.dev.dev_panel_state import GOTO, PanelState, center_of, entity_at, fit_zoom, goto_target
from src.simworld.shared.dev_commands import DEV_COMMANDS, NEEDS_SELECTION, parse
from src.simworld.world.tile_types import TILE_TYPES
from src.simworld.world.sandbox import BLOCK, REGION_LABEL, REGION_SIZE, entity_slots, layout_for, region_origin

failures = []
CATALOG = {"blueprints": ["wolf", "tree"], "tiles": ["grass", "stone"], "items": ["wood"], "structures": ["wall"]}


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


def armed(kind, name):
    state = PanelState()
    state.set_enabled(True)
    state.set_catalog(CATALOG)
    state.toggle()
    state.press(kind)
    state.pick_option(name)
    return state


def typed(result):
    return [text[2:] for text, kind in result.lines if kind == "echo"]


state = PanelState()
check("a new panel is closed and disabled", not state.open and not state.enabled)
check("a disabled panel cannot be opened", state.toggle() is False and not state.open)
state.set_enabled(True)
check("an enabled panel opens and closes", state.toggle() is True and state.open and state.toggle() is True and not state.open)
state.toggle()
state.press("spawn")
state.set_enabled(False)
check("disabling closes the panel and drops its tools", not state.open and state.mode is None and state.picker is None)
state.set_enabled(True)
check("it stays closed after being enabled again", not state.open)

rows = state.rows()
check("the rows are pause, step, speed, spawn, delete, wake, inspect, paint, go to", [row[0][0] for row in rows] == ["pause", "step", "speed:0.25", "spawn", "delete", "wake", "inspect", "paint", "goto:tiles"], str([row[0][0] for row in rows]))
check("the speed row has three buttons and the go to row four", [len(row) for row in rows if row[0][0].startswith(("speed", "goto"))] == [3, 4])
check("the go to buttons are the four places", [key for key, _, _ in rows[-1]] == [f"goto:{name}" for name, _ in GOTO] and [label for _, label, _ in rows[-1]] == ["Tiles", "Entities", "Generated", "Start"])
check("pause starts as Pause and 1x is the active speed", rows[0][0][1] == "Pause" and [active for _, _, active in rows[2]] == [False, True, False])

for key, text in (("pause", "/pause"), ("step", "/step"), ("speed:0.25", "/speed 0.25"), ("speed:1", "/speed 1"), ("speed:4", "/speed 4")):
    result = state.press(key)
    check(f"{key} sends what the typed {text} sends", result.requests == (parse(text, {}),) and typed(result) == [text], str(result))

check("every speed button sends a speed the table accepts", all(state.press(f"speed:{label[:-1]}").requests for _, label, _ in rows[2]))
check("the echo line is a typed command the parser turns back into the request", all(parse(typed(result)[0], {}) == result.requests[0] for result in (state.press("pause"), state.press("step"), state.press("speed:4"))))
check("each echo is one line of kind echo", state.press("pause").lines == (("> /pause", "echo"),))

state.note_result("pause", {"ok": True, "text": "paused", "data": {"paused": True, "tick": 4, "speed": 4.0, "pending": 0}})
rows = state.rows()
check("a pause result flips the button to Resume", rows[0][0][1] == "Resume" and rows[0][0][2] is True)
check("a result moves the active speed", [active for _, _, active in rows[2]] == [False, False, True])
state.note_result("pause", {"ok": False, "text": "no", "data": {"paused": False, "speed": 1.0}})
check("a failed result changes nothing", state.paused is True and state.speed == 4.0)
state.note_result("pause", {"ok": True, "text": "x", "data": "bad"})
state.note_result("speed", {"ok": True, "text": "x", "data": {"speed": True}})
state.note_result("spawn", {"ok": True, "text": "x", "data": {"paused": False}})
check("odd results and other commands are ignored", state.paused is True and state.speed == 4.0)

result = state.press("wake", {"selected": None})
check("wake with nothing selected shows the error and sends nothing", result.requests == () and result.lines == ((NEEDS_SELECTION, "error"),))
check("a boolean is not a selection", state.press("wake", {"selected": True}).requests == ())
check("wake with a selection sends /wake <id>", state.press("wake", {"selected": 7}).requests == (("wake", {"id": 7}),) and typed(state.press("wake", {"selected": 7})) == ["/wake 7"])
check("inspect with a selection sends /inspect <id>", state.press("inspect", {"selected": 7}).requests == (("inspect", {"id": 7}),) and typed(state.press("inspect", {"selected": 7})) == ["/inspect 7"])
check("inspect with nothing selected sends nothing", state.press("inspect", {}).requests == () and state.press("inspect").requests == ())
check("an unknown button does nothing", state.press("nope").requests == () and state.press("nope").lines == () and state.press("nope").goto is None)

state = armed("spawn", "wolf")
check("picking a blueprint arms spawn and closes the picker", state.mode == "spawn" and state.picker is None and state.blueprint == "wolf")
check("the spawn button shows the blueprint and is active", state.rows()[3][0][1] == "Spawn: wolf" and state.rows()[3][0][2] is True)
result = state.click((10.3, 7.9))
check("a click sends /spawn at the middle of the tile", result.requests == (("spawn", {"blueprint": "wolf", "x": 10.5, "y": 7.5}),) and typed(result) == ["/spawn wolf 10.5 7.5"], str(result))
check("the typed line parses to the same request", parse("/spawn wolf 10.5 7.5", {}) == result.requests[0])
check("spawn stays armed for the next click", state.mode == "spawn" and len(state.click((1.2, 2.2)).requests) == 1)
check("a negative point is the middle of its own tile", state.click((-0.2, -1.5)).requests == (("spawn", {"blueprint": "wolf", "x": -0.5, "y": -1.5}),))
state.press("spawn")
check("pressing spawn again disarms it", state.mode is None and state.click((1, 1)).requests == ())
state.press("spawn")
check("pressing spawn when disarmed opens the picker", state.picker == "spawn" and state.mode is None)
state.press("spawn")
check("pressing spawn with the picker open closes it", state.picker is None)

state = PanelState()
state.set_enabled(True)
state.set_catalog(CATALOG)
state.press("spawn")
check("the spawn picker lists blueprints, items and structures", state.options("spawn") == ["wolf", "tree", "item:wood", "structure:wall"], str(state.options("spawn")))
check("the paint picker lists tiles", state.options("paint") == ["grass", "stone"])
check("without a catalog the pickers are empty", PanelState().options("spawn") == [] and PanelState().options("paint") == [])
state.pick_option("item:wood")
check("an item name can be spawned", typed(state.click((3, 4))) == ["/spawn item:wood 3.5 4.5"])
check("a click with a blueprint never picked sends nothing", PanelState().click((3, 4)).requests == ())
check("picking with no picker open does nothing", PanelState().pick_option("wolf") == ((), (), None))

state = armed("paint", "stone")
check("picking a tile arms paint", state.mode == "paint" and state.rows()[7][0][1] == "Paint: stone" and state.rows()[7][0][2] is True)
result = state.click((4.6, 5.1))
check("a click paints with /tile at the middle of the tile", result.requests == (("tile", {"name": "stone", "x": 4.5, "y": 5.5}),) and typed(result) == ["/tile stone 4.5 5.5"], str(result))
check("the same tile again while dragging sends nothing", state.drag((4.9, 5.9)).requests == ())
check("a new tile while dragging paints it", typed(state.drag((5.1, 5.2))) == ["/tile stone 5.5 5.5"] and typed(state.drag((5.1, 6.2))) == ["/tile stone 5.5 6.5"])
check("going back over a tile paints it again", typed(state.drag((5.1, 5.2))) == ["/tile stone 5.5 5.5"])
state.release()
check("after release a drag paints nothing", state.drag((9.1, 9.1)).requests == () and not state.painting)
check("a drag without a press paints nothing", armed("paint", "stone").drag((1.5, 1.5)).requests == ())
check("outside the world on the left or top is skipped", armed("paint", "stone").click((-0.5, 3)).requests == () and armed("paint", "stone").click((3, -0.5)).requests == ())
check("dragging with spawn armed sends nothing", armed("spawn", "wolf").drag((3, 3)).requests == ())

state = PanelState()
state.set_enabled(True)
state.press("delete")
check("delete arms", state.mode == "delete" and state.rows()[4][0][2] is True)
check("a click on empty ground deletes nothing", state.click((3, 3), None).requests == ())
result = state.click((3, 3), 12)
check("a click on an entity sends /delete <id>", result.requests == (("delete", {"id": 12}),) and typed(result) == ["/delete 12"])
check("delete stays armed", state.mode == "delete")
state.press("delete")
check("pressing delete again disarms", state.mode is None and state.click((3, 3), 12).requests == ())

state = armed("spawn", "wolf")
state.press("paint")
check("opening the other picker disarms the armed tool", state.mode is None and state.picker == "paint")
check("cancel closes the picker first", state.cancel() is True and state.picker is None)
check("cancel with nothing open reports nothing changed", state.cancel() is False)
state = armed("spawn", "wolf")
check("cancel disarms and reports it", state.cancel() is True and state.mode is None)
state.select(5)
state.note_result("inspect", {"ok": True, "text": "wolf\nhp 3", "data": {"id": 5}})
check("an inspect result is kept with its text", state.inspect == (5, "wolf\nhp 3"))
check("cancel clears the inspect text", state.cancel() is True and state.inspect is None)
state.note_result("inspect", {"ok": True, "text": "x" * 5000, "data": {"id": 5}})
check("inspect text is capped", len(state.inspect[1]) == 1000)
state.note_result("inspect", {"ok": True, "text": "no id", "data": {}})
check("an inspect result without an id is ignored", state.inspect[0] == 5)
state.select(6)
check("selecting another entity drops the inspect text", state.inspect is None and state.selected == 6)
state.select(6)
state.note_result("inspect", {"ok": True, "text": "again", "data": {"id": 6}})
state.select(6)
check("selecting the same entity keeps it", state.inspect is not None)

state = PanelState()
check("without a dev selection the fallback is used", state.current_selected({1, 2}, 9) == 9)
state.select(2)
check("a dev selection wins over the fallback", state.current_selected({1, 2}, 9) == 2)
check("a dev selection that is gone is dropped", state.current_selected({1}, 9) == 9 and state.selected is None)

state = PanelState()
state.set_enabled(True)
state.toggle()
state.set_catalog(CATALOG)
state.press("paint")
state.pick_option("grass")
state.select(3)
state.note_result("pause", {"ok": True, "data": {"paused": True, "speed": 4.0}})
state.reset()
check("reset puts everything back", not state.enabled and not state.open and state.catalog is None and state.blueprint is None and state.tile is None and state.selected is None and not state.paused and state.speed == 1.0 and state.mode is None)

for text in ("/spawn wolf 10.5 7.5", "/tile stone 4.5 5.5", "/delete 12", "/wake 7", "/inspect 7"):
    check(f"{text} is a command the table knows", parse(text, {})[0] in DEV_COMMANDS)

check("center_of", center_of((2.9, 3.0)) == (2.5, 3.5) and center_of((-0.1, -1.0)) == (-0.5, -0.5))

tile_count = len(TILE_TYPES)
layout = layout_for(tile_count)
labels = [(8 + (index % layout.columns) * 5, 8 + (index // layout.columns) * 5, f"t{index}") for index in range(tile_count)]
labels.append((layout.region_x, layout.region_y, REGION_LABEL))
region = goto_target(labels, "generated")
check("generated is the middle of the 50x50 section", region.x == layout.region_x + REGION_SIZE / 2 and region.y == layout.region_y + REGION_SIZE / 2 and region.span == REGION_SIZE, str(region))
tiles = goto_target(labels, "tiles")
tile_labels = [label for label in labels if label[2] != REGION_LABEL]
left, right = min(x for x, _, _ in tile_labels), max(x for x, _, _ in tile_labels) + BLOCK
top, bottom = min(y for _, y, _ in tile_labels), max(y for _, y, _ in tile_labels) + BLOCK
check("tiles is the middle of the gallery and covers it", tiles.x == (left + right) / 2 and tiles.y == (top + bottom) / 2 and tiles.span == max(right - left, bottom - top), str(tiles))
entities = goto_target(labels, "entities")
slots = entity_slots(tile_count)
check("entities is the middle of the entity slots", min(x for x, _ in slots) < entities.x < max(x for x, _ in slots) + 1 and min(y for _, y in slots) < entities.y < max(y for _, y in slots) + 1, str(entities))
start = goto_target(labels, "start")
check("start is above the gallery", start.y < 8 + 8 and start.x > 0 and start.span > 0, str(start))
check("the section label is at the section origin", region_origin() == (layout.region_x, layout.region_y))
check("an unknown name or empty labels give nothing", goto_target(labels, "moon") is None and goto_target([], "tiles") is None and goto_target(None, "start") is None and goto_target([], "generated") is None)
check("without a region label generated gives nothing", goto_target([label for label in labels if label[2] != REGION_LABEL], "generated") is None)
check("a lone region label still offers generated", goto_target([(60, 8, REGION_LABEL)], "generated").x == 85 and goto_target([(60, 8, REGION_LABEL)], "tiles") is None)
check("zoom fits the span in the smaller side with room to spare", abs(fit_zoom(50, (800, 600), 32, 0.01, 10) - 600 / (50 * 32 * 1.1)) < 1e-9)
check("zoom is clamped", fit_zoom(1, (800, 600), 32, 0.01, 2) == 2 and fit_zoom(100000, (800, 600), 32, 0.01, 2) == 0.01 and fit_zoom(0, (800, 600), 32, 0.01, 10) > 0)

things = [SimpleNamespace(id=1, position=SimpleNamespace(x=100.0, y=100.0)), SimpleNamespace(id=2, position=SimpleNamespace(x=110.0, y=100.0)), SimpleNamespace(id=3, position=SimpleNamespace(x=500.0, y=500.0))]
to_screen = lambda x, y: (x, y)
check("the entity under the point is found, owner or not", entity_at((101, 100), things, to_screen, lambda entity: 12) == 1)
check("the nearest of two overlapping entities wins", entity_at((109, 100), things, to_screen, lambda entity: 12) == 2)
check("nothing near gives None", entity_at((300, 300), things, to_screen, lambda entity: 12) is None and entity_at((300, 300), [], to_screen, lambda entity: 12) is None and entity_at((1, 1), None, to_screen, lambda entity: 12) is None)
check("the radius is per entity", entity_at((120, 100), things, to_screen, lambda entity: 25 if entity.id == 1 else 5) == 1)

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")