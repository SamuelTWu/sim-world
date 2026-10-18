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
