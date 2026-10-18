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
