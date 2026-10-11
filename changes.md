# Multiplayer Refactor Log
Running list of what was changed, by README step. Newest at the bottom.

### 1.1 Headless Simulation
- simulation.py (new): owns generation settings, generator, world, entity manager, behavior manager, systems, seeded RNG. `start_new_game(seed)` and `step(dt)`.
- game.py: now only the window, loop, and renderer. All state is under `game.sim`.
- Seed always resolves to a concrete value (`sim.seed`). Starting pixels use `sim.rng`, not global `random`.
- game.py re-subscribes to `tile_placed` after every new game (systems are recreated).

### 1.2 Remove rendering references
- entity.py: removed `Sprite` dataclass; `sprite: Sprite` is now `sprite_id: str = "pixel"`.
- rendering/sprites.py (new): `Sprite` dataclass, `SPRITES` registry, `get_sprite(sprite_id)` with a default fallback, and `load_sprites(path)`, which reads the "sprite" block from each entity definition JSON and registers it under the definition's `sprite_id` (default: file name).
- rendering/entity_renderer.py:
  - uses `get_sprite(entity.sprite_id)` instead of `entity.sprite` (including the layer sort).
  - owner border now reads `entity.owner` (a real field) instead of `entity.props["owner"]`. Also fixes player id 0 being skipped.
  - owner colors now come from a fixed palette indexed by player id (old `hash(owner)` gave near-identical colors for small ids).
