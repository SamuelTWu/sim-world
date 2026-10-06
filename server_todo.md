# Sim World Multiplayer
The server owns the truth. Clients generate the same world from a shared seed, render it, and send commands. The only things sent over the network are world changes and entities near the player's own pixels.

Work top to bottom. Each step says WHAT to do and HOW. Don't start a phase until the one above works.

### Decisions (already made)
- Server is authoritative. Clients send commands (intents), never state.
- Transport: WebSockets (works for desktop now, browser later). Library: `websockets` + `asyncio`.
- Encoding: `msgpack`. No pickle, no Python-only formats (keeps other client languages possible).
- Tick rate: 10-20 Hz server, client interpolates.
- World: shared seed + settings, client generates locally, server sends only deltas.
- Entities: server sends only pixels within range of the client's own pixels (+ camera view).
- Bullets and effects are EVENTS ("fired from A to B"), not pixels streamed every tick.
- Ship desktop client first. Keep the web door open (see Phase 12).
- Server is hosted by you (VPS or your own machine). Players never run it.

### Server Files (server/)
- protocol.py: message types + encode/decode. Shared by client and server.
- server.py: connections, fixed tick loop, runs the headless Simulation, broadcasts.
- client.py: network layer + replicated state. The renderer reads from this.
- interest.py: spatial grid, per-client visibility diffing (enter/update/leave).
- deltas.py: world change log `(x, y, new_tile)` grouped by chunk.
- commands.py: validates and applies player intents.

---

## Phase 1: Headless Simulation
Goal: the game runs with no Pygame. Single player still works.

- [X] 1.1 Make a `Simulation` class (new file, e.g. simulation.py) that owns: world, entityManager, systemRunner, eventBus, and one seeded RNG.
      HOW: move the non-rendering parts of game.py into it. It exposes `step(dt)` and nothing about screens.
- [X] 1.2 Remove rendering references from entity.py, entityManager.py, and everything in system/ and behavior/.
      HOW: search those files for `pygame`, `camera`, `sprite`, `image`. Move sprite info to a plain string field (e.g. `sprite_id`) that only the renderer interprets.
- [X] 1.3 Give every pixel a stable unique `id` and an `owner` (player id).
      HOW: a counter in EntityManager. IDs are never reused.
- [X] 1.4 Make pixel state serializable.
      HOW: add `to_dict()` / `from_dict()` on pixel, properties, behaviors, and blueprints. Plain ints/floats/strings/lists only.
- [X] 1.5 Make the tick fixed-step.
      HOW: `Simulation.step()` always advances a constant dt (e.g. 0.05s). The game loop calls it in a loop with an accumulator so rendering FPS doesn't affect simulation.
- [X] 1.6 Route ALL world edits through one function (e.g. `world.set_tile(x, y, tile)`).
      HOW: grep for any direct tile writes outside world generation. Replace them. This function will later append to the delta log.
- [X] 1.7 Replace all unseeded `random` use in the simulation with the Simulation's RNG.
- [X] 1.8 Test: run `Simulation` in a plain script with no Pygame import. Step it 1000 times without errors.

## Phase 2: Determinism + Checksum
Goal: two machines generate the exact same world from the same seed.

- [X] 2.1 Audit world generation (generator.py, noise.py, map*.py, feature*.py).
      HOW: no `hash()` on strings (use `hashlib` or a fixed table), no unseeded `random`, no iteration over sets, no dependence on dict order from external input. Sort anything you iterate. -> 
- [X] 2.2 Write `world.checksum()` that hashes the tile grid (or sampled chunks).
      HOW: `hashlib.sha256` over tile ids in a fixed order.
- [X] 2.3 Test: generate the same seed twice in separate processes, then on a second machine if you can. Checksums must match.-> lol i skipped this
- [X] 2.4 Pin dependency versions (numpy etc.) in requirements.txt.

## Phase 3: Protocol + Transport
Goal: a client connects, gets the seed, and generates a matching world.

- [X] 3.1 Write protocol.py: message types as small dicts with a `type` field, encoded with msgpack.
      Start with: `join`, `welcome` (player id, seed, settings, checksum), `command`, `tick_update`, `world_delta`, `error`.
- [X] 3.2 Write server.py: asyncio WebSocket server, accepts connections, assigns player ids, runs `Simulation.step()` at a fixed rate.
      HOW: one asyncio task for the tick loop, one handler per connection pushing messages into a queue the tick loop drains.
- [X] 3.3 Write client.py network layer: connects, sends `join`, receives `welcome`.
- [X] 3.4 Client generates the world from the seed, compares the checksum, and refuses to continue (with a clear error) if it mismatches.
- [X] 3.5 Test: run server and two clients on your machine. Both show identical terrain.

## Phase 4: Single Player = Local Server
Goal: one code path for everything.

- [X] 4.1 Single player launches the server in a background thread/process on loopback and connects to it like any client.
- [ ] 4.2 Main menu: "Singleplayer" (starts local server) and "Join" (enter address).
- [ ] 4.3 Make the renderer read ONLY from client.py's replicated state, never from the Simulation directly.

## Phase 5: Commands
Goal: players control pixels through the server.

- [ ] 5.1 Write commands.py with a handler per command type. Start with `move` (pixel ids + target).
      HOW: every handler checks that the player owns the pixel IDs, that the target is valid, and ignores or rejects otherwise. Never trust the client.
- [ ] 5.2 Add `spawn` (blueprint id, position). Check currency and unlocks.
- [ ] 5.3 Add `attack`.
- [ ] 5.4 Add click-drop and drag-select recall (from the main TODO list) as commands.
- [ ] 5.5 Add `edit_property` and `save_blueprint` (check currency + tech unlocks).
- [ ] 5.6 Client sends a command, shows an optimistic hint if needed, and corrects when the server state arrives.

