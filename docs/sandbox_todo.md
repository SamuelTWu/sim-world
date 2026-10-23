# Developer Mode: a sandbox world with one of everything

Goal: a secret entry in the start menu that opens a local server and world containing **one of every tile and one of every entity**, laid out in a labeled gallery, with a few small tools for poking at things. Use it to test tiles, blueprints, actions, items and structures without hunting for them in a random world.

Conventions and "Do / Done when": same as the other plan files. Relative imports only, no comments or docstrings in new code, longer lines, snake_case files, an `__init__.py` in every folder, pygame only in `client/`. Run every existing check after each step.

This file does not depend on the entity foundation, actions, items or structures files. It finds blueprints by looking at the content folders, so whatever exists when you run it is shown, and each new JSON file you add later appears in the gallery on its own.

---

## The idea in one page

The client builds its own copy of the world from the server's welcome message (`generate_world(welcome)` rebuilds it from `welcome["settings"]` and the seed, then compares checksums). So the sandbox world must be **generated from the settings alone, the same way on server and client**. That is why the tile gallery is a new generation `mode`, not something the server paints afterwards. Entities are different: the server spawns them after the world exists and replicates them like any others.

Four pieces:
1. **A `sandbox` world mode** (`GenerationSettings.mode`): a flat floor with one of every tile type in a labeled grid. No noise, no maps, no features.
2. **A sandbox layout of entities**: one of every blueprint (and later every item and structure) in a second grid, plus a few player-owned test units at the start.
3. **A secret menu entry** that starts a local server with `--sandbox`.
4. **A few dev tools** (pause and step, spawn, inspect, delete, paint tile), which the server accepts **only** when it was started in sandbox mode.

---

## Part 1: The sandbox world (tiles)

- [X] **1.1 A `mode` setting**
  **Do:** add `mode: str = "normal"` to `GenerationSettings` (it is sent to clients in the welcome message because the whole dataclass is). Accept `"normal"` or `"sandbox"`; refuse anything else with a clear error. `WorldGenerator.generate()` calls `generate_sandbox` when the mode is `"sandbox"`.
  **Done when:** a normal world still generates exactly as before (the world checksum of a seeded 100x100 world is unchanged) and `mode="bogus"` is refused.
- [X] **1.2 The tile gallery**
  **Do:** `world/sandbox.py`: `generate_sandbox(settings) -> World`. Take `TILE_TYPES` sorted by name. Fill the world with one neutral floor tile (the default tile). Lay the tiles out in rows, each as a 3x3 block with a 2-tile gap between blocks, in sorted order, starting 8 tiles from the corner, as many per row as fit. Use no random numbers. Size the world from the tile count and the entity count (step 2.1) with a minimum of 64x64, and ignore `settings.width` and `height` in this mode.
  **Done when:** `check_sandbox_world.py`: every tile type appears in exactly one block, the same settings give an identical world checksum in two processes with different `PYTHONHASHSEED`, and adding a tile type adds a block with no other change.
- [X] **1.3 Labels**
  **Do:** a `labels` list on the sandbox world: `(x, y, text)` for each block, the tile name. Send nothing new: the client derives them from the same function (it rebuilds the world with the same code), and the renderer draws them in dev mode only (step 3.5). Keep the renderer reading them through a small `world.labels` attribute that is empty in normal worlds.
  **Done when:** the check lists one label per tile block, and normal worlds have none.
- [X] **1.4 A client builds the same sandbox world**
  **Do:** run the existing client/server world checksum comparison on a sandbox world (the check in `check_world_checksum.py` style).
  **Done when:** server and client checksums match and `run_local.py --sandbox` (add the flag) reports identical terrain images.

## Part 2: The entity gallery

- [X] **2.1 Find everything to show**
  **Do:** `sim/dev/catalog.py`: `gallery_entries() -> list[(kind, name, definition)]`, sorted by `(kind, name)`, built by listing the content folders at run time: every blueprint JSON in the entity folder, and, if the folders exist, every resource in `content/resources/` that has an `item` (one item stack) or a `structure` (one block). Skip a file that fails to load and print its name (a bad file must not stop the sandbox).
  **Done when:** the check shows the entries match the files in the folders, and dropping a new JSON file in the folder adds one entry with no code change.
