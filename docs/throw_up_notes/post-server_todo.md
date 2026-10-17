# Sim World: Implementation Checklist (post-server)

Same format as the main README: one linear checklist, one item at a time. Each item names the files, signatures, message shapes and the check script to write.

## Working rules (apply to every item)

1. **Inspect before editing.** Open the files named in the item. If a name below does not match the tree (file, function, field), use what exists and say so in one line. Never invent a parallel system.
2. **One item per turn.** Write the code, write its `check_*.py`, tick the README box, add a CHANGES.md entry, send the changed files with SendUserFile.
3. **Server owns state.** Clients send intents only. Every new client-to-server message is validated for phase, ownership, ranges and types before any state changes. Never trust client ids, positions or flags.
4. **Determinism.** Gameplay decisions iterate in sorted-id order. Randomness comes only from the sim's seeded RNG. Same seed plus same command list must give the same state hash.
5. **No pygame on the server side.** Server and sim modules must import without pygame. Rendering reads replicated client state only, never `Simulation`.
6. **Wire format.** msgpack dicts. Add builders next to the existing ones in `server/protocol.py`, bump `PROTOCOL_VERSION` once per phase group, extend the `check_protocol.py` samples. Positions on the wire use `to_wire`/`from_wire`.
7. **Check scripts.** Plain scripts (no pytest), print `all N checks passed`, exit non-zero on failure. Use stand-ins where `msgpack`/`websockets`/`pygame` are missing, as the existing checks do.
8. **No speculative abstractions.** Add a registry, base class or config option only when two callers need it now.
9. **Stay cheap.** Anything that runs per tick must be proportional to what changed or to what is active, never to world size. Add a counter to the server stats for each new per-tick cost.

Existing pieces to reuse (confirm names):
`world/chunks.py` (`CHUNK_SIZE`, `chunk_of_tile`, `chunk_of_point`, `chunks_near`), `world/deltas.py` (`DeltaLog`), `server/chunksync.py` (`ChunkSync`), `server/interest.py` (`SpatialGrid`, `visible_ids`), `server/replication.py` (`diff`, `entity_state`), `command/visibility.py` (`can_see`, `is_hidden`, `is_ally`, `REVEALS`), `entity/system/transientEvents.py` (`emit`, `TransientEventLog`), `server/transientsync.py`, `entity/inventory.py`, `command/commands/place.py` (`PLACE_GATES`), `entity/system` `SystemRunner`, `server/replica.py` (client-side replica), `ServerClock`.

---

## G. Groundwork (do first; later phases depend on it)

- [X] G.1 **Game phase.** Create `server/phase.py`:
  ```python
  LOBBY, PLACEMENT, PLAYING = "lobby", "placement", "playing"
  COMMAND_PHASES = {"place_colony": {PLACEMENT}, "lobby_*": {LOBBY}}   # default for every other command: {PLAYING}
  def allowed(phase: str, command_type: str) -> bool: ...
  ```
  `Server.phase` (default `LOBBY` for hosted games), `Server.phase_tick`. Call `allowed(...)` at the top of `commands.execute`; reject with `COMMAND_RESULT {ok: False, error: "wrong_phase"}`. Existing checks that connect and send commands directly must set `server.phase = PLAYING` in their setup (add a `Server(..., start_phase=PLAYING)` kwarg). Test `check_phase.py`: every command type is rejected outside its phase, accepted inside.
- [ ] G.2 **Nation record.** `server/nations.py`:
  ```python
  @dataclass
  class Nation: id: str; player: str; name: str; color: str; icon: str; colony: dict | None = None
  class Nations: by_player: dict[str, Nation]; def get(player) -> Nation; def for_owner(owner) -> Nation|None
  ```
  Keep `entity.owner` as the player id; nation lookup goes through `Nations`. Nations are created at lobby join with defaults (`f"Nation {n}"`, palette color n). Test: lookup by player and by owner, default uniqueness.
- [ ] G.3 **Command correlation.** Every command message carries `ref` (client int). `COMMAND_RESULT` echoes `ref` and returns `ids` (created entity or structure ids) where relevant. Update `protocol.py`, `client.py` (`send_command` returns the ref, store pending refs) and `check_protocol.py`.
- [ ] G.4 **Scheduler.** If `SystemRunner` cannot run "at tick N" without scanning, add `entity/system/scheduler.py`: a heap of `(tick, seq, callback_name, args)`; `schedule(tick, name, *args)`, `run_due(tick)`. Callbacks are looked up by name in a dict so the heap holds only plain data (saveable). Seq breaks ties deterministically. Test: ordering, same-tick tie order, 10k scheduled items cost near zero on empty ticks.
- [ ] G.5 **Save sections.** Find the current save/load code. Add an extensible top-level dict with `version` and optional sections `structures`, `nations`, `fog`, `projectiles`. Loader ignores missing sections. No pickle; ordinary dicts only. Test: old save loads unchanged.
- [ ] G.6 **State hash helper.** `world/statehash.py`: `state_hash(sim) -> str` (sha1 over sorted entity dicts, tile deltas, and later structures and projectiles, serialized with `msgpack` or `json` with sorted keys). Used by every determinism test.
- [ ] G.7 **Protocol bump to v7.** One bump covers G, 11 and 12. Later phases bump again.

---

## Phase 11: Main Menu and Lobby

### 11.1 Server lobby state

- [ ] 11.1.1 Create `server/lobby.py`:
  ```python
  @dataclass
  class LobbyPlayer: id: str; name: str; ready: bool = False; connected: bool = True
  class Lobby:
      players: dict[str, LobbyPlayer]; host: str | None; settings: dict   # {"seed": int, "gen": {...}}
      def join(pid) -> None; def leave(pid) -> None; def set_ready(pid, v) -> None
      def set_nation(pid, name, color, icon) -> str|None      # returns error code or None
      def set_settings(pid, patch: dict) -> str|None
      def can_start() -> bool;  def snapshot() -> dict
  ```
  Nation data lives in `Nations` (G.2); `Lobby` calls into it. Host is the first joiner. `snapshot()` returns plain dicts and is the only thing sent to clients.
- [ ] 11.1.2 Wire into `Server`: on accepted connection, if `phase == LOBBY` call `lobby.join`; else reply `LOBBY_ERROR game_started` and close. On disconnect call `lobby.leave` and broadcast. Remove partially initialized clients in a `try/finally` around the handshake.
- [ ] 11.1.3 Protocol (`protocol.py`):
  client to server: `LOBBY_SET_NATION {name, color, icon}`, `LOBBY_SET_READY {ready}`, `LOBBY_SET_SETTINGS {seed?, gen?}`, `LOBBY_START {}`.
  server to client: `LOBBY_STATE {players:[{id,name,ready,connected,nation:{name,color,icon}}], host, settings, can_start}`, `LOBBY_ERROR {code, message}`.
  Broadcast the full `LOBBY_STATE` after every accepted change. No deltas.
- [ ] 11.1.4 **Host policy.** If the host leaves, host passes to the earliest remaining joiner (ordered dict). If nobody remains, the server closes (hosted) or stops (local). Broadcast `LOBBY_STATE` with the new host. Test `check_lobby.py` cases: join order, host transfer, last player leaves.

### 11.2 Validation (all in `lobby.py`, pure functions, tested directly)

- [ ] 11.2.1 `valid_nation_name(name, taken)`: strip, 1..24 chars, regex `^[A-Za-z0-9 _'\-]+$`, no leading/trailing spaces, case-insensitive uniqueness against other players' nations, small banned list constant. Return error codes `name_length`, `name_chars`, `name_taken`, `name_banned`.
- [ ] 11.2.2 Colors: choose a server-owned `PALETTE` list and accept an index or exact `#rrggbb` that is in the palette. Reject duplicates with `color_taken`. Icons: `ICONS` list of ids; reject unknown.
- [ ] 11.2.3 Settings: `SETTINGS_SCHEMA = {"seed": (int, 0, 2**31-1), "gen.<field>": (type, min, max), ...}` built from the real `GenerationSettings` fields (inspect them). `set_settings` checks host, phase, key whitelist, type, range; unknown key is an error; apply atomically (all keys valid or none applied).
- [ ] 11.2.4 Ready and start: `LOBBY_SET_READY` any player. `can_start()` = host exists and all connected non-host players ready (policy: host may start only when all others are ready; document in README). `LOBBY_START` host only, phase `LOBBY`, `can_start()`; a second `LOBBY_START` returns `already_started`.
- [ ] 11.2.5 Test `check_lobby.py`: 3 fake clients through the real message handlers; unauthorized settings, bad names, duplicates, disconnect frees name, repeated start, wrong phase. Print the check count.

### 11.3 Client menu and connection

- [ ] 11.3.1 Menu: edit the existing menu module to three buttons `Singleplayer`, `Host Server`, `Join Server`. Menu state machine: `MENU -> CONNECTING -> LOBBY | ERROR(msg) -> MENU`. All buttons disabled in `CONNECTING`.
- [ ] 11.3.2 Local server launcher `server/launcher.py`: `start_local(host="127.0.0.1", port=0) -> LocalServer(port, stop())`. Runs `Server` in a background thread with its own asyncio loop (or a subprocess if the existing server entry point is already a script; follow how `run_server` is currently started). Bind port 0 and read the actual port back. A module-level handle prevents a second local server; `stop()` is idempotent and called on leaving to menu and on exit.
- [ ] 11.3.3 Singleplayer: `start_local` then connect to it as the host. Hosting: same with `0.0.0.0` and a user-supplied port (default constant). Join: parse `host[:port]` (reject empty, bad port), connect with a 5 s timeout.
- [ ] 11.3.4 Errors: map `ConnectionRefusedError`, timeout, DNS failure, protocol mismatch, and `LOBBY_ERROR game_started` to short messages. No tracebacks in the UI. A failed attempt leaves no client thread and no local server running (test with a closed port).
- [ ] 11.3.5 Lobby screen: draw from the latest `LOBBY_STATE` held on the `Client`. Controls send the messages from 11.1.3. Only host sees editable settings and the Start button, others see read-only values. Tutorial popup toggle is local config, never sent.
- [ ] 11.3.6 Test `check_menu_flow.py` (no pygame): drive the menu state machine with a fake connector: success, refused, timeout, double click, mismatch error returns to MENU.

