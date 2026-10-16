# Sim World: Project Structure

Short orientation for a person or for Claude. Last updated 2026-10-15.

## 1. Basics

- Python game, run from the repo root with `python -m src.simworld.__main__`. The package is imported as `src.simworld`.
- Singleplayer starts the server as a separate process: `python -m src.simworld.server.server` with the repo root as working directory (`server/local.py` builds this command from its own package name, nothing is hardcoded).
- **Always use relative imports** inside the package (`from ..shared import protocol`). Never `from src.simworld...` and never `from simworld...`. Mixing names loads the same file twice under two names, which gives duplicate classes and silent `isinstance` failures.
- Every folder under `src/simworld/` should have an `__init__.py`.

## 2. Layout

```
src/simworld/
├── __main__.py            starts the client (menu)
├── shared/                protocol.py: messages shared by client and server
├── world/                 HOW terrain works (no content definitions here)
│   ├── world.py  generator.py  noise.py  chunks.py  deltas.py  tile.py  tile_types.py  module_loader.py
│   ├── maps/              map.py  map_types.py  map modifiers
│   └── features/          feature.py  feature_manager.py  feature_selection_strategy.py
├── content/               WHAT exists: one file per thing, found automatically
│   ├── tiles/             all tiles, in group folders (ground, liquids, vegetation, ores, built, exotic) + default.py
│   ├── features/          all features, in group folders (biomes, water, landmarks; folder names may differ)
│   ├── maps/              all environmental maps (height, temperature, wetness, ...)
│   ├── blueprints/        entity definitions as JSON (commander.json, ...)
│   └── tech/              tech tree (tree.py, known.py)
├── sim/                   the authoritative simulation (no pygame)
│   ├── simulation.py  visibility.py
│   ├── core/              system_runner, sim_context, event_bus, counters, activity, transient_events
│   ├── entities/          entity, entity_manager, entity_factory, inventory, transfer_step
│   ├── behaviors/         behavior.py, behavior_manager.py + all behaviors (one file each)
│   ├── commands/          command.py + all player commands (one file each)
│   ├── combat/            attack_method.py + methods/ (all attack methods: collision, ranged, ...)
│   ├── ai/                decision_system, need_system, considerations, task, orders, rules, memory_system, relationship_system
│   ├── perception/        proximity, stimulus
│   ├── navigation/        movement
│   └── territory/         territory, territory_rules
├── server/                networking
│   ├── server.py  local.py  metrics.py
│   └── replication/       interest, replication, chunksync, worldsync, transientsync
└── client/                everything with a screen (only place pygame is used)
    ├── game.py  menu.py
    ├── net/               connection.py, replica.py
    ├── render/            renderer, camera, world_renderer, entity_renderer, selection, hints, sprites, transient_events
    └── ui/                gui, theme, widgets, window, icon, bar, tree_layout, tech/, blueprint/
```

Also proposed but not confirmed to exist yet: `tests/` (mirrors the source folders, `check_*.py` scripts), `tools/` (dev scripts), `docs/`, `assets/`, `pyproject.toml`.

## In Depth Tree

Repo root:

```
sim-world/
├── README.md 
├── CHANGES.md 
├── pyproject.toml~                 # package metadata, deps (pygame, msgpack, websockets), entry points
├── docs/
│   ├── ARCHITECTURE.md            # layers, import rules, data flow (section 3 of this file, kept up to date)
│   ├── CHECKLIST.md               # implementation checklist (G, 11-13, B, A)
│   ├── phases/                    # phase_C_autonomy.md, phase_T_tile_art.md, future phases
│   └── ART_GUIDE.md               # artist handoff (Phase T)
├── assets/
│   ├── packs/                     # placeholder/, base/ art packs (Phase T)
│   └── fonts/                     # audio/ etc. later
├── saves/                         # gitignored
├── tools/                         # dev scripts (section 5)
├── tests/                         # mirrors src/simworld (section 4)
└── src/simworld/                  # the game (below)
```

The game package (`simworld` is a placeholder; rename freely, nothing else depends on it):