- [X] **2.2 Lay them out**
  **Do:** `sim/dev/layout.py`: `build_sandbox_entities(sim)`: place one entity per entry in a grid on the far side of the tile gallery, 4 tiles apart, in catalog order, owned by `None`, through `spawn_pixel` (world building, so the limits do not apply). Items and structures use their own creation path when the files exist (`make_item`, `build_structure`). Put the label (kind and name) in `world.labels` or a parallel `entity_labels` list.
  **Done when:** `check_sandbox_entities.py`: exactly one entity per catalog entry, none on top of another, all inside the world.
- [X] **2.3 Test units for the player**
  **Do:** also spawn 3 player-owned units near the start corner when a player joins the sandbox (the same hook the normal game uses to give a player their first pixel), so commands can be tried at once.
  **Done when:** a joining player has 3 units and can command them.
- [X] **2.4 A calm world**
  **Do:** in sandbox mode, entities with traits still behave, but the gallery ones start **frozen** (not in the awake set, no decisions) until you wake them from the dev tools (step 4.4). That keeps the gallery still and readable, while you can release one to watch it act.
  **Done when:** after 200 ticks every gallery entity is still where it was; waking one makes it start deciding.

## Part 3: The server and the secret menu

- [X] **3.1 `--sandbox` on the server**
  **Do:** in `server/server.py` add `--sandbox`: set `generation_settings.mode = "sandbox"`, use seed 0 unless `--seed` is given, run `build_sandbox_entities`, relax the 9.9 limits (all 0), and set `sim.sandbox = True`. Print `[server] SANDBOX MODE` at start.
  **Done when:** `python -m server.server --sandbox` starts, and a client joins and sees the gallery.
- [X] **3.2 `LocalServer(sandbox=True)`**
  **Do:** add a `sandbox` option to `server/local.py` that adds `--sandbox` to the command line. Singleplayer is unchanged.
  **Done when:** a test starts a local sandbox server and a client reaches READY.
- [X] **3.3 The hidden menu entry**
  **Do:** in `menu.py`, add a `DEVELOPER` result. The button is **not drawn** by default. It appears when the player types the word `dev` on the main screen (keep a short buffer of the last typed letters, reset after 2 seconds of no typing), or when the environment variable `SIMWORLD_DEV=1` is set. Once revealed, a "Developer" button is added under "Singleplayer". Put the sequence test in a small pure function `secret_typed(buffer)` so it can be checked without pygame.
  **Done when:** `check_menu_secret.py` (no pygame needed): `d`, `e`, `v` typed in order reveals it, other keys and timeouts do not, and the button list on a fresh menu has no Developer entry.
- [X] **3.4 Start it from the game**
  **Do:** in `game.py` handle `DEVELOPER` like `SINGLEPLAYER`: `start_developer()` creates `LocalServer(sandbox=True)`, and `back_to_menu` returns to the main screen (a failed sandbox start shows its error there). Set `self.mode = DEVELOPER` so "new game" restarts a sandbox.
  **Done when:** choosing Developer opens the gallery world, and quitting to the menu and choosing it again works.
- [X] **3.5 It never looks like a real game**
  **Do:** show a small "DEV" tag in a corner while in developer mode, and draw the tile and entity labels (step 1.3, 2.2) only then. Saves and scores (if any) are off in this mode. Along with the developer section, include a generated section in the world, a small 50x50 sim using maps/features as normal, to test those features. Only allow map/feature toggles in dev mode
  **Done when:** the tag and labels appear in developer mode and nowhere else.

## Part 4: Dev tools (sandbox only)

Keep this small: a few commands, typed in a chat box or clicked in a panel, both going through one path. Nothing here touches `sim/commands/command.py` (the player commands) or its gates. Dev commands have their own message, table and handlers.