---

## Phase 12: Game Start and Colony Placement

### 12.1 World start and identity

- [ ] 12.1.1 `Server.start_game()` (called from the `LOBBY_START` handler after validation): freeze `lobby.settings`, build the `World` from seed and generation settings using the same function the client uses, compute the world checksum, set `phase = GENERATING` if generation is async, else go straight on. Store `world_info = {seed, gen, checksum}`.
- [ ] 12.1.2 Messages: server `GAME_STARTING {seed, gen, checksum}`; client `WORLD_READY {checksum}`. The client generates the world, compares to the server checksum locally, and sends `WORLD_READY` with its own checksum. Server: matching checksum marks the client ready; mismatch sends `LOBBY_ERROR world_mismatch` and disconnects that client.
- [ ]12.1.3 When all connected clients are ready, or `WORLD_READY_TIMEOUT_TICKS` (about 15 s) passes (stragglers are disconnected), set `phase = PLACEMENT`, `placement_end_tick = tick + PLACEMENT_TICKS`. Broadcast `PHASE {phase, ends_in_ms}`.
- [ ]12.1.4 Preview: purely client-side. When `phase == PLACEMENT` the client renders all terrain without fog (Phase 13). It must not write exploration data. Test `check_start_flow.py::world_ready`: matching and mismatching checksums; mismatch client removed.

### 12.2 Countdown

- [ ]12.2.1 `PLACEMENT_TICKS` config (default 25 s at 20 Hz). During `PLACEMENT`, no player can start playing until they place their colony. Each client transitions to active gameplay immediately upon placing their colony. No placement timeout; players who place later are disadvantaged by first-come, first-served progression.
- [ ]12.2.2 Client derives phase state from server messages. No periodic server messages. Resend `PHASE` on reconnect (8.4) with the current phase and placement status.
- [ ]12.2.3 Per-player start: when a client places their colony, transition them to active gameplay and broadcast the updated state. Players who have not placed remain in `PLACEMENT`; no global countdown or forced start. `EARLY_START = True`.
- [ ]12.2.4 Test: placement immediately activates the placing player; other players remain in `PLACEMENT`; no timeout for unplaced colonies; late placement starts the player only after placement; commands before placement rejected with `wrong_phase`.

### 12.3 `place_colony`

- [ ]12.3.1 `command/commands/place_colony.py`, registered with `COMMAND_PHASES[place_colony] = {PLACEMENT}`. Params `{x, y}` (int tiles). Gates, in order, each returning a distinct error code: `wrong_phase`, `no_nation`, `bounds`, `terrain` (every footprint tile passable and not water, using `tiles_by_name`), `spacing` (distance to every other colony anchor at least `MIN_COLONY_SPACING`, Chebyshev), `limit` (one colony per nation). Successful placement immediately starts active gameplay for that nation; nations that have not placed remain in `PLACEMENT`. No placement timeout.
- [ ]12.3.2 Order: commands are processed from the single server queue. Sort the commands of one tick by `(player_id)` only if the queue can batch multiple; otherwise arrival order stands. Revalidate spacing and terrain immediately before commit (the gates above run inside the commit function). First valid placement at a contested location wins; slower players must place elsewhere if the spacing rule prevents their placement.
- [ ]12.3.3 Client preview: `rendering/colony_preview.py` draws the footprint at the mouse tile, green or red using the same `colony_footprint(x, y)` and terrain/spacing checks imported from a shared pure module `world/colony_rules.py` (also used by the server). The server remains authoritative.
- [ ]12.3.4 Test `check_colony_place.py`: valid placement starts that nation immediately; water; out of bounds; too close to another colony; same tile by two players in one tick (exactly one succeeds); late command after own placement; no timeout for unplaced nations; repeated command by one player after starting is rejected; failed placement preserves any existing colony.

### 12.4 Colony creation

- [ ] 12.4.1 `entity/colony.py`: `create_colony(sim, nation, x, y) -> list[int]` is the single creation path. It uses the existing `place`/spawn path for N starter pixels from blueprint names in a `COLONY_START` table (data), set `owner = nation.player`. Before Phase B exists the colony marker is a pixel from a `colony_hub` blueprint (add it as a normal blueprint). After Phase B it becomes a structure. Return created ids; record in `nation.colony = {"x","y","ids":[...]}`.
- [ ] 12.4.2 Starting resources are granted in `begin_playing()` (12.5), not at placement, using the existing inventory API with amounts from settings. Repositioning therefore never duplicates resources.
- [ ] 12.4.3 Test: ids unique, ownership correct, nation record matches, replication shows the pixels to their owner on next tick, reposition leaves no orphan pixels.

### 12.5 Start gameplay

- [ ]12.5.1 Per-nation start: when a nation successfully places its colony, immediately run `begin_playing(nation)` for that nation. No automatic placement, placement timeout, or forced removal for taking too long. Players who have not placed remain in `PLACEMENT` until they place their colony. First-come, first-served progression means slower players start later and are automatically disadvantaged.
- [ ]12.5.2 `begin_playing(nation)`: grant resources to that nation, mark it as `PLAYING`, initialize its fog (13.5.2), broadcast `PHASE {phase: "playing"}` for that nation, then let normal replication take over. Make this idempotent (guard against duplicate starts). Other nations remain in `PLACEMENT` until they place their colonies.
- [ ]12.5.3 Test: each nation starts immediately after its own successful placement; resources and fog initialize exactly once; nations that have not placed remain in placement indefinitely; normal commands are rejected before that nation's start; `place_colony` is rejected after that nation starts.

### 12.6 Developer mode

- [ ] 12.6.1 `server/devmode.py`: `DevConfig(skip_wait, placement_ticks, auto_place, reveal)`. Enabled only by a server launch argument or environment variable read in the server entry point (`--dev`). It is never read from any client message and never serialized to clients.
- [ ] 12.6.2 When enabled: `LOBBY_START` ignores ready state; `PLACEMENT_TICKS` shortened; `auto_place_all()` runs immediately if `auto_place`. These call the same functions as the normal flow.
- [ ] 12.6.3 Privileged commands live in a separate registry `DEV_COMMANDS` (`dev_spawn`, `dev_grant`), dispatched only if `server.dev is not None`; otherwise `unknown_command`. Test: with dev off, dev commands are rejected and normal flow is unchanged; no client message can set `server.dev`.

### 12.7 End to end

- [ ] 12.7.1 `check_start_flow.py`: 3 clients lobby, ready, start, checksum, placement, timer expiry fallback, playing. Disconnects at lobby, placement and generation. Simultaneous placement. Dev mode fast path. Assert that all clients see the same `phase`, colony positions, ownership and starting resources.

---

## Phase 13: Fog

Design: terrain is generated on the client, so **unexplored** is a render state; the server enforces what *entities and changes* a client receives. Server stores per-nation `explored` (persistent) and `visible` (derived). Preview is the `placement` phase, not data.

### 13.1 Masks and exploration state

- [ ] 13.1.1 `world/bitmask.py`: chunk-local bit storage. `CHUNK_BYTES = CHUNK_SIZE*CHUNK_SIZE//8`. Functions `get(buf, lx, ly)`, `set(buf, lx, ly)`, `clear`, `or_into(dst, src)`, `any_set(buf)`. Pure Python on `bytearray` first; optimize only if measured.
- [ ] 13.1.2 `server/fog.py`:
  ```python
  class NationFog:
      explored: dict[(cx,cy), bytearray]
      count: dict[(cx,cy), array('H')]      # ref counts per tile, CHUNK_SIZE*CHUNK_SIZE
      dirty_explored: set; dirty_visible: set
      def is_explored(tx, ty) -> bool;  def is_visible(tx, ty) -> bool       # visible == count > 0
      def stamp(tx, ty, r, sign) -> None  # sign=+1/-1; on 0->1 set explored bit, mark dirty
  class Fog: nations: dict[nation_id, NationFog]; sources: dict[entity_id, (nation_id, tx, ty, r)]
  ```
  `visible` is derived from `count`, not stored separately. Precompute `DISC[r]` offset lists once.
- [ ] 13.1.3 Test `check_fog.py::state`: stamp then unstamp returns every count to zero; overlap of two sources; explored stays set after unstamp; independence between two nations.

### 13.2 Vision sources and updates

- [ ] 13.2.1 Blueprint field `vision` (tiles; default constant for pixels, structures default 0). `Fog.sync_sources(entities)` is called once per tick after `sim.step()`, next to `grid.sync`. For each owned entity with `vision > 0`, compare its tile and radius with `sources[id]`. If unchanged do nothing. If changed: `stamp(old, -1)` then `stamp(new, +1)`. Removed or dead entities: `stamp(old, -1)` and delete. Iterate in sorted id order. Count work in `stats["fog_stamps"]`.
- [ ] 13.2.2 Line of sight is **off** initially (pure disc). Add later behind a blueprint flag `vision_los`, using the vision-blocking flag from B.4.3.
- [ ] 13.2.3 Test: move a source across chunk boundary (both chunks marked dirty); destroyed source clears visibility but not exploration; 64 sources moving costs under a threshold per tick (record a number).

### 13.3 Server-side filtering