- entity/entities/entityFactory.py:
  - no longer imports or builds `Sprite`; sets `sprite_id` instead.
  - `load_definition` stamps `sprite_id` (default: the definition's file name) onto each loaded definition, so blueprints that carry the dict also carry the id.
  - the "sprite" block in definition JSON is untouched and ignored by the simulation. Only the client reads it.
- game.py: calls `load_sprites(...)` once on startup (client only).

### Open items found along the way
- Search the whole project for `props["owner"]` / `props.get("owner")` and switch to `entity.owner`.
- Anything else reading `entity.sprite` (renderer.py, world_renderer.py, others) must use `get_sprite(entity.sprite_id)`.
- main.py / menu.py: check for `game.world`, `game.entity_manager`, `game.generator`, `game.generation_settings`, `game.systems`; they now live under `game.sim`.
- 1.7: search entity/ for global `random` use.
- Later (client/server split): the client needs its own copy of the definitions folder for `load_sprites`, since it won't have a Simulation.

### 1.2 - 1.4 (done by you)
- Rendering references removed from entity.py, entityManager.py, system/, behavior/.
- Pixels have stable unique `id` and `owner`.
- Pixel state and blueprints are serializable (plain ints/floats/strings/lists).
- Persistent simulation decisions moved server-side so clients can replicate authoritative state without owning simulation logic.

### 1.5 Fixed-step tick
- simulation.py: `TICK_RATE = 20`, `TICK_DT = 0.05`. `step()` takes no argument and always advances `TICK_DT`. Added `sim.tick` counter (reset on new game).
- game.py: accumulator loop (`step_simulation`). Frame time is clamped to 0.25s, max 5 steps per frame (backlog dropped if exceeded). `renderer.update()` still uses real frame time.
- game.py: `self.alpha` (0..1 progress to the next tick) is computed but unused until interpolation (Phase 8.1).
- Known visual side effect: with a 20 Hz sim and 60 FPS render, pixels move in visible steps until interpolation exists. Temporarily set `TICK_RATE = 60` if it bothers you.
- Check: search simulation code for `time.time`, `perf_counter`, `pygame.time`, and `delta` params that bypass TICK_DT.

### 1.6 Single world-edit path
- Grep found no direct tile writes outside world.py. Only runtime tile edit is build.py (already uses `world.set_tile`); the other hit is generation (featureManager.py). No changes needed in either.
- world/world.py: `set_tile` is now the only write path. Returns True if the tile was replaced; skips identical tiles.
- world/world.py: added `recording` flag, `changes` ((x, y) -> tile name, latest only) and `dirty` set, plus `take_dirty()` for broadcasts (Phase 6). Only changes after generation are recorded.
- world/world.py: `fill()` raises if called while recording (generation only).
- simulation.py: `self.world.recording = True` right after `generate()`.
- `tile_placed` event untouched (build.py emits it, game.py and territoryRules.py listen).
- Deltas use `tile.name` as the tile id. Verify: `python -c "from game.tile.tile_types import TILE_TYPES; print([k for k, t in TILE_TYPES.items() if t.name != k])"` should print `[]`.
- Phase 2 note: Tile colors use unseeded `random` in `Tile.__post_init__`. Checksums must hash tile names, never colors.

### 1.7 Seeded RNG (in progress)
- entity/system/simContext.py: added `rng` field; raises if it is missing, so a forgotten wire-up can't silently fall back to nondeterminism.
- simulation.py: passes `rng=self.rng` to `SystemRunner`.
- systemRunner.py: must accept `rng` and pass it to `SimContext(...)`.
- Behaviors and generators use `context.rng.<method>(...)` instead of `random.<method>(...)` (revert `step(self, simulation, ...)` signatures back to `step(self, entity, context, delta_time)`).
- Search for leftovers: `grep -rnE "import random|from random|np\.random|numpy\.random|\brandom\.[a-z]+\(" game --include=*.py`

### 1.7 / 2.1 world/generator.py
- Already used its own seeded `random.Random` (not the global module), so no `Simulation.rng` needed here.
- `self.random` is now seeded with `f"world:{seed}"` (a separate stream from the sim RNG). A `None` seed still gives a random generator, as before.
- Same seed now produces a different world than before this change.
- Still to audit for global `random` use: map/, feature/, tile/ (should use `generator.random` / `context.random`).

### 2.1 world/noise.py
- Pure-Python Perlin: no hash(), no global random, basic float math only, so results are bit-identical across machines.
- Permutation shuffle replaced with an explicit Fisher-Yates driven by `Random.random()`. `random.shuffle` output is not guaranteed stable across Python versions; `random()` is.
- Side effect: the same seed gives different terrain than before this change.
- check_noise.py (run from the project root: `python check_noise.py`): hashes a 64x64 grid of noise. Expected `ed45e0cbc496863e` on every machine and Python version.

### 2.1 tile/tile.py
- `Tile.resolve_color` no longer uses the global `random`. A color list / color range now resolves from `random.Random(f"tile:{name}")` using only `random()`, so each tile type gets the same color on every machine and every run.
- Terrain was never affected (the generator uses its own RNG); this makes tile colors identical across clients and removes the last global `random` use in tile/.
- Per-tile speckle, if wanted later, belongs in the renderer (derived from x, y), not in the shared Tile object.

### 1.7 Seeded RNG (done)
- Grep of `game/` shows the only global `random` call left is `random.randrange(2**32)` in simulation.py (picks a seed when none is set; the server does this, clients never do).
- Everything else is a seeded instance: `context.rng` (simulation), `generator.random` / `context.random` (world generation, features, magic map).
- check_sim_determinism.py (run from the project root): runs two same-seed simulations for 300 steps and hashes entity state + tile changes. Run it under different hash seeds and compare the hash:
  `PYTHONHASHSEED=1 python check_sim_determinism.py` and `PYTHONHASHSEED=2 python check_sim_determinism.py`
- Not part of 1.7 (Phase 2.1): confirm FeatureManager registers features in a fixed order (no unsorted directory listing), and grep for other nondeterminism: `uuid|secrets|urandom|time.time|datetime|\bhash\(`.

### 2.1 Determinism audit tool
- audit_determinism.py (run from the project root): static scan of game/world, game/map, game/feature, game/tile (or any paths you pass).
- Flags: hash(), unseeded or global random (random, numpy), entropy sources (urandom, uuid, secrets), iteration over sets (loops, comprehensions, list()/join()/*unpack/.pop()), dicts loaded from json/msgpack/yaml/pickle, unsorted directory listings, id(), wall-clock time, libm math functions and fractional powers, numpy imports.
- Levels: HIGH = will break determinism, MEDIUM = check it, LOW = usually fine. Exit code 1 if any HIGH.
- Silence a reviewed line with a trailing `# determinism: ok`.

### 2.2 World checksum
- world/world.py: `checksum(x0, y0, x1, y1)` returns a SHA-256 of tile names, row by row (y, then x), with the world size and region in the header. Colors and other tile fields are ignored. Whole world by default; optional region for chunk-level comparison later. About 13 ms for 500x500.
- world/world.py: `finish_generation()` stores `generation_checksum` (terrain before any changes) and turns on change recording. The server sends this to joining clients; each client compares it with its own freshly generated world.
- simulation.py: calls `self.world.finish_generation()` right after `generate()` (replaces `self.world.recording = True`).
- check_world_checksum.py: prints the checksum for seed 12345 (200x200). Run it under different `PYTHONHASHSEED` values and on each machine; the checksum must match every time.
- Tile names are the ids, so they must be unique and match their TILE_TYPES keys (see the check under 1.6).

### 3.1 Protocol
- server/protocol.py (new): message builders (`join`, `welcome`, `command`, `tick_update`, `world_delta`, `error`), `validate`, `encode`, `decode`, `ProtocolError`. No imports from game/.
- Messages are dicts with a `type` field, msgpack-packed, one binary WebSocket frame each. Max 1 MB. `PROTOCOL_VERSION = 1`; bump it whenever a message changes shape.
- Strict schemas: unknown types, missing fields, wrong types (bool is not an int), and unexpected fields are rejected.
- `decode(data, accept=CLIENT_TYPES)` on the server and `accept=SERVER_TYPES` on the client, so a peer can't send the other side's messages.
- welcome = player_id, seed, settings (dict), checksum (`world.generation_checksum`), tick, tick_rate.
- tick_update = tick plus optional enter / update / leave / events lists and `ack` (last command seq processed); empty fields are omitted.
- world_delta = tick plus `tiles`: a list of [x, y, tile_name] (the output of `world.take_dirty()`).
- check_protocol.py (run from the project root): round-trips every message and checks the rejections. Needs `pip install msgpack`; then add its pinned version to requirements.txt.

### 3.2 Server
- server/server.py: asyncio WebSocket server. One tick loop drains an inbox and runs `Simulation.step()` at TICK_RATE; one handler per connection validates frames and pushes them into the inbox. Only the tick loop touches the simulation and the player table.
- Join flow: version check, capacity check, player ids from 1 (never reused), name cleaned, `welcome` sent. Commands are rejected for now (`command_rejected`).
- Protection: per-client pending-message cap, bounded per-client outbox (slow clients are dropped, the tick loop never waits on a socket), 10 s join timeout, 1 MB frame limit, binary frames only.
- Run: `python -m server.server [--host 0.0.0.0] [--port 8765] [--seed N] [--size N] [--max-players N]`.
- check_server.py: real-library smoke test. Logic was tested here with fake sockets only.

### 3.3 - 3.4 Client and world sync
- server/client.py: background-thread network layer (states: idle, connecting, generating, ready, failed, closed). `start()`, `wait()`, `poll()`, `send()`, `command()`, `close()`.
- After the welcome the client generates the world from the seed and settings (server/worldsync.py) and compares its checksum with the server's. A mismatch ends in FAILED with a clear "world mismatch" error and the client never reaches READY.
- world/world.py: `finish_generation(record=False)` for clients, so they don't log changes.
- check_client.py: real-library smoke test.

### 3.5 Local multiplayer test
- run_local.py: starts the server and two clients as separate processes (different PYTHONHASHSEED values), checks both verified the server's checksum, and writes terrain_alice.png / terrain_bob.png (byte-identical when the terrain is identical). `--test-mismatch` also checks that a tampered client is refused.
- Not yet true: the server may send tick_updates as soon as a client joins. In Phase 7, wait for a client `ready` message first, because world generation can take longer than the server's outbox allows.

### 4.1 Single player = local server
- server/local.py (new): `LocalServer` starts `python -m server.server` as a background process on 127.0.0.1 with a free port. States: starting, ready, failed, exited, stopped. Output is echoed to the console; the ready line is detected from the server's output.
- The server exits by itself if the game dies (it watches the stdin pipe the launcher keeps open), and `stop()` also runs at interpreter exit.
- server/server.py: prints `READY_MARKER` once it is listening; `--watch-stdin`; `--size`.
- game.py: `Game` no longer owns a Simulation. `start_new_game` starts a LocalServer; the loop shows status text (Starting server / Connecting / Generating world / errors) until the Client is READY, then renders `client.world` with `client.generator.maps/features`. Shutdown (including after an exception) stops the client and the server.
- Known for now: no entities are drawn in single player until Phase 7 (the renderer is given an empty list), and the `tile_placed` redraw hook is gone until Phase 6 re-adds cache invalidation on `world_delta`.
- Anything that used `game.sim` (menu.py, main.py, other tools) must be updated.
- Frozen builds (Phase 11) cannot use `python -m`; the launcher will need an in-process or multiprocessing variant.

### 4.2 Main menu
- menu.py (new, replaces any existing menu.py): main screen (Singleplayer, Join, Quit) and a join screen with an address field. Mouse or keyboard (Up/Down/Enter); Esc goes back from the join screen. `normalize_address` accepts `host`, `host:port`, `ws://host:port`, `wss://...`, `[::1]:port` and fills in port 8765; bad input shows a message. Ctrl/Cmd+V pastes (best effort). The last typed address is remembered while the game runs.
- `Menu.show(notice, screen)` blocks and returns `("singleplayer", None)`, `("join", url)` or `("quit", None)`.
- game.py: shows the menu on startup. Singleplayer starts the local server and connects (4.1). Join connects straight to the typed address with no local server. While connecting/generating/failed, Esc returns to the menu (the join screen if you were joining) with the failure reason shown. Restart reconnects to the same server in join mode.
- Join name is fixed to "player" for now.
- No in-game way back to the menu yet: that needs a key in the renderer's event handling (4.3).

### 4.3 Renderer reads only the client's state
- server/replica.py (new): `View` (frozen snapshot: world, maps, features, entities, player_id), `ReplicatedEntity` (id, sprite_id, owner, position) and `Position`. No imports from game/.
- server/client.py: `client.entities` (empty until Phase 7) and `client.view()`, which copies the entity list into a fresh View. Only valid when READY.
- rendering/renderer.py: `render(view)` replaces `render(world, maps, features, entities)`; the renderer can no longer be handed a Simulation. Esc sets `menu_requested`.
- game.py: `renderer.render(client.view())`; Esc in game calls `back_to_menu()` (single player returns to the main menu, join returns to the join screen).
- check_renderer_isolation.py: fails if anything in game/rendering imports game.simulation, game.entity, game.game, server.server or server.local, or uses the name Simulation or a `.sim` attribute.
- Phase 7 rule: client.entities is only changed on the game thread (poll() will apply tick_updates), so view() never races with the network thread.

### 5.1 Commands (move)
- server/commands.py (new): `execute(ctx, player_id, name, args)` is the only entry point; it never raises for bad input (a crashing handler is logged and rejected). Registry: subclass `Command`, set `name`, implement `run`, decorate with `@command`.
- Commands are an aspect of a pixel: a pixel only obeys `move` if `traits["command"]["move"]` is true (`grant`, `revoke`, `commandable`). Off by default, so the player cannot command anything until you give pixels the trait.
- Who may be commanded is a list of gate functions (`GATES`: owner, alive, has the trait). Add or remove gates to change the rules.
- `move`: args `{"ids": [...], "target": [x, y]}`. Rejects malformed args, unknown keys, bad or too many ids (max 256, duplicates merged), non-finite or out-of-world targets. Pixels that are unknown, not yours, dead, or unable to obey are skipped; if none are left the command is refused (`strict = True` refuses everything on any bad id). Someone else's pixel looks the same as a missing one.
- A valid command only stores an order (`pixel.components["order"] = {"kind": "move", "x", "y", "tick", "issuer"}`) and emits `order_issued`. Nothing consumes the order yet: that is left for you to decide.
- server/server.py: `handle_command` calls `commands.execute`; rejections go back as `command_rejected` with the seq. Accepted commands get no reply until `tick_update.ack` exists (Phase 7).
- `CommandContext` is the one place that knows the simulation's attribute names: `sim.world`, `sim.tick`, `sim.systems.events`, `sim.entity_manager.get(id)`.

### 5.1b Commands split into game/command/
- game/command/command.py: the framework (registry, Command base, gates, helpers, `execute`, `load_commands`). game/command/commands/move.py: the `move` command. `commands/__init__.py` imports every module in that folder (sorted, files starting with `_` skipped), so a new command is just a new file. `execute()` loads them lazily; the server also calls `load_commands()` at startup so a broken command file fails immediately.
- server/commands.py is gone; server/server.py imports `game.command.command`.

### 4.5.1 Tech tree data
- game/tech/tech.py: loads the tech tree from JSON files in game/tech/nodes/ (subfolders allowed; files and folders starting with `_` ignored). Node fields: kind (body, sense, action, reaction; `class` also accepted; may be set once per file), name, description, cost (number or {currency: amount}), requires (prerequisite ids, which is what draws the tree), provides ({traits, props, commands, triggers, effects, structures, resources}), starts_unlocked.
- Every mistake is reported at once with file and node, with did-you-mean hints: bad JSON (line/column), duplicate keys or ids, unknown fields, bad kinds, bad costs, unknown or self requirements, requirement loops, start-unlocked nodes that need locked ones, unknown provide categories. Warnings: provides nothing; start-unlocked node with a cost.
- game/tech/known.py: the names the game defines (commands, triggers, effects), so `provides` entries are checked against real ones. props, traits, structures and resources accept any name for now.
- game/tech/nodes/*.json: a 25-node sample tree (placeholder content) and `_template.json` to copy from.
- check_techtree.py: prints the tree as text by kind and tier and lists all problems. Exit code 1 on errors.
- Not done yet: per-player ownership and buying (must live on the server), the tech tree window and the rest of the GUI.

### 4.5.2 Bottom bar (placeholders)
- game/gui/bar.py: `Bar` draws a bar along the bottom (theme.BAR_HEIGHT) with four buttons (Tech Tree, Resources, Structures, Blueprints) on the left and a stats panel (Score, Pixels) on the right. Buttons do nothing yet: register a function in `bar.handlers["tech"]` etc. to give one a job. Stats show `--` until you fill `bar.stats["score"]` etc.
- game/gui/gui.py: `Gui` owns the Painter and the Bar. `handle_event(event)` returns True when the GUI used the event.
- rendering/renderer.py: `self.gui`; events go to the GUI first (a click on the bar never reaches the camera), and the GUI is drawn after the entities.
- No window, tech tree drawing or purchasing yet; next steps are one window per button.

### 4.5.3 Resizable window, fullscreen, scaling GUI
- rendering/renderer.py: the window is `pygame.RESIZABLE`, starts at most 90% of the desktop size, and cannot be dragged below 640x400. F11 or Alt+Enter toggles fullscreen (restores the old window size when toggled back). `resized()` re-reads the real size and updates `renderer.width/height`, the world and entity renderers' `screen`, and the camera: it calls `camera.resize(w, h)` if the camera has one, otherwise sets whichever of `width`, `height`, `screen_width`, `screen_height`, `viewport_width`, `viewport_height` it has. Resize events are also passed on to the camera.
- gui/gui.py: `gui.scale` follows the window (1.0 at 1800x1000, between 0.7 and 2.0); `gui.px(value)` scales any size. Use it for everything new.
- gui/bar.py: height, buttons, text and margins all scale; the buttons shrink to fit narrow windows so they never run into the stats panel.
- gui/widgets.py: `draw_button` takes an optional `size` for its label (default 26, so nothing else changes).
- Not checked: game/rendering/camera.py and world_renderer.py were never shared with me. If the world doesn't fill a resized window, they probably cache the old size.

### 4.5.4 Tech tree window
- gui/tech_window.py (new): `TechWindow`, a `Window` that draws the tree from game/tech/nodes/*.json with `layout_tree`: one coloured lane per kind (with an owned/total count), one column per tier, arrows from each requirement to what it unlocks. Starting techs show "Unlocked"; the rest show their cost. Hovering a node shows its description, requirements and provides in the strip at the bottom. Drag the background to pan, mouse wheel to scroll (Shift for sideways). The Reload button re-reads the JSON files; if they have mistakes, the window lists them instead of the tree.
- Clicking a node calls `TechWindow.on_node_clicked(node)`, which does nothing yet: buying goes there. "Owned" is just the `starts_unlocked` nodes for now; the real set must come from the server.
- gui/gui.py: `Gui` now manages windows by name (`WINDOWS = {"tech": TechWindow}`). The bar button toggles the window (and is highlighted while it is open), the X button or Esc closes it (Esc closes the top window before it opens the menu), the last clicked window is drawn in front, windows stay above the bar and are pulled back inside when the game window shrinks. Clicks on a window never reach the camera. To add the next window, write a `Window` subclass and add it to `WINDOWS` under its bar button's name.
- gui/bar.py: a button is drawn highlighted while its window is open.
- rendering/renderer.py: events go to the GUI before the renderer's own keys (so Esc closes a window first).
- game.py: `shutdown()` closes all windows.
- The tree is loaded by the client from its own copy of the JSON (no `known` check; use check_techtree.py for that).

### 4.5.5 Structures button removed
- gui/bar.py: the Structures button is gone (deprecated). The bar now has Tech Tree, Resources and Blueprints. The tech JSON `provides` category "structures" is untouched; say if that should go too.

### 4.5.6 Blueprint tray and sidebar
- gui/blueprints.py (new, no pygame): `load_blueprints(folder=None)` reads every `*.json` in game/entity/entities/ (the folder EntityFactory loads from) and returns `(blueprints, problems)`; a file that is not valid JSON or not an object is reported, not fatal. `describe(blueprint)` turns one into sections of (label, value) rows: Overview, Vitals, Movement/Physics/Material, Properties, Needs, Traits (command shows as the list of allowed commands), Inventory, Home, and then any other top-level key under its own heading, so new attributes show up without editing this file.
- gui/bar.py: the Blueprints button expands the bar upward into a tray of cards (colour swatch from the blueprint's sprite colour, name, kind, health/energy). The wheel scrolls the tray sideways. Clicking a card calls `bar.on_select(id)`. The Structures button is gone (see 4.5.5); the Blueprints button is highlighted while the tray is open.
- gui/blueprint_panel.py (new): `BlueprintSidebar`, a panel down the right side (to the top of the bar) with the selected blueprint's name, kind and attributes. It scrolls with the wheel and has an X button. It only shows data; "Drag onto the map to spawn" is a placeholder line.
- gui/gui.py: opens and closes the tray and sidebar. The blueprints are re-read from disk each time the tray opens, so edits to the JSON show up by closing and reopening it. Clicking the selected card again, the X, or Esc closes the sidebar; Esc then closes the tray; the Blueprints button closes both. Windows are kept above the bar and left of the sidebar.
- Blueprints are read from the client's own copy of the files. Player-saved blueprints (Phase 5.5) will need to come from the server.

### 5.2 Place: the player creates a pixel by dragging a blueprint (WORK IN PROGRESS, paused)
Two separate mechanics: `place` is the PLAYER creating a pixel (drag and drop, below). `spawn` is a PIXEL creating another pixel (5.2b). "place" is a working name.
- gui/gui.py: dragging a card out of the blueprint tray (8 px or more) starts a drag; a ghost swatch follows the mouse (red "Drop it on the map" over the bar, sidebar or a window). Letting go over the map adds (blueprint id, screen position) to `gui.drops`. A short press still selects the card. Esc cancels. `gui.notify(text)` shows a short message at the top of the screen.
- rendering/renderer.py: turns drops into world positions (`camera.screen_to_world` if the camera has it, otherwise it inverts `world_to_screen`) and queues them; `take_place_requests()` returns `[(blueprint id, x, y)]`. It also calls `load_sprites(game/entity/entities)` so placed pixels use their blueprint's sprite.
- game.py: `send_places()` sends each request as a `place` command and shows the server's refusal reason with `gui.notify`.
- command/commands/place.py: `place` with args {"blueprint": id, "position": [x, y]}. Needs no pixel and no command trait. The position must be inside the world. A blueprint with "placeable": false is refused. `PLACE_GATES` is where currency and tech-unlock checks go. No limit per player yet. The pixel is created with `systems.spawn_blueprint(definition)`, then its owner and position are set, and it is recorded in `sim.owned`.
- command/command.py: `as_blueprint` (validates a blueprint id: letters, digits, _ and - only, and the file must exist), `CommandContext.load_blueprint` and `CommandContext.spawn` (creates a pixel; shared by `place` and, later, whatever carries out a `spawn` order). simulation.py: `sim.owned` (player id -> pixel ids), `claim`, `owned_ids`.
- server/replication.py (new), server/server.py, server/replica.py, server/client.py: the server now sends each player a `tick_update` (enter / update / leave) for the pixels they own, and `Client.poll()` applies it to `client.entities`. This is the first slice of Phase 7: no distance rules yet, and the 300 starting pixels (no owner) are still not sent.
- Tested with fakes: `place` and `spawn` (good and bad input) and replication, plus the client applying updates. NOT tested: the drag itself, the game.py and renderer wiring, and server.py's replicate call. websockets and msgpack could not be installed here and most of the game's modules are not in this folder.
- Assumption to check: `systems.spawn_blueprint(definition)` must return the new pixel, and setting `pixel.owner` afterwards must be enough.

### 5.2b Spawn: a pixel creates another pixel
- command/commands/spawn.py: `spawn` is now a command for pixels, like `move`. args: {"ids": [pixel ids], "blueprint": id, "target": [x, y] (optional)}. Only pixels you own, that are alive and carry the "command" trait for "spawn" obey (the others are skipped; the whole command is refused if none can). A blueprint with "spawnable": false is refused (`SPAWN_GATES`).
- Like `move`, it only stores an order: `pixel.components["order"] = {"kind": "spawn", "blueprint", "tick", "issuer", "x", "y"}` ("x" and "y" only when a target was given) and emits `order_issued`. Nothing carries it out yet. When a behavior does, it should call `ctx.spawn(definition, pixel.owner, x, y)` and charge the parent the spawn cost (not inventory; the cost itself is still undecided). Give a pixel the ability with `grant(pixel, "spawn")` or `"traits": {"command": {"spawn": true}}` in its blueprint.

### 5.3 Attack
- command/commands/attack.py (new): `attack`, a command for pixels like `move` and `spawn`. args: {"ids": [pixel ids], "target": a pixel id}. Only pixels you own, that are alive and carry the "command" trait for "attack" obey; the others are skipped, and the command is refused if none can. A pixel never attacks itself (it is skipped).
- The target must exist, be alive and be visible; a missing, dead or invisible target all answer "invalid target", so ids cannot be probed. You cannot target your own pixels. Pixels with no owner (neutral) can be attacked. `ATTACK_GATES` holds these checks; add range and "can this player see it" rules there (Phase 7.5). Right now a player can name any living, visible pixel by id, wherever it is.
- Like `move`, a valid command only stores an order: `pixel.components["order"] = {"kind": "attack", "target": id, "tick", "issuer"}` and emits `order_issued`. Nothing carries it out yet: a behavior has to walk into reach, deal damage, and re-check the target each time (it can die or vanish while the order stands). Give a pixel the ability with `grant(pixel, "attack")` or `"traits": {"command": {"attack": true}}` in its blueprint.
- Tested with fake stand-ins (22 checks); the real simulation was not available here.
- The order does not say how to attack. See 5.3b.

### 5.3b Attack methods (collision by default)
- Pixels attack in different ways, so HOW is separate from the `attack` command (which only says WHO). Each way is an attack method: one file in game/command/attack_methods/ (auto-loaded like commands), a subclass of `AttackMethod` with a `name`, decorated with `@attack_method`. It defines `can_attack(ctx, attacker, target, params)` (default: within `reach`), `attack(...)`, and `defaults` (including `cooldown_ticks`). Examples in the docstring: explode (reach = blast radius, hurts everything inside, kills the attacker) and projectile (reach = range, spawns a projectile pixel with `ctx.spawn`).
- game/command/attack_method.py (new): the registry and `attack_step(ctx, attacker, target)`, which a behavior should call once per tick for a pixel holding an attack order. It returns "gone" (drop the order), "approach" (move closer), "waiting" (cooldown) or "hit". The cooldown is per pixel, kept in `components["attack_ready_tick"]`.
- game/command/attack_methods/collision.py (new): melee, the default. Params: `damage` (1.0), `reach` (half a tile), `cooldown_ticks` (10). It lowers the target's health (never below 0) and emits an "attacked" event (attacker, target, amount, method). Whatever already handles health reaching 0 must do the killing; this does not set `alive`.
- Choosing a method: a pixel's "attack" trait, e.g. `"traits": {"attack": {"method": "collision", "damage": 2.0}}`. Everything but "method" overrides the method's defaults. No attack trait means collision with its defaults. This is separate from the "command" trait, which only decides whether the player may order the pixel to attack.
- The attack command skips a pixel whose attack trait names an unknown method ("unknown attack method 'x'"), and `attack_step` treats it as "gone".
- Tested with fake stand-ins (39 checks in total, including a made-up second method plugged in without touching anything else).

### Inventory slots
- Every entity has `slots` (how much it can hold) and `size` (how many slots it takes up when something holds it), set in its blueprint: `"slots": 5, "size": 1`. Defaults: 0 slots, size 1. A bad value (text, negative, a fraction) falls back to the default. entity.py gets `slots`, `size`, `cargo` and `carried_by`; entityFactory.py reads the first two.
- entity/inventory.py (new, imports nothing from the game): all the rules.
  - Resources take slots: one slot holds `stack_size(name)` units (1 unless `STACK_SIZES["grain"] = 10`), so 5 slots hold 5 iron. `add_resource` / `remove_resource` / `transfer_resource` return how much actually moved; a full entity takes nothing. `slots_used`, `slots_free`, `overfull`.
  - Holding entities: `load(item, holders, lookup)` takes the item's `size` in slots from one or more holders, in the order given, all or nothing. A size-20 settlement needs 4 pixels with 5 free slots each (`holders_needed(item, 5)` is 4); a transport with 4 slots carries 4 size-1 pixels. `is_loaded(item)` is true only when carriers cover the whole size; losing a carrier (`release(item, lookup, holder_id)`) makes it not loaded again, and loading more tops it up. `drop_all(holder, lookup)` for when a holder dies. Refused: loading onto itself, onto a dead holder, the same holder twice, or onto something the item holds (no loops).
  - Resources and cargo share the same slots. What a holder holds does not add to its own size (a loaded transport with 4 passengers takes 1 slot on a ship).
  - `check(entities, lookup)` lists problems (over capacity, links only recorded on one side, wrong totals) for tests and audits.
- `cargo` and `carried_by` are lists of [entity id, slots] pairs, so they stay plain data. Only change them through inventory.py.
- gui/blueprints.py: the blueprint sidebar shows a Capacity section (Slots, Size).
- Not done, on purpose, because the code is not here: (1) moving. A structure should only travel when `is_loaded`, and held entities should follow their carriers; whatever moves pixels has to do that. (2) Existing code that writes `entity.inventory[...]` directly bypasses the slot limit; switch it to `add_resource` / `remove_resource`. `Entity.carried()` still returns the total amount, not slots. (3) Whatever saves or sends entities must include `slots`, `size`, `cargo` and `carried_by` (a plain `dataclasses.asdict` does). (4) Commands to load / unload / pick up. (5) Blueprint inventory larger than its slots is not rejected; `overfull` finds it.
- Tested with fake stand-ins (37 checks): resources, stacks, the 4-pixel settlement, uneven carriers, transport with passengers, nesting and loops, the audit, and the blueprint fields.

### 5.3c Transfer: a pixel moves something that already exists
- command/commands/transfer.py: `transfer` is a command for pixels (needs the "command" trait for "transfer"). args: {"ids": [pixel ids], "item": {"resource": name, "amount": n} or {"entity": id}, "from": id (optional), "to": id or [x, y] (optional)}. Resources: exactly one of from/to is a pixel id, the other side is the acting pixel; a point is refused (that is `drop`). Entities: neither given = the acting pixels pick it up together; "to": id = put it on a carrier; "from": id = take it off a carrier (hand-over if no "to"); "to": [x, y] = set it down there.
- Every entity named must be alive and owned by the player, else the single message "invalid transfer" (ids cannot be probed). `TRANSFER_GATES` is where trading/allies will loosen that. An acting pixel cannot be the item or the other end of its own transfer (skipped). Bad shapes (extra keys, zero or fractional amounts, bool ids, points outside the world, from == to) are refused.
- Like `move`, a valid command only stores `{"kind": "transfer", "item", "from", "to", "tick", "issuer"}` and emits `order_issued`.
- (moved into the transfer behavior in 5.7) `transfer_step`: `transfer_step(ctx, actors, order)`, for whatever will carry orders out. Returns "gone" / "approach" (too far: reach is one tile, or `"traits": {"transfer": {"reach": n}}`) / "blocked" (with the reason, e.g. "it does not fit: it needs 20 slots and 15 are free") / "done". All slot rules stay in entity/inventory.py. A failed hand-over puts the old carriers back exactly.
- Not done: nothing runs the orders yet; carried entities should follow their carriers (and not be moved on their own) in whatever moves pixels; `drop` (5.3d) is separate.
- Tested with fake stand-ins (57 checks): command validation and refusals, give/take/partial/multi-actor resources, reach, the 4-pixel settlement pickup, hand-over and rollback, passenger boarding and unloading at a point.

### 5.7 Commands become behaviors (pixels can do everything a command orders, on their own)
Every pixel action is now a behavior (a trait with a task, in entity/behavior/behaviors/). A command only turns the player's clicks into that action's data and pins it on the pixel. The same task runs whether the decision system picked the action or the player ordered it.
- New behaviors: `move.py` (goto a spot; sets max_speed), `attack.py`, `spawn.py`, `transfer.py`, and `command.py` (the permission: `"command": {"attack": true}`, one bool param per command; add a line there when you add a command).
- Orders (entity/system/orders.py): an order is `pixel.components["order"] = {"kind": "attack", "target": 7, ...}`; `kind` is the action name and the rest is the Action's data. `follow_orders()` starts it with an infinite score (so no scored action, and not the 1.3x switch margin, can interrupt it), `order_finished()` removes it when the task ends (done or failed), and a newer order replaces the running one. Unknown kinds are dropped (`order_dropped` event). Events: `order_finished` (with status), `order_dropped`.
- entity/system/movement.py: `step_toward()` shared by move, attack and transfer. A pixel with no `max_speed` cannot approach, so its task fails instead of hanging.
- Commands: a pixel now needs the "command" permission AND the behavior of the same name (new `gate_behavior`: "cannot do that"). `SPAWN_GATES` moved into the spawn behavior so self-chosen spawns obey them too. command/transfer_step.py is gone: its logic is in the transfer behavior. `transfer` orders for an entity carry `"with": [all ordered ids]` so pixels lift things together; resources are moved by each pixel alone. `CommandContext.spawn` now calls `Simulation.spawn_pixel`.
- attack behavior params: `method` (checked against the attack-method registry, so a bad method fails at blueprint time), `damage`/`reach`/`cooldown_ticks` (left blank = the method's own default), `sight`, `candidates`. On its own a pixel picks the nearest hostile pixel (alive, visible, other owner) but only scores above 0 if it has an "aggression" need.
- spawn behavior params: `blueprint` (what it makes on its own; blank = nothing), `cooldown_ticks`. On its own it needs a "reproduction" need above 0. The cost is still `pay_spawn_cost()`, a hook that is free until decided. Orders wait out the cooldown (up to 30 s).
- transfer behavior param: `reach`. It has no generator yet, so pixels only transfer when ordered.
- Changes to YOUR files (small; full copies are included): `entity/system/simContext.py` gets `tick`, `spawn`, `get_entity()`, `load_blueprint()`; `entity/system/systemRunner.py` imports orders.py, sets `context.spawn`, calls `follow_orders` at the top of `think()`, `order_finished` in `run_task`, and `context.tick += 1` at the end of `update()`; `simulation.py` gets `spawn_pixel()` and sets `systems.context.spawn`. attack_method.py ignores None params.
- Tested with a real SystemRunner, BehaviorManager, EntityManager and your behavior/task/decision/consideration code, with stand-ins for the files I have not seen (needs, memory, world, entity factory): 55 checks for orders and behaviors, 60 for transfer, 61 for attack (including a group of 4 lifting a settlement, an order beating roam, replacing a running order, cooldowns, and failure paths). Not tested against your real world, needs or entity factory.
- Not done: autonomous `transfer` (what should a pixel do on its own?), `drop`, a `stop`/cancel command, using step_toward() in roam, and a spatial lookup for self-chosen attack targets (it scans all pixels; fine for now, see Phase 9).