Where things live:
- `shared/dev_commands.py`: the table of dev commands and the text parser. Pure, no pygame.
- `server/dev_commands.py`: the registry, the gate, validation, and the pause, step and speed handlers (they act on the server loop).
- `sim/dev/tools.py` (new, next to `catalog.py` and `layout.py`): plain functions that act on the sim (`delete_pixel`, `inspect_pixel`, `paint_tile`, `regen_section`), so they can be tested without a server.
- `client/ui/dev/`: `console_state.py` (pure), `console.py` and `dev_panel.py` (pygame).

- [X] **4.1 The gate and the message**
  **Do:** in `shared/protocol.py` add the client message `dev {seq, what, args}` and the server message `dev_result {seq, ok, text, data}`, bump `PROTOCOL_VERSION` once and extend the `check_protocol.py` samples. In `server/dev_commands.py` add `DEV_HANDLERS = {}`, a decorator `@dev_command("name")`, and `run_dev(server, client, what, args) -> DevResult(ok, text, data)`. `run_dev` checks the existing `sim.sandbox` first: if it is false it returns `DevResult(False, "not available")` and adds to the counter `dev_refused`. Then it looks the command up (unknown: `"unknown dev command"`), validates `args` with `validate` from 4.2, and runs the handler. In `Server.handle`, route the message type `dev` to `run_dev` and send back `dev_result`; do not call `commands.execute`. Dev commands ignore the game phase (G.1). `run_dev` never raises: a handler exception becomes `ok False, "dev command failed"` and is printed.
  **Done when:** `tests/server/check_dev_commands.py`: every dev command is refused on a normal server and accepted on a sandbox one; a bad `what`, bad `args` or a non-dict `args` never raises.
- [X] **4.2 The command table and the typed syntax**
  **Do:** `shared/dev_commands.py`. `DEV_COMMANDS` maps each command name to its help text and its arguments; an argument has a name, a type (`int`, `number`, `name` or `point`, which is two numbers `x y` in tiles), whether it is optional, and optional `choices`. Functions: `parse(text, context) -> (what, args)` (raises `DevSyntaxError(message)`), `validate(what, args) -> args` (used by the server too: rejects wrong types and ranges, clamps `step` count to 1..100), `usage(what)` and `names()`. Typed forms (a leading `/` is expected in the console):
  `/pause`, `/step [count]`, `/speed 0.25|1|4`, `/spawn <blueprint> [x y]`, `/delete [id]`, `/wake [id]`, `/inspect [id]`, `/tile <name> [x y]`, `/catalog`, `/help [command]`. The generation commands (`/gen ...`) are added in 4.10.
  `context = {"selected": id or None, "cursor": (x, y) or None}`. Like Minecraft's `~`, an omitted point means the tile under the mouse and an omitted id means the selected entity, so `/spawn wolf` spawns at the mouse and `/wake` wakes the selection. If the needed context is missing the error is `"select something first"` or `"point at a tile first"`. The result contains only plain ints, floats and strings (msgpack safe).
  **Done when:** `tests/shared/check_dev_parser.py`: every command parses its example; the `~` and `@` defaults work; unknown command, missing argument, bad number and extra arguments each give a readable `DevSyntaxError`; `validate` rejects an out-of-range step count and a speed that is not in `choices`.
- [X] **4.3 Pause, step, speed**
  **Do:** `dev pause` toggles `server.paused`; `dev step {count}` adds to `server.pending_steps` (only while paused, default 1); `dev speed {value}` sets `server.speed` (0.25, 1 or 4). In `Server.tick_loop` replace the direct `self.sim.step()` with `self.advance()`: while paused it runs `pending_steps` ticks and clears the counter; otherwise it adds `speed` to a `credit` value and runs `int(credit)` ticks (at most 4), keeping the remainder. The inbox, order notices and replication still run every loop, so clients see edits while paused. The simulation still advances only in whole fixed ticks, so determinism is unaffected. The result text says where it is, for example `"paused at tick 1204"`.
  **Done when:** paused, the tick number stays put; `step 3` advances it by exactly 3; at speed 4 four ticks run per loop and at 0.25 one tick per four loops; two runs with the same dev commands give the same world checksum.