- [ ] 13.3.1 Pixels: in `Server.seen_by`, add the nation layer: a pixel not owned by the viewer is visible only if `fog.is_visible(viewer_nation, tile_of(pixel))` and it passes the existing hidden rules. Interest areas stay the broad phase. `replication.diff` already emits `leave` for ids that drop out; no change there. During `PLACEMENT` skip the fog check (everything visible, but pixels do not exist yet).
- [ ] 13.3.2 Put the same nation check inside `visibility.can_see(viewer, entity)` so `attack`, `act`, `inspect` and `attack_step` inherit it. Add an `is_tile_visible(viewer, tx, ty)` helper in `visibility.py` backed by a module-level hook set by the server (same pattern as `REVEALS`) so the command layer does not import the server.
- [ ] 13.3.3 Terrain deltas: `ChunkSync` sends a chunk's deltas only for chunks the viewer's nation has explored. A tile change in an explored-but-not-visible chunk is not sent. When a chunk transitions not-visible to visible for a nation (watch `dirty_visible`), reset that client's cursor for the chunk to 0 so it receives the full current delta log for that chunk (compaction already bounds it).
- [ ] 13.3.4 Commands that name a tile target (`place`, later `launch`) are rejected with `unexplored` if the target tile is not explored by the nation.
- [ ] 13.3.5 Test `check_fog_leaks.py`: two clients on different nations; decode every message client B receives and assert no entity id belonging to A's out-of-sight pixels appears; hidden tile change not delivered; delivered after sight; `attack` on an unseen enemy rejected.

### 13.4 Fog replication

- [ ] 13.4.1 Protocol: `FOG_UPDATE {chunks: [{c: [cx, cy], e: bytes|None, v: bytes|None}]}` for the receiving client's nation only. `e` is the explored mask when changed, `v` is the visible mask when changed (derive `v` from `count > 0` on send).
- [ ] 13.4.2 Per client: keep `fog_sent: dict[chunk, (e_version, v_version)]`. Each nation chunk has integer versions bumped when its masks change. Send in the replicate step at most every `FOG_SEND_EVERY = 4` ticks, one batched message, at most `MAX_FOG_CHUNKS_PER_MESSAGE = 64` chunks (rest next time).
- [ ] 13.4.3 Join and reconnect: send all explored chunks of that nation (in batches) and then all current visible masks. Never include other nations' data; test by asserting message contents.
- [ ] 13.4.4 Client: `server/replica.py` adds `FogView` with `explored` and `visible` dicts of bytes, `apply_fog_update`. `Client.fog` exposes it. `game.py` passes it to the renderer.
- [ ] 13.4.5 Test `check_fog_sync.py`: initial send, incremental send only dirty chunks, no resend when nothing changed (byte count), reconnect restores.

### 13.5 Preview and transitions

- [ ] 13.5.1 Client rule: `preview = (phase == "placement")`. While true the renderer skips fog and draws all terrain. No exploration writes.
- [ ] 13.5.2 `Fog.init_from_sources()` runs in `begin_playing()`: for each nation stamp all current sources once. Then broadcast `FOG_UPDATE`.
- [ ] 13.5.3 Test: after placement, `explored` contains only colony discs; preview never changed `explored`.

### 13.6 Rendering

- [ ] 13.6.1 `rendering/fog.py` `FogRenderer.draw(surface, camera, fog_view, preview)`. Draw after terrain and entities. Per visible chunk in the camera, cache a per-chunk overlay surface keyed by `(chunk, e_version, v_version)` and rebuild only when the key changes. States per tile: unexplored opaque dark; explored and not visible semi-transparent dark; visible none. Tile-level drawing only inside chunks with any change; use a coarse fill when a chunk is fully unexplored or fully visible.
- [ ] 13.6.2 Hover, selection, tooltips and contextual commands consult `fog_view` and replicated entities only. No hover information for unexplored tiles.
- [ ] 13.6.3 Remembered terrain needs no extra storage because hidden deltas are withheld (13.3.3); the client's tile copy is stale in the correct way. Verify with a test rather than adding a snapshot layer.
- [ ] 13.6.4 Persistence: save `fog.explored` as `{nation_id: {"cx,cy": bytes}}` in the `fog` save section; on load rebuild `count` by `init_from_sources()`.
- [ ] 13.6.5 End-to-end `check_fog_e2e.py`: temporary reveal, independent nations, persistent discovery, moving and destroyed sources, stealth pixels via `REVEALS`, reconnect, performance numbers (visibility ms per tick, FOG bytes per client with 64 sources on a large map).

---

## Phase B: Structures

Structures are records in `StructureManager`, not entities. Data-driven blueprints, own id counter, occupancy dict for O(1) tile queries, per-chunk index for rect queries, chunk-driven replication with change log (like terrain deltas). Passive structures cost nothing per tick.

### B.1 Model

- [ ] B.1.1 `entity/structure.py`:
  ```python
  @dataclass
  class Structure: id: int; bp: str; owner: str|None; x: int; y: int; rot: int; hp: float; state: dict
  def to_dict(s) -> dict;  def from_dict(d) -> Structure
  ```
  `state` holds only ints, floats, strings, lists, dicts (e.g. `{"open": False, "inv": {...}, "prod": {...}}`). Static data is not stored on the instance.
- [ ] B.1.2 Blueprints: add `"kind": "structure"` entries next to pixel blueprints (inspect the blueprint loader; extend it to return `kind`, default `"pixel"`). Fields: `footprint: [[dx,dy],...]` (default `[[0,0]]`), `material`, `max_hp`, `blocks: {"move": true, "projectile": true, "vision": false}`, `requires: {...}`, `cost: {...}`, `salvage: 0..1`, `capabilities: {...}`, `vision`, `tags: [...]`.
- [ ] B.1.3 `entity/structureManager.py`:
  ```python
  class StructureManager:
      structures: dict[int, Structure]; next_id: int
      occupancy: dict[(tx,ty), int]; by_chunk: dict[(cx,cy), set[int]]
      def cells(self, s) -> list[(tx,ty)]            # the ONLY footprint function
      def can_place(self, bp, x, y, rot) -> str|None   # error code or None
      def add(self, bp, owner, x, y, rot) -> Structure
      def remove(self, id, reason) -> Structure|None
      def at_tile(self, tx, ty) -> Structure|None
      def in_chunk(self, c) -> list[Structure]         # sorted by id
      def to_dict(self) -> dict;  def load(self, d) -> None   # load calls the same _register as add
      log: StructureLog   # B.5
  ```
  Ids come from `next_id` (saved), never reused. `_register`/`_unregister` update `occupancy` and `by_chunk` and are the only code that touches them.
- [ ] B.1.4 Footprint rotation: `rotate(dx, dy, rot)` applying `(dx, dy) -> (-dy, dx)` `rot` times, then sorted. Anchor is the (0,0) offset. Unit-test 1x1, 2x1, 3x2 at all four rotations.
- [ ] B.1.5 Wire into `Simulation`: `sim.structures = StructureManager(...)`. Not part of `entity_manager`, not stepped by behaviors.
- [ ] B.1.6 Test `check_structure_model.py` (no pygame): ids never reused after removal, lookup, footprints, rotation, `to_dict`/`from_dict` round trip, removal clears `occupancy` and `by_chunk`, multi-chunk footprint registers in each chunk.

### B.2 Placement and construction

- [ ] B.2.1 Extend `command/commands/place.py`: branch on blueprint `kind`. Structures call `place_structure(sim, player, bp, x, y, rot)` in a new `command/commands/build.py`. Reuse `PLACE_GATES` for ownership, unlock and cost; add structure gates after them: bounds, terrain rules, footprint overlap (`occupancy` and pixel-blocking rules), then commit. Check cost first, spend only at commit, in the same function, so a failure never charges.
- [ ] B.2.2 Rules dispatcher: `RULES = {"terrain": fn, "clear": fn, "adjacent_to": fn}` in `build.py`, each `(world, structures, cells, arg) -> bool`. Blueprint `requires` keys select them. Unknown key is a load-time error.
- [ ] B.2.3 `rot` is clamped to 0..3. Cells always come from `StructureManager.cells`. The client preview imports a pure `cells_for(bp, x, y, rot)` (extract it from the manager so both share it).
- [ ] B.2.4 `remove_structure` command (owner only): `salvage` fraction of cost returned through the inventory API, then `StructureManager.remove(id, "deconstructed")`. Destruction by damage calls `remove(id, "destroyed")` and runs the blueprint `on_destroy` drops through the same drop/spawn helper.
- [ ] B.2.5 Autonomous build: add a `build` action available to pixels with the `Build` tag that calls `place_structure` with the pixel's owner (same pattern as how `attack` behavior calls the attack command). Grammar-based construction is deferred to B.4.9.
- [ ] B.2.6 Conflicts: all placement goes through the single command queue; revalidate occupancy at commit (so the second of two same-tile requests fails with `occupied`).
- [ ] B.2.7 Test `check_structure_place.py`: valid; each rejection code; cost charged exactly once; same-tile double request; removal refund; rotated placement uses rotated cells.

### B.3 Index and collision

- [ ] B.3.1 `world/collision.py`:
  ```python
  @dataclass
  class Hit: t: float; kind: str; ref: int|tuple; x: float; y: float; nx: float; ny: float
  def tile_blocked(sim, tx, ty, mover=None) -> bool
  def segment_hit(sim, p0, p1, ignore=None, mask=("terrain","structure","pixel")) -> Hit|None
  ```
  Terrain: DDA along the segment's tiles using the tile properties already used for movement. Structures: for each DDA tile look up `occupancy`, apply `blocks.projectile` and door-open state. Pixels: `grid.in_rect(bbox)` then exact segment-vs-circle. Smallest `t` wins; ties by `(kind_rank terrain<structure<pixel, id)`.