```
src/simworld/
├── __main__.py                    # `python -m simworld` starts the client (from game/main.py)
├── bootstrap.py~                  # load_content(): registers all tiles/features/maps/tech once; used by client and server
│
├── shared/                        # pure, imported by everyone, no pygame
│   ├── protocol.py                # message types, builders, PROTOCOL_VERSION      (from server/protocol.py)
│   └── constants.py               # TILE_SIZE, TICK_RATE, ... collect scattered constants here (new)
│
├── world/                         # HOW terrain works: deterministic, no pygame, used by server AND client
│   ├── world.py   generator.py   noise.py   chunks.py   deltas.py   module_loader.py
│   ├── tile.py    tile_types.py                       # Tile class + registry
│   ├── maps/      map.py  map_types.py  modifiers.py  # environmental map machinery
│   └── features/  feature.py  feature_manager.py  feature_selection_strategy.py │
├── content/                       # WHAT exists: declarative, one file per thing, auto-discovered
│   ├── tiles/                     # all 37 tiles, grouped:
│   │   ├── ground/                #   grass dirt sand sandstone stone gravel clay mud moss ash salt laterite
│   │   │                          #   basalt snow packed_snow ice permafrost            (17)
│   │   ├── liquids/               #   water lava                                         (2)
│   │   ├── vegetation/            #   tree flower                                        (2)
│   │   ├── ores/                  #   coal_ore iron_ore gold_ore                         (3)
│   │   ├── built/                 #   cobblestone concrete iron_block wood_plank stone_brick glass asphalt brick (8)
│   │   ├── exotic/                #   cursed_earth blessed_earth emberstone void_stone   (4)
│   │   └── default.py 
│   ├── features/                  # all 19 features, grouped:
│   │   ├── biomes/                #   arctic taiga tundra temperate_forest grasslands savanna jungle swamp
│   │   │                          #   desert dunes badlands                              (11)
│   │   ├── water/                 #   ocean river beach coral_reef                       (4)
│   │   └── landmarks/             #   volcano stoney_peaks enchanted_glade arcane_wasteland (4)
│   ├── maps/                      # all 8 environmental maps (height, temperature, wetness, fertility, erosion, wind, salinity, magic)
│   ├── blueprints/                # entity definitions as JSON (commander.json, ...)
│   ├── tech/                      # tree.py (was tech.py), known.py
│   └── ...                        # planned: structures/ projectiles/ tasks/ locomotion/ influence/ (JSON or .py, same loader)
│
├── sim/                           # authoritative simulation: headless, server-side only
│   ├── simulation.py              # Simulation: world + managers + runner + bus + seeded RNG
│   ├── visibility.py              # can_see, is_hidden, is_ally, REVEALS   (from command/visibility.py)
│   ├── core/                      # machinery that runs the sim
│   │   ├── system_runner.py  sim_context.py  event_bus.py  counters.py  activity.py  transient_events.py 
│   ├── entities/                  # what pixels are made of
│   │   ├── entity.py  entity_manager.py  entity_factory.py  inventory.py  transfer_step.py 
│   ├── behaviors/                 # all behaviors (build react roam command attack spawn move adapt pickup drop)
│   │   ├── behavior.py  behavior_manager.py  + one file per behavior 
│   ├── commands/                  # all player commands (place attack act spawn move save_blueprint pickup drop edit_property)
│   │   ├── command.py  + one file per command 
│   ├── combat/                    # attack_method.py , methods/ (collision, ranged)       planned: damage.py, projectiles.py
│   ├── ai/                        # decision_system  need_system  considerations  task  orders  rules  memory_system  relationship_system 
│   ├── perception/                # proximity.py  stimulus.py                              planned: sense.py
│   ├── navigation/                # movement.py                                            planned: collision.py flowfield.py regions.py locomotion
│   ├── territory/                 # territory.py  territory_rules.py 
│   └── ...                        # planned: structures/ (structure, structure_manager, build rules, capabilities), scheduler.py
│
├── server/                        # networking and what clients are told
│   ├── server.py                  # connections, tick loop, command intake
│   ├── local.py                   # starts a server for singleplayer
│   ├── metrics.py
│   ├── replication/               # everything about "what does each client know"
│   │   ├── interest.py  replication.py  chunksync.py  worldsync.py  transientsync.py
│   └── ...                        # planned: lobby.py phase.py nations.py fog.py devmode.py structuresync.py
│
└── client/                        # everything with a screen; the only place pygame is allowed
    ├── game.py                    # Game: loop and state machine (menu, lobby, placement, playing)   (from game/game.py)
    ├── menu.py                    # main menu                                                        (from game/menu.py)
    ├── net/
    │   ├── connection.py          # websocket client                                                 (from server/client.py)
    │   └── replica.py             # replicated state the renderer reads                              (from server/replica.py)
    ├── render/                    # (from ui/rendering)
    │   ├── renderer.py  camera.py  world_renderer.py  entity_renderer.py  selection.py  hints.py  sprites.py  transient_events.py
    │   └── ...                    # planned: terrain_renderer.py fog.py structures.py pixel_view.py layers.py art/
    └── ui/                        # (from ui/gui) windows, widgets, editors
        ├── gui.py  theme.py  widgets.py  window.py  icon.py  bar.py  tree_layout.py
        ├── tech/                  # tech_window.py
        └── blueprint/             # catalog.py  blueprint_editor.py  editor_model.py  blueprint_panel.py  blueprints.py
```
### Tests mirror the source
```
tests/
├── run_checks.py                  # (tools/run_checks.py is the same runner) discovers check_*.py, runs each, prints summary
├── architecture/                  check_imports.py   check_renderer_isolation.py
├── shared/                        check_protocol.py
├── world/                         check_noise.py   check_world_checksum.py   check_deltas.py
├── sim/                           check_visibility.py   check_hidden.py   check_activity.py   check_sleep.py
│                                  check_proximity.py   check_rates.py
├── content/                       check_techtree.py   check_known.py        # + future "every tile/feature loads" checks
├── server/                        check_server.py   check_interest.py   check_interest_e2e.py   check_replication.py
│                                  check_reconnect.py   check_quantize.py   check_transient_events.py   check_metrics.py
├── client/                        check_interpolation.py   client_check.py
├── perf/                          check_loadtest.py
└── determinism/                   check_sim_determinism.py   audit_determinism.py
```
### Tools
```
tools/
├── run_checks.py                  # `python tools/run_checks.py [area]` runs all or one area, one-line pass/fail each
├── check_imports.py               # import-boundary enforcement (section 3)
├── run_local.py                   # from test/run_local.py
├── loadtest.py   profile_sim.py   # from test/
├── new.py                         # scaffolding: `python tools/new.py tile lava_rock`, also feature/map/behavior/command
│                                  #   creates the file from a template in the right folder, with a matching check stub
└── art/                           # planned (Phase T): make_placeholder_pack.py, art_preview.py, check_pack.py, make_art_template.py
```
## 3. Where things go

