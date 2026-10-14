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

- [] G.1 **Game phase.** Create `server/phase.py`:
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
- Colony can be repositioned until the timer ends.
- Host leaving transfers host to the earliest joiner.
- Clients hold the full generated terrain; fog hides entities and changes, not the base terrain.
- Projectiles have no height axis initially.