- [ ] B.3.2 Door and traversal rule in one function `structure_blocks(s, bp, mover, what)`: `bp.blocks[what]` false means no block; door capability with `state["open"]` true means no block; blueprint `passable_for: ["owner"]` allows the owner. Used by movement and projectiles alike.
- [ ] B.3.3 Pixel movement: locate where movement currently checks terrain for a destination tile and call `tile_blocked`. No other movement change.
- [ ] B.3.4 Structure index changes only in `_register/_unregister` (placement, removal, rotation). Add a stats counter `occupancy_lookups`.
- [ ] B.3.5 Test `check_collision.py`: walking into a wall blocked, open gate passable, closed gate blocked, multi-chunk footprint, segment tests across tile boundaries, tie-breaking, a 1 000-structure world where a query touches only a few cells (count lookups).

### B.4 Materials and capabilities

- [ ] B.4.1 Materials: inspect how tile properties are defined; add `world/materials.json` (or extend the existing table) with `hardness`, `flammable`, `opaque`, `permeable`. Blueprints reference a material by name.
- [ ] B.4.2 `entity/system/damage.py`: `apply_damage(sim, ref, amount, source, kind) -> bool` where `ref = ("p", id)` or `("s", id)`. Refactor `attack_methods/collision.py` and `ranged.py` to call it, keeping behavior and existing checks green. Structure hp 0 means `remove(id, "destroyed")`.
- [ ] B.4.3 Collision flags from blueprint `blocks` read by `collision.py` and Phase 13 (`vision`).
- [ ] B.4.4 Destruction reactions: blueprint `on_destroy: [{"drop": "wood", "count": 2}, {"tile": "rubble"}]`. Handler in `structureManager.remove` loop bounded by `MAX_REACTIONS_PER_TICK`; extras queue to the scheduler.
- [ ] B.4.5 Capabilities: `capabilities` dict in blueprint. `StructureManager.caps: dict[str, set[int]]` indexes ids by capability, filled in `_register`. Systems iterate only their set. A structure with no capabilities appears in no set.
- [ ] B.4.6 Doors: command `toggle_door {id}` (owner or permitted). Flip `state["open"]`, emit a change to the structure log. No other recompute.
- [ ] B.4.7 Storage: `state["inv"]` as an `entity/inventory.py` structure. Use the existing transfer function generalized to `ref` endpoints. Do removal and addition in one function with rollback; test by summing totals before and after.
- [ ] B.4.8 Production: capability `producer: {recipe, ticks}`. When inputs are present, `scheduler.schedule(tick + ticks, "produce", id)`. `produce` rechecks inputs, consumes, outputs, reschedules if inputs remain. Cap with `MAX_PRODUCTION_PER_TICK`. Runs with no clients connected.
- [ ] B.4.9 Graph grammars: defer until the grammar code is read; then allow rule right-hand sides to name structure blueprints and call `place_structure`.
- [ ] B.4.10 Test: one blueprint with `storage` + `producer` and no new Python; passive structure count 5 000 gives zero per-tick touches.

### B.5 Replication

- [ ] B.5.1 `server/structuresync.py`: `StructureLog` per chunk like `DeltaLog` (`record(chunk, id, kind, fields)`, one latest entry per id, with seq). Kinds: `add`, `change`, `remove(reason)`. `StructureManager` records on every add/modify/remove.
- [ ] B.5.2 Protocol (v8): `STRUCTURES {enter: [...], update: [{id, ...fields}], remove: [{id, reason}]}`; one message per tick per client when non-empty. `enter` carries full state through `structure_state_for(viewer, s)`.
- [ ] B.5.3 Per client `StructureSync`: per-chunk cursor identical in logic to `ChunkSync`. On chunk becoming near, send `enter` for all structures in the chunk, then only log entries newer than the cursor. Leaving the near area sends nothing (client forgets structures in chunks it no longer keeps; the client computes this from its own view or the server sends `remove` with reason `"far"`; choose `"far"` from the server to keep the client simple). Destruction uses reason `"destroyed"`.
- [ ] B.5.4 Privacy: `structure_state_for(viewer, s)` strips `inv` unless viewer is owner; omits structures where `visibility.is_hidden(viewer, s)` (give `Structure` `.owner`, `.visible`, `.tags` so the existing function works). In `PLAYING` also apply the fog check.
- [ ] B.5.5 Client: `replica.apply_structures(structs, message)` into `dict[id, dict]`; `rendering/structures.py` draws from it. Placement ghost is replaced when the `ref` from `COMMAND_RESULT` (G.3) equals the id arriving; no order matching.
- [ ] B.5.6 Test `check_structure_sync.py`: two clients; enter on approach, damage `update` fields only, door state, destroy `remove` reason, far client gets it only on approach, no traffic for idle structures (byte count zero over 100 ticks), dropped-message recovery by reconnect.

### B.6 Persistence and lifecycle

- [ ] B.6.1 Save section `structures: {next_id, items: [to_dict...]}`; load via `StructureManager.load` after terrain; uses `_register`. Scheduler entries for production are saved with the scheduler data (plain tuples).
- [ ] B.6.2 Lifecycle table in README: item to structure (new id), structure to item (id retired), structure to pixel (new pixel id; store `origin` field), pixel to projectile to pixel (same id). Implement `structure_to_pixel(sim, id)`: unregister first, then spawn pixel, copy owner and inventory.
- [ ] B.6.3 Owner leaves or dies: structures persist, ownership unchanged. No decay logic.
- [ ] B.6.4 Test `check_structure_save.py`: save and reload with open door, damaged wall, partly filled chest, mid-recipe factory; `state_hash` equal before and after.

### B.7 Performance and determinism

- [ ] B.7.1 Stats: structure count, `occupancy_lookups`, structure bytes sent per client, production runs per tick. Log in the existing stats output.
- [ ] B.7.2 Load script `check_structure_load.py`: 5 000 inert walls versus 5 000 active pixels, record tick ms; dense settlement with a wide wall; record numbers in CHANGES.
- [ ] B.7.3 Determinism: run the same seeded command list twice and compare `state_hash`.

### B.8 End to end

- [ ] B.8.1 One script per case, in order: fence, wall (projectile half after Phase A), gate, storage, factory (no clients connected), persistence, visibility, performance. Each uses the real server and fake clients.

---

## Phase A: Projectiles

`ranged.py` (hitscan) and TransientEvents already cover instant shots. Phase A adds objects that travel. No gravity or height axis unless a later item asks for it.

### A.1 Model

- [ ] A.1.1 `entity/projectiles.py`:
  ```python
  @dataclass
  class Projectile:
      id: int; source: int|None; owner: str|None
      x: float; y: float; vx: float; vy: float            # world units, per second
      payload: dict     # {"item":"rock","n":1} | {"pixel":id} | {"material":"water","n":3}
      motion: dict      # {"drag":0.0,"bounce":0.0,"homing":None}
      impact: dict      # {"damage":5,"penetrate":0,"embed":False,"deposit":None}
      born: int; expires: int; alive: bool = True; preset: str = ""
  ```
  `to_dict`/`from_dict`. Own id counter on `ProjectileSystem` (saved).
- [ ] A.1.2 `entity/projectileTypes.json`: presets keyed by name giving default `motion`, `impact`, `speed`, `ttl_ticks`, `replicate` (`"event"` or `"state"`), `visual`. Payload material may override `impact` through the materials table (B.4.1). New behavior means a new JSON entry, not a new class.
- [ ] A.1.3 Test `check_projectile_model.py`: round trip, preset lookup, override, no pygame.

### A.2 System and launch

- [ ] A.2.1 `ProjectileSystem` in `entity/projectiles.py`, registered with `SystemRunner`, stepped after pixel behaviors and before `grid.sync`. Keeps `active: dict[int, Projectile]`. Removes dead ones at end of tick.
- [ ] A.2.2 `launch(sim, source_id, payload, origin, direction=None, velocity=None, preset="", owner=None) -> Projectile|None`. Clamp speed to `MAX_SPEED`, range via `ttl`, enforce `MAX_ACTIVE`, `MAX_ACTIVE_PER_OWNER`, `MAX_LAUNCH_PER_TICK`. One function for commands and behaviors.
- [ ] A.2.3 Command `command/commands/launch.py`: `{source, payload_ref, tx, ty}`; gates: phase, owner of source, source alive, cooldown, unlocked, payload present in source inventory. Remove the payload from the inventory and create the projectile inside `launch` after all gates pass.
- [ ] A.2.4 Behavior caller: add a `throw` behavior (or an action in an existing combat behavior) that calls the same `launch`. Only after the command works.
- [ ] A.2.5 Verb separation: keep `spawn`, `transfer`, `drop`, `launch` as separate named functions in one module `entity/objects.py`; `launch` uses the `transfer` removal path. Launching a pixel payload sets `entity.in_flight = projectile.id`, removes it from the grid sync set and skips it in behaviors and `seen_by`.
- [ ] A.2.6 Test `check_launch.py`: valid; each rejection; resource consumed once; thrown pixel is never in two places; caps enforced.

### A.3 Movement and collision

- [ ] A.3.1 Step per projectile: apply drag and homing, compute `p1 = p0 + v*dt`, call `collision.segment_hit(p0, p1, ignore=source)`.
- [ ] A.3.2 On hit: resolve impact in `resolve_impact(sim, p, hit)`: `apply_damage` (B.4.2), `penetrate` count then continue from the hit point with the remaining distance, `bounce` reflect velocity about `(nx, ny)`, `embed` calls `drop`/spawn (A.4), `deposit` calls `world.set_tile` (terrain replication follows from `DeltaLog` automatically), otherwise end. All of it table-driven by `impact` and materials, no weapon names.
- [ ] A.3.3 Friendly rule: skip the source for the first `SELF_HIT_GRACE_TICKS`; target eligibility for pixels uses `visibility.is_ally`/`can_see` only where the preset flags `respect_alliance`.
- [ ] A.3.4 Terminal state: single function `end(p, reason)` sets `alive=False`; nothing reads dead projectiles; end-of-tick purge.
- [ ] A.3.5 Test `check_projectile_collide.py`: fast projectile does not tunnel through a 1-tile wall; two targets in one step, nearer first; tie order; bounce angle; penetrate; deposit changes a tile and records a delta.

