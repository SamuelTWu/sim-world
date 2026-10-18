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