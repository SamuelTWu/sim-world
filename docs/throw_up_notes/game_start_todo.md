## Phase 12: Game Start and Hearth Placement

A nation starts the game by placing its **hearth**: the first structure, the heart of its colony. Starter pixels appear around it. The hearth is the nation's anchor: later phases read its position as the nation's home point and territory centre (through the `hearth` tag, never the name). The command keeps the name `place_colony` (it is already in `COMMAND_PHASES`, G.1), and what it places is the hearth.

### 12.1 World start and identity

- [ ] 12.1.1 `Server.start_game()` (called from the `LOBBY_START` handler after validation): freeze `lobby.settings`, build the `World` from seed and generation settings using the same function the client uses, compute the world checksum, set `phase = GENERATING` if generation is async, else go straight on. Store `world_info = {seed, gen, checksum}`.
- [ ] 12.1.2 Messages: server `GAME_STARTING {seed, gen, checksum}`; client `WORLD_READY {checksum}`. The client generates the world, compares to the server checksum locally, and sends `WORLD_READY` with its own checksum. Server: matching checksum marks the client ready; mismatch sends `LOBBY_ERROR world_mismatch` and disconnects that client.
- [ ] 12.1.3 When all connected clients are ready, or `WORLD_READY_TIMEOUT_TICKS` (about 15 s) passes (stragglers are disconnected), set `phase = PLACEMENT`. Broadcast `PHASE {phase}` (there is no placement end time, see 12.2.1).
- [ ] 12.1.4 Preview: purely client-side. When `phase == PLACEMENT` the client renders all terrain without fog (Phase 13). It must not write exploration data. Test `check_start_flow.py::world_ready`: matching and mismatching checksums; mismatch client removed.

### 12.2 Placement phase

- [ ] 12.2.1 During `PLACEMENT`, no player can start playing until they place their hearth. Each client transitions to active gameplay immediately upon placing it. There is no placement timeout: players who place later start later and are disadvantaged by first-come, first-served progression.
- [ ] 12.2.2 Client derives phase state from server messages. No periodic server messages. Resend `PHASE` on reconnect (8.4) with the current phase and the player's placement status.
- [ ] 12.2.3 Per-nation start: when a client places its hearth, transition that nation to active gameplay and broadcast the updated state. Nations that have not placed remain in `PLACEMENT`; there is no global countdown or forced start. `EARLY_START = True`.
- [ ] 12.2.4 Test: placing the hearth immediately activates the placing nation; other nations remain in `PLACEMENT`; no timeout for unplaced nations; a late placement starts that nation only after its own placement; normal commands before placement are rejected with `wrong_phase`.

### 12.3 `place_colony` (places the hearth)