### A.4 Transitions

- [ ] A.4.1 `embed`/land: payload `{"item"}` becomes a dropped pixel through the existing spawn path with ownership kept; seeds become their blueprint (plant pixel or structure) if the terrain is valid, else drop as an item.
- [ ] A.4.2 Thrown pixel lands: clear `in_flight`, set position at the stop point (nearest passable tile if blocked), re-add to grid sync; id preserved.
- [ ] A.4.3 Transient payloads (consumed on impact) create no entity. Source death or owner disconnect never cancels flight.
- [ ] A.4.4 Test `check_projectile_land.py`: rock recovered by pick-up, thrown pixel identity preserved, seed grows, no duplicates (count entities before and after).

### A.5 Replication

- [ ] A.5.1 Event class (default): on launch call `emit(sim.transient_events, "projectile", ...)` with start, a predicted end from the same collision query, speed and `visual`; on impact existing `hit` event. Extend `rendering/transient_events.py` `DRAWERS` with `projectile` (draw a moving sprite from start to end over the flight time using `ServerClock`; on a `hit` for the same projectile id snap and remove). Add the projectile id to the event so client can match.
- [ ] A.5.2 State class (`replicate: "state"`): add `projectile_state(p)` and run active state-class projectiles through `replication.diff` with a per-client `known_proj` set, quantized with `to_wire`. Message `PROJECTILES {enter, update, leave}`; client keeps `dict` in the replica; no smoothing beyond the existing pixel code reuse.
- [ ] A.5.3 Filtering: events pass through the existing `transient_events_for`; hide `owner` and `payload` details unless the viewer is the owner or `can_see` the source.
- [ ] A.5.4 Clients draw only. Hits and damage come from the server.
- [ ] A.5.5 Test `check_projectile_sync.py`: near client gets launch and impact events, far client none, hidden source not leaked, state-class projectile enter/update/leave.

### A.6 Performance and determinism

- [ ] A.6.1 Stats: active projectiles, segment tests per tick, events per tick, bytes per client. Burst test: 2 000 launches in one tick are capped by A.2.2 and tick time stays bounded.
- [ ] A.6.2 No arrays or compiled code unless a measurement shows the projectile step above 10% of the tick.
- [ ] A.6.3 Determinism test: replay the same seeded launches twice; `state_hash` (tiles, hp, projectile list) must match.

### A.7 End to end

- [ ] A.7.1 Scripts for: thrown rock and recovery, water/sand terrain deposit, seed embed and growth, bullets against pixels and structures, invalid launches, burst, multiplayer visibility, deterministic replay, adding a new preset in JSON only.

---

## Order

G, then 11, 12, 13, then B (B.1, B.2, B.5 first, then B.3, B.4), then A (needs `segment_hit`), then the end-to-end items in B.8 and A.7 that need both.

## Decisions already assumed (change them if wrong)

- Structure ids and pixel ids use separate counters; wire references carry a kind (`"p"` or `"s"`).
- Host leaving transfers host to the earliest joiner.
- Clients hold the full generated terrain; fog hides entities and changes, not the base terrain.
- Projectiles have no height axis initially.




---

### Edits to the rest of the checklist

**Order** (replace the existing line):

G, then 11, 12, 13, then B (B.1, B.2, B.5 first, then B.3, B.4), then A (needs `segment_hit`), then C (needs G.4, B.1, B.3, 13.1; C.4 to C.9 after B.3, C.10 and C.14 after C.3 to C.9), then the end-to-end items in B.8, A.7 and C.14 that need everything.

**Decisions already assumed** (append):

