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