| I want to... | Put it in |
|---|---|
| Add a tile / feature / map | a new file in the matching group folder under `content/` |
| Add or edit a blueprint | `content/blueprints/<id>.json` (file name = blueprint id) |
| Add a behavior / command / attack method | a new file in `sim/behaviors/`, `sim/commands/`, `sim/combat/methods/` |
| Change how terrain generates | `world/` |
| Change what clients are told | `server/replication/` |
| Change what is drawn | `client/render/` (world) or `client/ui/` (windows) |

New content needs no registration code: the folders are scanned automatically (see section 4).

## 4. How things are discovered (loaders)

- **Tiles, features:** `world/tile_types.py` and `world/features/feature_manager.py` use `find_modules()` from `world/module_loader.py`. It scans a content folder and all subfolders for `.py` files (no `__init__.py` needed), sorted by file name across all groups so registration order, and therefore the generated world, stays the same.
- **Maps:** `world/maps/map_types.py` imports every module in `content/maps/` and registers each `Map` subclass.
- **Commands:** `sim/commands/command.py` `load_commands()` imports every file in its own folder except `command.py`; commands register with `@command`.
- **Attack methods:** `sim/combat/attack_method.py` `load_attack_methods()` imports the `methods` package, so `methods/__init__.py` must import its modules.
- **Behaviors:** `sim/behaviors/behavior_manager.py` loads the behavior files in its own folder.
- **Blueprints:** `EntityFactory` (`sim/entities/entity_factory.py`) reads `content/blueprints/`. The client's tray reads the same folder (`client/ui/blueprint/blueprints.py`).

## 5. Dependency rules

Intended direction (imports go down only): `shared` < `world` < `content` < `sim` < `server`; `client` may use `shared`, `world`, `content` but not `sim` or `server`. Pygame only in `client/`.

Current exceptions (known, accepted for now):
- `world/` loads `content/` directly (tile_types, map_types, feature_manager). Target design: content registers itself and the engine never imports it.
- `client/game.py` imports `server/local.py` to start singleplayer, and `local.py` imports `READY_MARKER` from `server.py` (which pulls the whole server module into the client). Target: move `READY_MARKER` to `shared/`, and have `__main__` pass the local-server launcher to the client.

## 6. Code conventions