- Pixels have no hard collision; separation is steering only.
- Field invalidation rebuilds demand-limited fields in a back buffer instead of repairing them incrementally.
- Existing presets default to `autonomy: "none"`; wild and CPU blueprints opt in with `"full"`.
- Boarding and riding (a pixel controlled by another pixel, a carrier overriding the rider's locomotion) is deferred; `profile_of(entity)` is the only hook it needs.
- A.2.4's `throw` behavior is implemented as a task definition once C.3 exists.

## Phase T: Tile and Sprite Art Pipeline

Goal: a client-side art pipeline that looks like a shipped indie game and lets an artist plug in work without touching code. Dual-grid terrain edges, priority-based layering of any number of terrains, stable-hash variation (no visible repeats), animation, user-importable packs, pixel-perfect scaling, and the same pack system for structures and pixel sprites.

Rules for this phase (apply to every item):

1. **Art is data.** No terrain, structure or creature name, and no sprite path, appears in Python. Everything is resolved from pack manifests and file conventions. `check_art_data.py` greps `rendering/` for a banned-word constant list defined in the check itself (`grass water sand stone snow dirt wall tree wolf` and similar) and fails on any hit.
2. **Client only.** The server never reads art. No protocol bump (except the one noted in T.10.1), no save-format change. A blueprint's `appearance.sprite` is an opaque string to the server.
3. **Render from replicated state only** (same rule as the rest of `rendering/`). Terrain comes from the client's tile copy (local generation plus deltas), entities and structures from the replica.
4. **Cosmetic hash, not RNG.** All visual variation uses a pure coordinate hash (T.5.1). It never touches the sim's seeded RNG, never depends on tick, entity id, draw order or iteration order, and never enters `state_hash`. Do not use Python's built-in `hash()` on strings (it is randomized per process).
5. **Pure logic is separate from pygame.** `rendering/tiling.py`, `rendering/variation.py` and `rendering/art/pack.py` must import without pygame, so they are tested headless. Pygame-dependent checks set `SDL_VIDEODRIVER=dummy`; if pygame is missing they print `skipped: pygame missing` and exit 0 (only these).
6. **It always draws something.** Missing or invalid art falls back to the flat tile color from `tile_types`, or a generated placeholder, with one logged warning per missing id. Never an exception in the render loop.
7. **Stay cheap.** Bake once per change. Per-frame cost is proportional to visible chunks, visible animated cells, visible decals and visible entities, never world size. Add a counter for each new per-frame cost to the client stats.

Existing pieces to reuse (confirm names): `rendering/world_renderer.py`, `entity_renderer.py`, `camera.py`, `rendering/structures.py`, `rendering/fog.py` (chunk overlay cache pattern), `rendering/transient_events.py` (`DRAWERS`), `rendering/selection.py`, `world/chunks.py` (`CHUNK_SIZE`, `chunk_of_tile`), `world/tile_types.py`, `server/replica.py` (client tile copy and delta apply), `TILE_SIZE` (32), `ServerClock`, `Nations` colors as replicated to the client.

Dependencies: none on the server. T.1 to T.8 can start any time the renderer is stable and should be finished before any art is commissioned. T.9 needs Phase B (structures). T.10 needs pixel replication of the appearance key (T.10.1). T.12 can be built alongside T.1 to T.4.

### T.1 Packs and manifest

- [ ] T.1.1 **Folder convention (the artist-facing contract).** A pack is a folder containing only PNG and JSON, no code:
  ```
  packs/<pack_id>/pack.json                      # {"format":1,"id","name","tile_size":32,"author","license","tile_map":{...}}
  packs/<pack_id>/terrain/<terrain_id>/terrain.json   # optional; defaults inferred (T.3.1)
  packs/<pack_id>/terrain/<terrain_id>/fill.png       # strip: columns = variants, rows = animation frames (1 row = static)
  packs/<pack_id>/terrain/<terrain_id>/edge.png       # 128x128 dual16 sheet (T.4.4); edge_2.png, edge_3.png = optional variants
  packs/<pack_id>/terrain/<terrain_id>/decals/*.png   # scatter sprites (T.5.5)
  packs/<pack_id>/transitions/<upper>__<lower>/edge.png   # bespoke art for one pair (T.3.4)
  packs/<pack_id>/structures/<bp_name>/...            # T.9
  packs/<pack_id>/entities/<bp_name>/<anim>.png       # T.10
  ```
  Sprite ids are generated from paths: `terrain/<id>/fill`, `entity/<bp>/walk`. `pack.json` may add explicit sheets and aliases, but a pack that only follows the folder convention needs nothing beyond `pack.json` and the PNGs.
- [ ] T.1.2 `rendering/art/pack.py` (pure, no pygame): `load_pack(path) -> Pack`, `merge(packs) -> ArtDB`. Validation returns a list of `(severity, path, message)`; errors never raise into the game. Reject: manifest paths that are absolute or contain `..`, images over `MAX_IMAGE_PX` (4096), a pack whose total decoded size exceeds `MAX_PACK_MB` (128), `tile_size` different from the engine `TILE_SIZE`, unknown manifest keys (warning), `format` newer than supported. Reading PNG headers for dimensions uses a small pure reader so validation needs no pygame.
- [ ] T.1.3 **Pack stack and import.** Config key `art.packs` (ordered list of pack ids, later overrides earlier **per id**, so a user pack can replace only `terrain/grass/fill`). Search order: bundled `assets/packs/`, then the user dir `~/.simworld/packs/` (override with `SIMWORLD_PACKS`). Importing art = dropping a folder into the user dir and listing it in config. Packs are client-local and cosmetic only: no pack data is ever sent to or from the server, and packs are never downloaded from other players.
- [ ] T.1.4 **Placeholder pack.** `tools/make_placeholder_pack.py` generates `assets/packs/placeholder/` deterministically from `tile_types` colors: noisy fill variants (4 per terrain), full dual16 edge sheets with rounded corners, and 2 decals. It follows exactly the folder convention in T.1.1, so it doubles as the reference example for the artist and as the test fixture. It is the default pack; the game must run with only this pack.
- [ ] T.1.5 **Tile to terrain mapping.** `pack.json` `tile_map: {"<tile_type_name>": "<terrain_id>"}`; resolution chain: explicit map entry, then terrain id equal to the tile type name, then terrain id equal to the tile's `surface` attribute (inspect `tile.py` for the stable key), then fallback flat color. Gameplay tile data is never edited for art.
- [ ] T.1.6 **Hot reload.** With `--dev` or `ART_HOT_RELOAD=1`, poll pack file mtimes once per second; on change reload the affected packs, bump the global `art_version` (part of every cache key in this phase), and clear sprite and chunk caches. Errors keep the previous art and log one line.
- [ ] T.1.7 Test `check_art_pack.py`: valid pack loads; each rejection (traversal, oversize, wrong tile size, bad format); per-id override order; tile map chain; unknown terrain falls back without raising; placeholder pack validates with zero errors.

### T.2 Sprite library

- [ ] T.2.1 `rendering/art/sprites.py`:
  ```python
  @dataclass(frozen=True)
  class Frame: surface: pygame.Surface; ms: int
  class SpriteRef:
      id: str; frames: tuple[Frame, ...]; anchor: (int, int); mode: str   # "loop" | "pingpong" | "once"
      def frame_at(self, t_ms: int, phase_ms: int = 0) -> pygame.Surface
  class SpriteLibrary:
      def get(self, id) -> SpriteRef            # never raises; returns MISSING (magenta checker) and logs once
      def get_opt(self, id) -> SpriteRef | None
  ```
  Load PNGs with `convert_alpha()` once, slice sheets into cells, store as immutable surfaces. All scaling in the engine is nearest-neighbor (`pygame.transform.scale`), never `smoothscale`. A static sprite is a `SpriteRef` with one frame, so there is no static/animated code split anywhere downstream.
- [ ] T.2.2 **Sheet addressing.** Strips: columns are variants or frames, rows are animation frames, directions or states, and the meaning is fixed per role in the ART_GUIDE (T.12.5). `fill.png`: columns = variants, rows = animation frames. Entity anims: rows = directions in order `S, W, E, N` (or fewer, T.10.2), columns = frames. Per-sprite JSON (`terrain.json`, `anims.json`) gives `ms` per frame (default 120), `mode`, `anchor` (default bottom-center for entities, top-left for tiles).
- [ ] T.2.3 **Derived-surface caches** (bounded LRU, keyed by `(sprite_id, frame, art_version, params)`): flipped/rotated variants (T.4.4, T.5.2), nation-tinted (T.10.3), hit-flash, hover outline (T.10.4). `SPRITE_CACHE_MB` (default 64); evict LRU; counter `sprite_cache_bytes`.
- [ ] T.2.4 Test `check_sprites.py` (dummy driver): slicing sizes, frame timing and `frame_at` modes, missing id returns the placeholder once with one log line, flip/rotate caches hit on the second call, LRU bound holds.

### T.3 Terrain definitions

- [ ] T.3.1 `terrain.json` (all optional, inferred when absent): `{"priority": 20, "layout": "dual16"|"dual5"|"quad", "allow_rotate": false, "render": "dual"|"block", "ground": "<terrain_id>", "fill": {"weights": [10,4,1], "flip": ["x"], "patches": {...}}, "anim": {"ms": 150, "mode": "loop", "phase": "global"|"tile"}, "edge_variants": 1, "scatter": [...], "tags": []}`. Defaults: layout `dual16` if `edge.png` exists else `quad`; priority from `tile_types` ordering if the pack gives none (log a warning).
- [ ] T.3.2 **Priority is the ordering rule.** Higher priority draws on top of lower at every border, abstractly and for any number of terrains (see T.4.3). Ties break by terrain id string order. No pair-specific ordering code exists; pair-specific art is only an art override (T.3.4).
- [ ] T.3.3 **Layouts.**
  - `dual16`: full 4x4 sheet, one tile per corner mask (T.4.4). Best quality, most art.
  - `dual5`: five shapes (`corner`, `edge`, `diagonal`, `inner`, `full`); the loader derives the other masks by rotation (pre-rotated at load, cached). Only valid with `allow_rotate: true` (the artist confirms lighting is rotation-safe). Cheap art for the artist.
  - `quad`: no edge art; every corner quadrant is cut from the corner tile's own fill sprite, which reproduces an ordinary hard-edged tilemap exactly (and is the correct choice for floors, rooms and "same material, different tint" pairs).
- [ ] T.3.4 **Pair overrides.** `transitions/<upper>__<lower>/edge.png` (and optional `transition.json` with `layout`) replaces the upper terrain's own edge art when `upper` is drawn directly over `lower` (the next lower terrain present in the cell, T.4.3). A pair override with `"layout": "quad"` gives a hard edge between two chosen terrains (for example between two near-identical grasses). Lookup is `overrides.get((upper, lower))`, falling back to the upper terrain's own layout.
- [ ] T.3.5 **Block terrain.** `render: "block"` (rock walls, cliffs, anything drawn as a whole-tile object with a front face) is drawn as single tiles selected by the 4-neighbor connection mask from T.9.2, not by the dual grid. Its dual-grid corner value is its `ground` terrain, so the ground continues underneath and next to it. Front-face and height art for cliffs is deferred (end of phase).
- [ ] T.3.6 Test `check_terrain_defs.py`: inference defaults, priority tie-break, layout validation (`dual5` without `allow_rotate` is an error), pair override lookup, `block` corner value resolves to `ground`.

### T.4 Dual grid core (pure `rendering/tiling.py`)

- [ ] T.4.1 **Geometry and mask bits.** `T = TILE_SIZE`. Tile `(tx,ty)` occupies art pixels `[tx*T,(tx+1)*T) x [ty*T,(ty+1)*T)`. Display cell `(i,j)` is centered on the grid corner `(i*T, j*T)`, covering `[i*T - T/2, i*T + T/2) x [j*T - T/2, j*T + T/2)`. Its four corners are the tiles around that point:
  ```
  TL = tile(i-1, j-1)  bit 1     TR = tile(i, j-1)  bit 2
  BL = tile(i-1, j)    bit 4     BR = tile(i, j)    bit 8
  ```
  Cells run `i in 0..W`, `j in 0..H` (one more than the tile count). Out-of-bounds corner tiles clamp to the nearest in-bounds tile. Tile `(tx,ty)` influences exactly the four cells `(tx..tx+1, ty..ty+1)`. Expose `cell_corners(i, j, terrain_at) -> (t0,t1,t2,t3)` and `cells_of_tile(tx, ty)`.
- [ ] T.4.2 **`dual16` sheet index.** The edge sheet is 4x4, index = `mask` (0..15), row-major (`index = row*4 + col`). Index 0 (no corners) is never drawn. Index 15 (all corners) is unused when a `fill` strip exists. The template generator (T.12.1) labels every cell with its index and shows a four-pip corner diagram so artists cannot misorder it.
- [ ] T.4.3 **Layer list for a cell (the "smart ordering").**
  ```python
  Layer = (terrain_id, mask, layout, lower_id | None)
  def cell_layers(corners4) -> tuple[Layer, ...]:
      present = sorted(set(corners4), key=lambda t: (priority[t], t))     # low to high
      layers = [(present[0], 0b1111, "fill", None)]                       # lowest terrain fills the whole cell
      for k, t in enumerate(present[1:], 1):
          mask = sum(1 << c for c, tid in enumerate(corners4)
                     if (priority[tid], tid) >= (priority[t], t))         # t's own corners AND every higher terrain's
          layout = pair_override(t, present[k-1]) or layout_of[t]
          layers.append((t, mask, layout, present[k-1]))
      return tuple(layers)
  ```
  A layer's mask includes the corners of all higher-priority terrains, so each terrain's edge art sits over the next lower terrain, never over a terrain two levels down (stone-over-sand-over-grass shows sand beside the stone edge, not grass). Draw layers in list order. At most 4 layers per cell; a uniform cell is one layer. Memoize on the 4-tuple of terrain ids (`@lru_cache`); the domain is small.
- [ ] T.4.4 **Sprite selection per layout.**
  - `fill` layer: variant from T.5.2 using cell coordinates.
  - `dual16`: sheet cell `mask` from `edge` (or the `edge_<n>` variant chosen by hash, T.5.2).
  - `dual5`: compute `(base_shape, rot)` programmatically at import by trying all four rotations of each base mask (`corner=0b0001, edge=0b0011, diagonal=0b1001, inner=0b0111, full=0b1111`; rotation maps TL->TR->BR->BL); assert all 15 non-empty masks are covered. Pre-rotated surfaces come from the T.2.3 cache.
  - `quad`: for each corner bit set in the mask, copy that quadrant from the corner tile's own fill sprite (variant chosen by hash of the corner tile's coordinates, i.e. what that tile would pick alone), positioned in the cell's matching quadrant.
- [ ] T.4.5 **Animated cells.** A layer is animated if its sprite has more than one frame row. The selection function returns `(sprite_ref, source_rect, phase_key)` instead of a surface so the baker (T.6) and the animation overdraw (T.7.3) share one code path.
- [ ] T.4.6 Test `check_tiling.py` (pure, headless): corner order and bits for known maps; tile-to-cells mapping; world-edge clamping; `cell_layers` on 2, 3 and 4 terrain cells (expected lists written out by hand), a uniform cell returns one layer, higher-over-lower holds for all 24 orderings of 4 terrains; a stone/sand/grass cell never references grass edge art above sand; `dual5` table covers all 15 masks; `quad` output of an all-same-terrain cell equals the plain tile's pixels (headless via mock surfaces); no pygame import.

### T.5 Variation (no visible repetition)

- [ ] T.5.1 `rendering/variation.py` (pure):
  ```python
  def hash2(x: int, y: int, salt: int) -> int           # 32-bit; murmur/splitmix-style finalizer, no Python hash()
  def salt_of(*parts: str) -> int                        # FNV-1a over utf-8; stable across processes
  def value_noise(x, y, scale: float, salt: int) -> float   # 0..1, smooth, built on hash2 lattice
  ```
  Final salt = `salt_of(terrain_id, purpose)` mixed with the world seed (`art_seed`, from the generation seed) so different worlds differ and different purposes (fill, edge, decal) do not correlate.