- [X] **4.4 Spawn and delete**
  **Do:** `dev spawn {blueprint, x, y}` (any blueprint name from the catalog, or `item:<resource>`, or `structure:<resource>`; x and y in tiles, the server places it at the tile centre and rejects a point outside the world). Use the same creation functions as 2.2 (`spawn_pixel`, `make_item`, `build_structure`; confirm their signatures) with the sender as owner, so the pixel is visible and commandable. `dev delete {id}` calls `delete_pixel` in `sim/dev/tools.py`, which uses the normal removal path. Limits are already relaxed in a sandbox (3.1), so add nothing for them. Result text: `"spawned wolf #123 at 40,22"`.
  **Done when:** spawned things appear for every client and deleted ones disappear; an unknown blueprint returns `ok False` with the name; the `item:` and `structure:` forms work.
- [X] **4.5 Wake and inspect**
  **Do:** `dev wake {id}` puts a frozen gallery entity back to normal with the same call 2.4 uses. `dev inspect {id}` (`inspect_pixel`) returns its stats through the stats registry (`health`, `energy`, `need:*`, `inventory:*`, `prop:*`, `tag:*`, `status:*`), its current task, and the last few reasons it failed (from `components["failures"]` once 13.4 exists, otherwise leave that line out). `text` is a short readable summary and `data` the full dict; the console prints `text` and the panel shows it in a small text box next to the selected entity.
  **Done when:** inspecting a unit shows its stats, and waking a frozen one makes it start deciding.
- [X] **4.6 Paint a tile**
  **Do:** `dev tile {name, x, y}` (`paint_tile`; tile name from `TILE_TYPES`, x and y in tiles) sets one tile through `world.set_tile`, so the existing world delta path sends it to clients and wakes sleepers.
  **Done when:** the tile changes on every client, an unknown tile name is refused with its name, and the checksum comparison after a reconnect still passes (deltas are replayed).
- [X] **4.7 Catalog**
  **Do:** add `catalog_names()` to `sim/dev/catalog.py`: blueprint and resource names taken from `gallery_entries()` (2.1) plus tile names from `TILE_TYPES`, each list sorted. `dev catalog` returns `{"blueprints": [...], "tiles": [...], "resources": [...]}`; the client asks once after joining a sandbox and caches it for Tab completion and the pickers.
  **Done when:** the lists match the registries and the files on disk, and a normal server refuses the call.
- [X] **4.8 The console (typed commands)**
  **Do:** `client/ui/dev/console_state.py` (pure, no pygame): the text buffer with a cursor, command history (last 50, Up and Down), `complete(buffer, catalog)` for Tab (first the command names, then blueprint, tile or resource names by argument position) and a log of lines (last 100, each with the time it was added). `client/ui/dev/console.py` (pygame): `T` opens an empty box, `/` opens it with `/` already typed, Enter parses with `parse` and sends the `dev` message, Esc closes it. While it is open every key event goes to the console and none reaches the game (no camera or hotkeys while typing). While it is closed the last 8 lines stay visible for 6 seconds and then fade, like Minecraft chat. `dev_result` text is appended in green when `ok` and red when not. Text without a leading `/` shows `"dev commands start with /"`. The console exists only in developer mode (`game.mode == DEVELOPER`, 3.4, and the welcome settings say `mode == "sandbox"`); otherwise `T` and `/` do nothing. If `T` is already bound in the game, rebind that one key in the key map (one place) and keep `/`.
  **Done when:** `tests/client/check_console_state.py` (no pygame): history Up and Down, Tab completion at each argument position, buffer editing (insert, backspace, cursor moves), the log limit. By hand: in developer mode `T` and `/` open the box, `/pause` stops the ticks, `/spawn <name>` places at the mouse; in a normal game nothing opens.