- No comments, no docstrings in new or rewritten code. Keep it readable and make it look like a human wrote it.
- Prefer longer lines over more lines.
- Relative imports only.

## 7. Changes made since the original proposal

| File | Change |
|---|---|
| `world/maps/map_types.py` | loads maps from `content/maps` via a relative package path |
| `world/features/feature_manager.py` | loads features from every subfolder of `content/features` (any group names), via `find_modules`; imports `feature_selection_strategy` |
| `world/module_loader.py` (new) | `find_modules(package)`: finds `.py` files in all subfolders, sorted by file name |
| `world/tile_types.py` | loads tiles from every subfolder of `content/tiles` via `find_modules` |
| `sim/combat/attack_method.py` | `load_attack_methods` imports `.methods` (was `.attack_methods`) |
| `sim/commands/command.py` | `load_commands` imports all sibling modules except `command.py` (was a `commands` subfolder) |
| `server/server.py` | all imports relative (removed `src.` prefix); `Simulation` import in `main()` too |
| `server/local.py` | launches `-m <package>.server` and derives `ROOT` from the package depth, instead of `-m server.server` with a fixed parent |
| `client/ui/blueprint/blueprints.py` | `DEFAULT_FOLDER` now `content/blueprints` (via `parents[3]`) |
| `sim/entities/entity_factory.py` | `DEFAULT_DEFINITIONS_PATH` now `content/blueprints` (via `parents[2]`); files read as utf-8 |

## 8. Known issues / still to verify

- **All tiles generate as default (last seen, unresolved).** The log showed `features 0.010s`, meaning the feature manager loaded zero features (maps are fine). Likely cause: feature files import `Feature` under a different package name than the one running (for example `simworld...` vs `src.simworld...`), so `issubclass` fails for every class. Check with `grep -rnE "^(from|import) (simworld|src\.simworld)" src` and make them relative. A guard that raises when zero features load is recommended in `_load_features`.
- Tile, feature, map, command and attack-method files may still have old import paths (for example `from ..map import Map`). Fix each as its traceback appears.
- `client/game.py` may still contain `from src.simworld.server.local ...`; make it relative.
- `world/generator.py` imports `.maps.mapModifiers`; confirm the actual file name after the snake_case rename.
- Docstring paths in `command.py`, `attack_method.py` and `blueprints.py` still mention old folders.
- Two files named `replica.py` (`client/net/` and `client/render/`) may duplicate each other; check and merge.
- Not confirmed: whether `pip install -e .` with a `pyproject.toml` has been set up, and whether `tests/` and `tools/` exist.

## 9. Old paths to new paths (for older docs)

The README and the phase checklists use the original names. Translate with:

| Old | New |
|---|---|
| `server/protocol.py` | `shared/protocol.py` |
| `server/client.py`, `server/replica.py` | `client/net/connection.py`, `client/net/replica.py` |
| `server/{chunksync,interest,replication,transientsync,worldsync}.py` | `server/replication/` |
| `ui/rendering/*`, `ui/gui/*` | `client/render/*`, `client/ui/*` |
| `game/{game,menu,main}.py` | `client/game.py`, `client/menu.py`, `__main__.py` |
| `game/simulation.py` | `sim/simulation.py` |
| `game/world/*`, `game/tile/{tile,tile_types}.py` | `world/*` |
| `game/tile/tiles/*`, `game/feature/features/*`, `game/map/maps/*` | `content/tiles/<group>/`, `content/features/<group>/`, `content/maps/` |
| `game/map/*`, `game/feature/*` (machinery) | `world/maps/`, `world/features/` |
| `game/entity/entity.py`, `entityManager.py`, `inventory.py`, `entities/entityFactory.py` | `sim/entities/` (snake_case names) |
| `game/entity/entities/*.json` | `content/blueprints/` |
| `game/entity/behavior/**` | `sim/behaviors/` |
| `game/entity/system/*` | `sim/core/`, `sim/ai/`, `sim/perception/`, `sim/navigation/`, `sim/territory/` |
| `game/command/commands/*` | `sim/commands/` |
| `game/command/attack_methods/*` | `sim/combat/methods/` |
| `game/command/visibility.py` | `sim/visibility.py` |
| `tech/*` | `content/tech/` |
| planned `rendering/*`, `entity/projectiles.py`, `entity/structure*.py`, `world/collision.py`, `world/flowfield.py` | `client/render/*`, `sim/combat/projectiles.py`, `sim/structures/`, `sim/navigation/collision.py`, `sim/navigation/flowfield.py` |