## Phase 6: World Deltas
Goal: tile changes sync without resending the world.

- [ ] 6.1 Pick a chunk size (e.g. 16x16 tiles). Use the SAME size for deltas and the interest grid.
- [ ] 6.2 deltas.py: `set_tile` appends `(x, y, tile)` to the log for that chunk.
- [ ] 6.3 On join, send deltas for chunks near the player. As the player moves, send deltas for newly nearby chunks.
- [ ] 6.4 Broadcast new deltas only to clients that can see that chunk.
- [ ] 6.5 Client applies deltas on top of its locally generated world.
- [ ] 6.6 Compaction: if a tile is changed repeatedly, keep only the latest value per tile.
- [ ] 6.7 Test: player A mines/changes a tile, player B (nearby) sees it. Player C (far away) gets it only when moving close.

## Phase 7: Interest Management
Goal: clients only receive pixels near their own pixels.

- [ ] 7.1 interest.py: spatial hash grid of pixels (cell size = chunk size or smaller). Update it when pixels move.
- [ ] 7.2 Per client per tick, compute the set of visible pixel ids: pixels in cells near the client's own pixels + camera view.
- [ ] 7.3 Diff against what the client already knows: send `enter` (full state) for new, `update` (changed fields only) for existing, `leave` for gone.
- [ ] 7.4 Hysteresis: leave radius slightly larger than enter radius so pixels don't flicker at the edge.
- [ ] 7.5 Visibility rules: invisible pixels and spies are not sent to enemies. Do the check here on the server.
- [ ] 7.6 Client keeps a dict of known pixels, adds on enter, patches on update, removes on leave.
- [ ] 7.7 Test: pixel walks in and out of range, with no flicker and no leaked invisible pixels.

## Phase 8: Smoothness
- [ ] 8.1 Client interpolates pixel positions between the last two updates (render ~1 tick behind).
- [ ] 8.2 Quantize data: send positions as small ints, only changed fields, no floats with long decimals.
- [ ] 8.3 Bullets/effects as events: server sends `fired(from, to, type)`, clients animate locally. No bullet pixels streamed.
- [ ] 8.4 Reconnect: client rejoins with its player id and gets a fresh `welcome` + nearby state.

## Phase 9: Performance
Do this when the server tick starts taking too long. Measure first.

- [ ] 9.1 Log tick time and bytes sent per client every few seconds.
- [ ] 9.2 Only simulate chunks near some player.
- [ ] 9.3 Sleep idle pixels. Wake them on events.
- [ ] 9.4 Tiered think rates: distant pixels run decision/need systems less often (e.g. every 5th tick).
- [ ] 9.5 Move bulk movement to numpy arrays (positions, velocities) instead of one Python object per pixel.
- [ ] 9.6 Prefer cheap rules (flocking math, simple state) over a full decision system for simple pixels.
- [ ] 9.7 If still too slow, profile with `cProfile` and consider moving hot loops to numpy/Numba/Cython.

## Phase 10: Persistence + Accounts
- [ ] 10.1 Player ids / simple login (name + token to start).
- [ ] 10.2 Save world: seed + settings + delta log + all pixels (via `to_dict()`).
- [ ] 10.3 Save per-player data: currency, unlocks, blueprints. -> not needed for currency or blueprints, but maybe for drawings?
- [ ] 10.4 Autosave on an interval and on shutdown. Load on startup.

## Phase 11: Desktop Distribution
- [ ] 11.1 Test full flow with a friend over the internet (host server on a cheap VPS, or port-forward your machine).
- [ ] 11.2 Build the client with PyInstaller (or Nuitka) on each OS you support: Windows, Mac, Linux. You must build on the target OS.
- [ ] 11.3 Mac: unsigned apps trigger Gatekeeper warnings. For public release, sign + notarize (Apple Developer account). For friends, tell them to right-click > Open.
- [ ] 11.4 Windows: some antivirus flags PyInstaller builds. Test, and consider code signing for public release.
- [ ] 11.5 Host downloads on itch.io or GitHub Releases.
- [ ] 11.6 Put the server address in a config file so you can change it without a rebuild.

## Phase 12: Web (later, optional)
Keep these true from day one so the web stays possible:
- Transport is WebSockets and encoding is msgpack/JSON (no Python-only formats).
- The client is thin: no game logic, all decisions on the server.

Pick one route when you get here:
- [ ] Route A: Pygame client in browser with pygbag (WebAssembly).
      HOW: restructure the main loop around `asyncio`, verify numpy/msgpack/websockets work in the browser build. Expect slower performance than native.
- [ ] Route B: rewrite the client in JS/TS (Canvas or PixiJS).
      HOW: the server keeps working unchanged. Problem: JS can't easily reproduce your Python world generation bit-for-bit. Add a mode where the server sends terrain chunks instead of relying on the seed.

---

### Performance Notes (reference)
- Server tick time bottlenecks before bandwidth does.
- Fortnite works because: dedicated C++ cloud servers, ~100 players, mostly static world, hitscan or locally simulated bullets, prioritized and quantized updates.
- Your game (thousands of small units) is closer to an RTS. RTS games often use deterministic lockstep (only commands are sent). We are NOT doing that because it needs perfect determinism for the whole simulation, no per-client visibility filtering, and awkward late joins. Stay with authoritative server + interest management.

### Open Questions
- Chunk size?
- Player cap per server?
- How long should the server keep simulating when no players are near an area?
- What does the client show before the server confirms a command?
- Win conditions and match structure (affects persistence and when worlds reset).