- [ ] **4.9 The panel**
  **Do:** `client/ui/dev/dev_panel.py` (pygame): a single column opened with F3 in developer mode only. Buttons: Pause or Resume, Step, Speed (0.25x, 1x, 4x), Spawn (a blueprint picker from the catalog, then click to place), Delete (click an entity), Wake (selected), Inspect (selected, shows the text next to it), Paint tile (a tile picker, click or drag to paint), and a "Go to" row (Tiles, Entities, Generated, Start) that moves the camera to the matching label from `world.labels` (client only, nothing is sent). Every button that changes the world builds the same `(what, args)` as the typed command and sends it through the one function the console uses (`send_dev(what, args)`), so there is one path, and each press also echoes the equivalent `/` command into the console log.
  **Done when:** every tool works from the panel, each press shows its typed equivalent in the log, and the panel cannot be opened in a normal game.
- [ ] **4.10 Map and feature toggles**
  **Do:** inspect how the generator picks features and reads maps first, and use what exists. Add `sim.sandbox_gen = {"seed": n, "disabled_features": set(), "disabled_maps": set()}` (runtime only, nothing is saved) and make the generator read it for the 3.6 section only: a disabled feature is skipped by the selection strategy, a disabled map reads as its neutral value. With nothing disabled the result is identical to 3.6, and a normal world's checksum is unchanged. Command `dev gen {action, name, value}` with typed forms `/gen list`, `/gen feature <name> on|off`, `/gen map <name> on|off`, `/gen seed <n>`. Every change regenerates the nxn (can also set) section and writes only the tiles that differ through `world.set_tile` (`regen_section` in `sim/dev/tools.py`), so clients get ordinary deltas and a reconnecting client replays them. Add the `/gen` forms to the table in 4.2. `/gen list` returns the current seed and each feature and map with its on or off state. The toggles are refused outside a sandbox by the 4.1 gate, which is what keeps them dev-only.
  **Done when:** `tests/server/check_dev_gen.py`: turning a feature off removes its tiles from the section and turning it on brings them back; the same toggles and seed give the same tiles in two runs; only differing tiles are written; a normal server refuses `gen`; the checksum after a reconnect still passes.
- [ ] **4.11 Generation section in the panel**
  **Do:** in `dev_panel.py` add a "Generation" section: the seed with a "New seed" button, and a checkbox list of every feature and map (names from `dev gen list`, refreshed after each result). Each click sends the matching `/gen` command through `send_dev` and echoes it into the console log.
  **Done when:** toggling a box in the panel changes the generated section on screen and the typed equivalent appears in the log.

## Part 5: Checks and docs

- [ ] **5.1 Checks in the runner.** Add `check_sandbox_world`, `check_sandbox_entities`, `check_menu_secret` and `check_dev_commands` to `tools/run_checks.py`. They must also pass in the determinism audit (two hash seeds).
- [ ] **5.2 Every blueprint spawns.** Add one check that spawns every catalog entry in a sandbox simulation, runs 100 ticks, and reports any entry that raises (a quick way to catch a broken blueprint after any change).
- [ ] **5.3 Docs.** Put this in the project layout doc: how to open Developer mode (type `dev` on the menu, or `SIMWORLD_DEV=1`), `--sandbox` for a headless server, what the gallery contains, and that dev commands are refused on any non-sandbox server.

---

### Decisions made in this plan (change them if you want)
- The secret is typing `dev` on the main menu (or `SIMWORLD_DEV=1`).
- The tile gallery is a generation mode, so the client rebuilds it from the settings; entities are spawned by the server.
- Gallery entities start frozen so the gallery stays still; the dev tools wake them one at a time.
- Dev commands exist only on a server started with `--sandbox`.

### Open questions
- Is typing `dev` the secret you want, or a key combination (for example Ctrl+Shift+D)?
- Should gallery entities start frozen (this plan) or fully active?
- Should the sandbox world be saved between sessions, or always rebuilt?
- Should the same `--sandbox` server accept more than one player (to test multiplayer features), or just you?
- Which tools matter most to you, so they are built first (spawn, inspect, pause and step)?