- [ ] T.5.2 **Weighted variant pick.** `pick_variant(x, y, weights, salt) -> int` using a cumulative array and `hash2`. Optional flips/rotations per terrain (`"flip": ["x","y"]`, `allow_rotate`) multiply variants for free: `variant_id = (index, flip_x, flip_y)` derived from separate hash bits. Edge sheets pick `edge_<n>` the same way using cell coordinates. Flips are applied through the T.2.3 cache, never per frame.
- [ ] T.5.3 **Neighbor-aware anti-repeat that is edit-stable.** If the raw pick (`hash2(x,y,salt)` mapped to a variant) equals the raw pick of the left or the upper neighbor, re-pick with `salt+1`, then `salt+2`, then keep. Neighbor values are computed from coordinates only, never read from the world, so changing a tile elsewhere can never change another tile's variant.
- [ ] T.5.4 **Macro variation.** `fill.patches`: `{"scale": 24, "sets": [{"above": 0.62, "fill": "fill_b"}]}`; when `value_noise` at the tile is above the threshold use the named alternative fill strip (flower patches, dry patches, mossy stone). Optional brightness bands via `"shade": [{"above": .7, "mul": 1.06}]` applied with a cached tinted surface. This breaks the large-scale repetition that per-tile variants alone cannot.
- [ ] T.5.5 **Scatter decals.** `scatter: [{"sprite": "terrain/<id>/decals/tuft_a", "density": 0.12, "per_tile": 2, "jitter": [-8, 8], "interior_only": true, "z_by_y": false}]`. Per tile and slot `k`: placed if `hash2(x,y,salt+k)/2^32 < density`; sub-tile offset from `hash2(x,y,salt+100+k)`. `interior_only` requires the tile and its 8 neighbors to share the same terrain (no decals across a transition). Decals are **not baked into chunk surfaces** (the half-tile offset of ground surfaces would clip them): each chunk caches a deterministic decal list (sorted by y then x), invalidated with the chunk, and drawn from that list every frame in the pass defined in T.11. Cap with `MAX_DECALS_PER_CHUNK` (default 96). Decals taller than a tile use `z_by_y: true` and go into the y-sorted pass (T.11.2).
- [ ] T.5.6 Test `check_variation.py` (pure): `hash2` and `salt_of` stable across two subprocess runs and across `PYTHONHASHSEED` values; distribution of `pick_variant` matches weights within tolerance over 100x100 tiles; fraction of horizontally and vertically adjacent identical picks is lower than naive hashing (record both numbers in CHANGES); no run of the same variant longer than 6 along any row or column of a 200x200 area; changing a tile's neighbors does not change its variant (edit stability); `interior_only` decals never appear next to a transition; `value_noise` range and smoothness (neighbor difference bound).

### T.6 Chunk baking and cache