- [ ] 12.3.1 `command/commands/place_colony.py`, registered with `COMMAND_PHASES[place_colony] = {PLACEMENT}`. Params `{x, y}` (int tiles, the hearth's anchor tile). Gates, in order, each returning a distinct error code: `wrong_phase`, `no_nation`, `bounds`, `terrain` (every tile of `hearth_footprint(x, y)` passable and not water, using `tiles_by_name`), `spacing` (Chebyshev distance to every other hearth anchor at least `MIN_COLONY_SPACING`), `limit` (one hearth per nation). Successful placement immediately starts active gameplay for that nation; nations that have not placed remain in `PLACEMENT`.
- [ ] 12.3.2 Order: commands are processed from the single server queue. Sort the commands of one tick by `(player_id)` only if the queue can batch multiple; otherwise arrival order stands. Revalidate spacing and terrain immediately before commit (the gates above run inside the commit function). The first valid placement at a contested location wins; slower players must place elsewhere if the spacing rule prevents their placement.
- [ ] 12.3.3 Client preview: `rendering/colony_preview.py` draws the hearth footprint (and a faint ring of the starter-pixel tiles) at the mouse tile, green or red, using the same `hearth_footprint(x, y)` and terrain and spacing checks imported from a shared pure module `world/colony_rules.py` (also used by the server). The server remains authoritative.
- [ ] 12.3.4 Test `check_colony_place.py`: a valid placement starts that nation immediately; water; out of bounds; too close to another hearth; the same tile by two players in one tick (exactly one succeeds); a late command after the nation's own placement; no timeout for unplaced nations; a repeated command by one player after starting is rejected; a failed placement leaves no hearth and no starter pixels.

### 12.4 Hearth and colony creation

- [ ] 12.4.1 `entity/colony.py`: `create_colony(sim, nation, x, y) -> list[int]` is the single creation path. It first creates the hearth: before Phase B, a pixel from a normal `hearth` blueprint (`content/blueprints/hearth.json`: tag `hearth`, a fixed footprint, no behaviors, not commandable, no locomotion); after Phase B, a structure with the same tag and footprint. Then it creates the starter pixels with the existing `place`/spawn path, from blueprint names in a `COLONY_START` table (data, for example `{"hearth": "hearth", "pixels": {"worker": 3}}`), on the free passable tiles around the hearth taken in a fixed order (ring by ring, then by `(y, x)`) so the result is deterministic. All have `owner = nation.player`. Return the created ids (hearth first); record `nation.colony = {"x", "y", "hearth_id", "ids": [...]}`.
- [ ] 12.4.2 Starting resources are granted in `begin_playing()` (12.5), not at placement, using the existing inventory API with amounts from settings. They go into the nation's starting inventory (the hearth's, once structures have inventories). A repeated or repositioned placement therefore never duplicates resources.
- [ ] 12.4.3 Home point: `nation.colony` is the single source for "where is home". `home` goals and the `home` memory (Phase C) read the hearth by its tag through that record, so no behavior file names a hearth position or blueprint.
- [ ] 12.4.4 Test: ids unique, ownership correct, the hearth exists exactly once and carries the `hearth` tag, starter pixels are on distinct passable tiles around it, the nation record matches, replication shows the hearth and pixels to their owner on the next tick, a failed placement leaves no orphan pixels.

### 12.5 Start gameplay

- [ ] 12.5.1 Per-nation start: when a nation successfully places its hearth, immediately run `begin_playing(nation)` for that nation. There is no automatic placement, placement timeout, or forced removal for taking too long. Nations that have not placed remain in `PLACEMENT` until they place.
- [ ] 12.5.2 `begin_playing(nation)`: grant resources to that nation, mark it as `PLAYING`, initialize its fog around the hearth (13.5.2), broadcast `PHASE {phase: "playing"}` for that nation, then let normal replication take over. Make this idempotent (guard against duplicate starts). Other nations remain in `PLACEMENT` until they place.
- [ ] 12.5.3 Test: each nation starts immediately after its own successful placement; resources and fog initialize exactly once; nations that have not placed remain in placement indefinitely; normal commands are rejected before that nation's start; `place_colony` is rejected after that nation starts.

### 12.6 Developer mode

- [ ] 12.6.1 `server/devmode.py`: `DevConfig(skip_wait, placement_ticks, auto_place, reveal)`. Enabled only by a server launch argument or environment variable read in the server entry point (`--dev`). It is never read from any client message and never serialized to clients.
- [ ] 12.6.2 When enabled: `LOBBY_START` ignores ready state; `auto_place_all()` runs immediately if `auto_place` and places each nation's hearth at a deterministic spread of valid tiles. These call the same functions as the normal flow.
- [ ] 12.6.3 Privileged commands live in a separate registry `DEV_COMMANDS` (`dev_spawn`, `dev_grant`), dispatched only if `server.dev is not None`; otherwise `unknown_command`. Test: with dev off, dev commands are rejected and normal flow is unchanged; no client message can set `server.dev`.

### 12.7 End to end

- [ ] 12.7.1 `check_start_flow.py`: 3 clients lobby, ready, start, checksum, hearth placement, a nation that has not placed staying in placement, playing. Disconnects at lobby, placement and generation. Simultaneous placement. Dev mode fast path. Assert that all clients see the same `phase`, hearth positions, ownership and starting resources.