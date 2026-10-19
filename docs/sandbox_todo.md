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
- [ ] **2.4 A calm world**
  **Do:** in sandbox mode, entities with traits still behave, but the gallery ones start **frozen** (not in the awake set, no decisions) until you wake them from the dev tools (step 4.4). That keeps the gallery still and readable, while you can release one to watch it act.
  **Done when:** after 200 ticks every gallery entity is still where it was; waking one makes it start deciding.

## Part 3: The server and the secret menu

- [ ] **3.1 `--sandbox` on the server**
  **Do:** in `server/server.py` add `--sandbox`: set `generation_settings.mode = "sandbox"`, use seed 0 unless `--seed` is given, run `build_sandbox_entities`, relax the 9.9 limits (all 0), and set `sim.sandbox = True`. Print `[server] SANDBOX MODE` at start.
  **Done when:** `python -m server.server --sandbox` starts, and a client joins and sees the gallery.
- [ ] **3.2 `LocalServer(sandbox=True)`**
  **Do:** add a `sandbox` option to `server/local.py` that adds `--sandbox` to the command line. Singleplayer is unchanged.
  **Done when:** a test starts a local sandbox server and a client reaches READY.
- [ ] **3.3 The hidden menu entry**
  **Do:** in `menu.py`, add a `DEVELOPER` result. The button is **not drawn** by default. It appears when the player types the word `dev` on the main screen (keep a short buffer of the last typed letters, reset after 2 seconds of no typing), or when the environment variable `SIMWORLD_DEV=1` is set. Once revealed, a "Developer" button is added under "Singleplayer". Put the sequence test in a small pure function `secret_typed(buffer)` so it can be checked without pygame.
  **Done when:** `check_menu_secret.py` (no pygame needed): `d`, `e`, `v` typed in order reveals it, other keys and timeouts do not, and the button list on a fresh menu has no Developer entry.
- [ ] **3.4 Start it from the game**
  **Do:** in `game.py` handle `DEVELOPER` like `SINGLEPLAYER`: `start_developer()` creates `LocalServer(sandbox=True)`, and `back_to_menu` returns to the main screen (a failed sandbox start shows its error there). Set `self.mode = DEVELOPER` so "new game" restarts a sandbox.
  **Done when:** choosing Developer opens the gallery world, and quitting to the menu and choosing it again works.
- [ ] **3.5 It never looks like a real game**
  **Do:** show a small "DEV" tag in a corner while in developer mode, and draw the tile and entity labels (step 1.3, 2.2) only then. Saves and scores (if any) are off in this mode.
  **Done when:** the tag and labels appear in developer mode and nowhere else.

## Part 4: Dev tools (sandbox only)

Keep this small: five commands, one panel.

- [ ] **4.1 The gate**
  **Do:** `command/commands/dev.py`: one command `dev` with a `what` argument. The server runs it **only when `sim.sandbox` is true**; otherwise it returns `Rejected("not available")` and counts `dev_refused`. The client never shows the dev panel in a normal game, but the gate is the real protection.
  **Done when:** `check_dev_commands.py`: every `dev` call is refused on a normal server and accepted on a sandbox one.
- [ ] **4.2 Pause, step, speed**
  **Do:** `dev pause`, `dev step` (advance one tick while paused), and `dev speed` (0.25x, 1x, 4x) change how often the server loop calls `sim.step()`. The simulation still advances only in whole fixed ticks, so determinism is unaffected.
  **Done when:** paused, the tick number stays put; `step` advances it by exactly 1; two runs with the same commands give the same world checksum.
- [ ] **4.3 Spawn and delete**
  **Do:** `dev spawn {blueprint, point}` (any blueprint name from the catalog, or `item:<resource>`, or `block:<resource>`) and `dev delete {id}`. Use the normal creation and removal paths so replication, limits (off here) and events all run.
  **Done when:** spawned things appear for every client and deleted ones disappear.
- [ ] **4.4 Wake and inspect**
  **Do:** `dev wake {id}` puts a frozen gallery entity back to normal (step 2.4). `dev inspect {id}` returns its stats through the stats registry (`health`, `energy`, `need:*`, `inventory:*`, `prop:*`, `tag:*`, `status:*`), its current task and the last few reasons it failed, and the client shows them in a small text panel next to the selected entity.
  **Done when:** inspecting a unit shows its stats, and waking a frozen one makes it start deciding.
- [ ] **4.5 Paint a tile**
  **Do:** `dev tile {point, name}` sets one tile through `world.set_tile`, so the existing world delta path sends it to clients and wakes sleepers.
  **Done when:** the tile changes on every client and the checksum comparison after a reconnect still passes (deltas are replayed).
- [ ] **4.6 The panel**
  **Do:** `client/dev_panel.py` (pygame): a single column opened with F3 in developer mode only, with buttons for pause, step, speed, a blueprint picker (from the catalog sent in the welcome message or fetched with `dev catalog`), and a tile picker. It only sends the commands above.
  **Done when:** every tool works from the panel, and the panel cannot be opened in a normal game.

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