- [ ] T.6.1 `rendering/terrain_renderer.py` (`TerrainRenderer`). One opaque ground surface per chunk at **art resolution** (zoom-independent), covering the chunk's display cells `i in [cx*C, (cx+1)*C)`, `j` likewise. Surface origin in art pixels is `(cx*C*T - T/2, cy*C*T - T/2)` and size `(C*T, C*T)`, so adjacent surfaces tile exactly with no overlap and no seams. Chunks on the last column or row add one extra cell so the world's last half-tile is covered; blitting clips to the world rectangle so nothing is drawn outside the map. Bake loop: for each cell, `cell_corners` -> `cell_layers` -> blit each layer's sprite rect.
- [ ] T.6.2 **Dirty tracking.** The client applies tile deltas (replica) through one function; add a hook `terrain_renderer.on_tile_changed(tx, ty)` there and in local terrain generation. A change dirties the chunk of each of the 4 affected cells plus, for decals with `interior_only`, the chunks of tiles within Chebyshev distance 1. Interior tile: 1 chunk; chunk edge: 2; chunk corner: 4. Dirty chunks rebake lazily when next visible.
- [ ] T.6.3 **Budget and fallback.** `BAKE_BUDGET_MS` (default 4) and `BAKES_PER_FRAME_MAX` (default 3) per frame, nearest-to-camera first. A visible chunk not yet baked is drawn as flat per-tile terrain average colors (`avg_color` computed once per terrain at load) so panning never shows holes or hitches. Idle frames pre-bake a ring of `PREBAKE_RING` (default 1) chunks around the camera. Surface cache is LRU bounded by `BAKE_CACHE_MB` (default 96); keys are `(chunk, tile_version, art_version)`.
- [ ] T.6.4 **Overview LOD.** For zoom below 1 (placement preview, zoomed-out map) do not draw sprites: maintain one 1-pixel-per-tile overview surface per chunk from terrain `avg_color`, update it incrementally from `on_tile_changed`, and scale it with nearest-neighbor. Fog and selection are unaffected.
- [ ] T.6.5 Test `check_terrain_bake.py` (dummy driver): a 3x3 chunk world bakes with no transparent pixel in the world area and no seam (surface edge pixels equal the neighboring surface's expected pixels, compared against a brute-force full-world render made cell by cell); a tile edit on a chunk corner dirties exactly 4 chunks, rebake output equals a fresh full bake; world-border cells are clipped; LRU bound; budget respected (counter) and fallback colors drawn while unbaked; `tile_version` change invalidates.

### T.7 Animation

- [ ] T.7.1 `rendering/animation.py`: `RenderClock.now_ms()` from `time.monotonic()` (injectable for tests). Animation never reads sim ticks, never affects gameplay, and keeps running if the sim is slow.
- [ ] T.7.2 **Terrain animation.** `anim.phase: "global"` (all tiles in sync, waves and shimmer) or `"tile"` (per-cell phase offset from `hash2`, grass sway and flicker). Frame index = `(now_ms + phase_ms) // frame_ms % frames` via `SpriteRef.frame_at`. Edge sheets may be animated the same way (shoreline foam): extra rows in `edge.png`.
- [ ] T.7.3 **Static bake plus animated overdraw.** Chunk bakes draw every cell using frame 0 (so there are never holes). Each chunk also stores `anim_cells`: a list of `(cell, layer, sprite_ref, source_rect)` for animated layers only. Every frame, for visible chunks, redraw those cells over the baked surface onto the world surface (T.8). Counter `anim_cells_drawn`. Benchmark this against rebake-on-frame-change in T.13.2 and keep whichever is cheaper; do not build both.
- [ ] T.7.4 **One-shot animation hooks** for pixels and structures use `TransientEvents` (`hit`, `death`, `hurt`, `build`): add `DRAWERS` entries that play a sprite's named anim once (`mode: "once"`) at the event position using `ServerClock` for start time. Replicated state never carries animation frames.
- [ ] T.7.5 Test `check_anim.py` (injected clock): frame at known times for loop, pingpong, once; global versus tile phase; a static terrain has zero `anim_cells`; animated terrain produces exactly its animated cells; no sim access.

### T.8 Pixel-perfect view

- [ ] T.8.1 `rendering/pixel_view.py`. All world content (ground chunks, decals, structures, entities, projectiles) is drawn onto a **world surface at art resolution**, size `(ceil(screen_w / zoom) + 1, ceil(screen_h / zoom) + 1)`, then scaled once with nearest-neighbor into the screen surface (`pygame.transform.scale(src, size, dest)`). `ZOOM_STEPS = (1, 2, 3, 4)` are integers for sprite rendering (mouse wheel steps through them); steps below 1 use the overview LOD (T.6.4). Fractional zoom is not allowed in sprite mode because it causes uneven pixel sizes and shimmering.
- [ ] T.8.2 **Snapping.** The camera position used for rendering is rounded to an integer art pixel. Chunk blits, decals and entity sprites are drawn at integer art-pixel positions; interpolated entity positions are rounded to art pixels at draw time (the interpolation itself stays in float). Sprite anchors are integer pixels.
- [ ] T.8.3 **Draw spaces.** World surface (art resolution): ground, decals, structures, entities, shadows, projectile sprites, selection outlines. Screen space after scaling: fog overlay (tile aligned, existing renderer), health bars, selection boxes, text, UI. Document this table in the renderer module docstring.
- [ ] T.8.4 **Single transform.** `Camera` screen/world conversion (hover tile, click targets, box select) uses the same snapped position and integer zoom as the renderer; add one `world_to_screen` / `screen_to_world` pair used by both. Test that a click at the center of a drawn tile resolves to that tile at every zoom step.
- [ ] T.8.5 Test `check_pixel_view.py` (dummy driver): at zoom 1..4 a 1-pixel marker sprite renders as an exact `zoom x zoom` block; camera sub-pixel movement of 0.4 art pixels does not move the image; screen-to-world and world-to-screen round trip; world surface size formula.

### T.9 Structure art

- [ ] T.9.1 **Manifest and lookup.** Structure sprite id defaults to `structure/<blueprint_name>`; `structures/<bp>/structure.json` (all optional): `{"connect": "<group>"|null, "states": {"open": "door_open", "closed": "door_closed"}, "damage_stages": [0.66, 0.33], "rotations": "rotate"|"sheet", "anchor": [x, y], "z_by_y": true}`. The sprite covers the blueprint footprint; multi-cell structures use one sprite sized to the footprint's bounding box in tiles, aligned to the anchor tile after rotation (use `StructureManager.cells`/`cells_for` for placement so art and collision cannot disagree).
- [ ] T.9.2 **Connection autotile.** `connect_mask4(structure_group_at, tx, ty, group) -> 0..15` (N=1, E=2, S=4, W=8, tiles with the same `connect` group count). Fence/wall/pipe sheets are 4x4 indexed by this mask (same convention doc as dual16). The same function serves `block` terrain (T.3.5). Pure and unit tested; neighbor changes dirty the 4 neighbors' render (structure `update` messages already arrive per chunk).
- [ ] T.9.3 **State selection.** Sprite variant is chosen from replicated structure `state`: `open` (doors), hp fraction against `damage_stages` (cracked sprites), production active (optional anim row). Selection reads only fields that `structure_state_for` already sends; no new replication.
- [ ] T.9.4 **Placement ghost.** The preview from the placement command draws the real sprite at 50% alpha, tinted green or red from the same `cells_for` validity check as the existing preview. Rotation picks the rotated sprite from cache.
- [ ] T.9.5 Test `check_structure_art.py`: `connect_mask4` truth table; rotated 3x2 footprint bounding box and anchor; door state swaps the sprite; hp stages; ghost tint from validity; missing art falls back to a flat footprint rectangle.

### T.10 Pixel (entity) art

- [ ] T.10.1 **Appearance key.** Pixel sprite id defaults to `entity/<blueprint_name>`; a blueprint's `appearance.sprite` overrides it. Confirm what `replication.entity_state` already sends. If the sprite key is not replicated, add it as an enter-only string field (plus an update when `Mutate` changes it) and bump `PROTOCOL_VERSION` once, extending `check_protocol.py` samples. If no sprite exists in the pack, fall back to the existing `Appearance` attribute rendering (color, size, shape), which stays the default for new blueprints.
- [ ] T.10.2 **Animation state from client data only.** `anims.json` names a clip per state: `idle`, `move`, and optional named clips used by transient events (`attack`, `hurt`, `death`, `work`). `move` versus `idle` comes from the interpolated displacement of the last few frames (hysteresis: switch to `idle` only after `IDLE_AFTER_MS` of no movement, default 120). Facing is the last non-zero movement direction quantized to the rows available (`4` rows `S,W,E,N`, `2` rows with `mirror: true` flipping one, or `1` row), held while stationary. No facing or animation field is added to replication.
- [ ] T.10.3 **Nation tint.** `<anim>_mask.png` (white where the nation color applies) is multiplied by the owner's nation color from the replicated nation data and composited over the base frame; result cached per `(sprite, frame, color)` through T.2.3. Sprites without a mask draw unmodified, and the nation color can still appear on the selection ring and minimap.
- [ ] T.10.4 **Overlays.** Ground shadow (blueprint `shadow: {"w": 14, "h": 5}` or a sprite id) drawn under the sprite; hover and selection outline generated from the sprite alpha with `pygame.mask.from_surface(...).outline()` and cached; one-frame white flash on `hurt` events via an additive cached variant (T.2.3). All overlays are drawn only for pixels the client currently sees (fog and stealth already filter the replica).
- [ ] T.10.5 Test `check_entity_art.py` (dummy driver): sprite id resolution order (explicit, then blueprint name, then Appearance fallback); facing quantization for 1, 2 and 4 rows; idle/move hysteresis; tint cache hit; hovering returns an outline sized to the sprite; a pixel whose sprite changes via `Mutate` updates the next frame.

### T.11 Render order

- [ ] T.11.1 One `RenderLayer` enum in `rendering/layers.py`, drawn in this order onto the world surface: `GROUND` (baked chunks plus animated overdraw) -> `GROUND_DECAL` -> `GROUND_STRUCTURE` (floors, flat things) -> `SORTED` (y-sorted structures, tall decals, shadows then pixels) -> `OVERHEAD` (tree canopies, roofs; empty until art uses it) -> `PROJECTILE`. After scaling: fog, then UI. All ordering lives here; no renderer hardcodes another order.
- [ ] T.11.2 **Y-sorting.** `SORTED` items sort by `(y_bottom_art_px, x_art_px, kind_rank, id)` where `y_bottom` is the sprite's anchor line, so draw order is deterministic and stable and a pixel standing in front of a tall structure draws over it, behind it draws under.
- [ ] T.11.3 **Culling.** Only items inside the visible art-pixel rectangle (plus a margin of the largest sprite height) are collected, using the replica's chunk indexes and the client's visible entity set. Counters `items_drawn`, `items_culled`.
- [ ] T.11.4 Test `check_render_order.py`: sort key ties, a pixel above/below a tall structure, `GROUND` never draws above `SORTED`, culling margin keeps a partly visible tall sprite.

### T.12 Tooling and artist handoff

- [ ] T.12.1 `tools/make_art_template.py <terrain_id>`: writes `edge_template_dual16.png` (4x4 grid, each cell labeled with its mask index and a four-pip corner diagram, guides for the half-tile cell geometry) and `edge_template_dual5.png`, plus empty `fill.png` strip templates with the right dimensions. This is the file an artist opens to draw into.
- [ ] T.12.2 `tools/check_pack.py <pack_path>`: runs T.1.2 validation plus art-quality checks: image sizes are multiples of cell size, semi-transparent pixels (warn: pixel art should be hard-edged unless intended), per-sprite color counts, missing roles for every tile type in `tile_types` (list tile types with no terrain art), missing mask cells in `dual16` sheets (index 1..14 empty), unused files, license field present. Exit code non-zero on errors.
- [ ] T.12.3 `tools/art_preview.py <pack_path> [out.png]`: renders a contact sheet using the real renderer: every terrain's fill variants and all 15 edge masks; a **pair matrix map** where every terrain borders every other (straight edges, inner and outer corners, diagonals, 3- and 4-way junctions, 1-tile islands and 1-tile holes) to check priorities and transitions; decals scattered on a 24x24 field; animation strip. Dev-mode key `F6` shows the same map in game.
- [ ] T.12.4 Dev overlays (dev mode only): `F7` draws the dual grid (cell borders and mask numbers), `F8` draws chunk boundaries and baked/dirty state, `F9` shows art counters (bake ms, anim cells, decals, cache MB).
- [ ] T.12.5 `docs/ART_GUIDE.md` (the document you give the artist; generate parts of it from the real constants): tile size and cell geometry with diagrams; folder and file naming (T.1.1); sheet layouts and index tables (T.4.2, T.2.2); recommended counts (4 to 8 `fill` variants with suggested weights, 1 to 2 edge variants, 6 to 12 decals per terrain, 4-frame loops for water); palette and outline guidance; no baked directional lighting when `allow_rotate` is used; hard-edged pixels only; entity sheets (rows `S,W,E,N`, `idle`, `move`, optional `attack`/`hurt`/`death`/`work`, anchor at the feet); structure sheets and connection masks; the placeholder pack as the reference; the `check_pack.py` and `art_preview.py` commands that define "accepted"; license field requirements; a delivery checklist.

### T.13 Performance

- [ ] T.13.1 Client stats: `bake_ms`, `chunks_baked`, `chunks_cached`, `bake_cache_bytes`, `anim_cells_drawn`, `decals_drawn`, `items_drawn`, `sprite_cache_bytes`, `scale_ms`.
- [ ] T.13.2 `check_art_perf.py` (dummy driver, prints numbers, enforces loose bounds only): pan across a 64x64-chunk world at zoom 1, 2 and 4 and record per-frame ms and worst bake spike; 30 animated-water chunks visible with overdraw versus rebake-on-frame-change (keep the cheaper, record both in CHANGES); 2 000 visible pixels with sprites; 5 000 decals. The target is stable 60 FPS on the dev machine at 1080p with the placeholder pack, with no frame over 20 ms during panning.
- [ ] T.13.3 Memory: with `BAKE_CACHE_MB` and `SPRITE_CACHE_MB` at defaults, total art memory stays under 256 MB after a full-map pan (assert from counters).

### T.14 End to end and handoff acceptance

- [ ] T.14.1 `check_art_e2e.py` (dummy driver): start with the placeholder pack; add a second pack that overrides only `terrain/<id>/fill.png` and nothing else; hot reload picks it up with no restart and no code change; a deliberately broken pack leaves the previous art and logs one error; an edit to a tile re-renders correctly across a chunk border; a 12-terrain map with every pair adjacent renders with no hole, no seam and no wrong ordering (compared to a brute-force reference renderer written in the check).
- [ ] T.14.2 **Acceptance for the artist handoff:** a person who has only `docs/ART_GUIDE.md`, the templates and `check_pack.py` can add a new terrain (fill, edge, decals), a structure and an animated pixel to a new pack folder, run the preview tool, and see them in game with zero code edits and zero server changes. Record that you walked through this once and note anything that needed explaining in the guide.

**Deferred, but do not block** (the design leaves room; do not build now): cliff and height faces with `OVERHEAD` fading, a final day/night tint pass over the world surface (the world surface in T.8.1 is the natural place), wind sway as a vertex-style row offset on animated decals, per-biome tint maps, auto-generated edge art from fills, GPU atlasing (keep sprite access behind `SpriteLibrary` so a port touches one module), and pack download or sharing between players.

---

### Edits to the rest of the checklist

**Order** (append):

Phase T is client-only and independent of the server. Do T.1 to T.8 once the renderer is stable (before commissioning art), T.9 after Phase B, T.10 after the pixel appearance key is settled, and T.12 alongside T.1 to T.4 so the artist handoff material exists as early as possible.

**Decisions already assumed** (append):

- `TILE_SIZE` stays 32 and a pack must declare the same `tile_size`; other sizes mean re-authoring, not scaling.
- Sprite mode uses integer zoom only; zoom below 1 switches to a flat-color overview.
- Decals are not baked into chunk surfaces; ground is baked at art resolution with half-tile-offset surfaces.
- Higher terrain priority draws on top; pair-specific art is an override, never special-case ordering.
- Packs are cosmetic and client-local; nothing in a pack is sent over the network.

## Phase 10: Persistence + Accounts
- [ ] 10.1 Player ids / simple login (name + token to start).
- [ ] 10.2 Save world: seed + settings + delta log + all pixels (via `to_dict()`).
- [ ] 10.3 Save per-player data: currency, unlocks, blueprints. -> not needed for currency or blueprints, but maybe for drawings?
- [ ] 10.4 Autosave on an interval and on shutdown. Load on startup. 