# **Phase B: Structures and Persistent World Objects**

## **Goal**

## Implement a lightweight, server-authoritative system for persistent objects such as walls, fences, doors, bridges, storage, factories, and traps. Structures are separate from tiles, pixels, and projectiles. Reuse existing systems wherever possible. Avoid unnecessary abstractions and optimize based on measurements.

### **Decisions (already made)**

## - Tiles represent terrain; structures occupy space above or within terrain.

- Structures are persistent world objects, not ordinary pixels.

- Pixels handle autonomous and mobile behavior.

- Projectiles handle transient movement and impacts.

- Structures share materials, collision rules, inventories, blueprints, and interaction systems where practical.

- The server owns all authoritative structure state.

- Stationary structures must not run unnecessary AI, movement, or per-tick updates.

- Structure definitions are data-driven; do not create a Python class for every structure type.

- Structures use stable unique IDs, ownership, serialization, spatial indexing, and chunk-based replication.

- All authoritative changes must be deterministic and validated by the server.***

## **Phase B.1: Structure Model**

## Goal: create a minimal structure system.* [ ] B.1.1 Create `structure.py` and `structureManager.py`. HOW: follow existing project conventions; implement structure state, creation, lookup, modification, removal, and ID allocation without rendering dependencies.

* [ ] B.1.2 Define structure state. HOW: include only necessary fields such as ID, blueprint ID, owner ID, position, rotation, footprint, and mutable runtime state.

* [ ] B.1.3 Separate definitions from runtime state. HOW: store default properties, material, footprint, collision, and capabilities in blueprint definitions; store current durability, door state, inventory, and other mutable values on instances.

* [ ] B.1.4 Add stable unique IDs. HOW: use a persistent allocation strategy that never reuses IDs and remains safe across save/load and multiplayer operations.

* [ ] B.1.5 Add serialization. HOW: implement `to_dict()` and `from_dict()` using ordinary serializable values; never use pickle or serialize Python object references.

* [ ] B.1.6 Support footprints. HOW: support at least `1x1` and rectangular multi-tile structures with consistent anchor and rotation rules.

* [ ] B.1.7 Test the model. HOW: test IDs, ownership, lookup, footprints, serialization round trips, and removal without importing Pygame.

## **Phase B.2: Placement and Construction**

## Goal: create and remove structures through validated server operations.* [ ] B.2.1 Implement structure placement. HOW: add or extend a command that validates ownership, permissions, technology unlocks, resource costs, terrain compatibility, world bounds, and footprint conflicts before placing anything.

* [ ] B.2.2 Integrate blueprints. HOW: allow blueprints to specify whether they create a pixel or structure; reuse the existing blueprint system.

* [ ] B.2.3 Implement placement rules. HOW: support data-driven requirements such as solid ground, water access, clear space, and compatible materials.

* [ ] B.2.4 Support rotation. HOW: rotate footprints, collision geometry, and visual orientation consistently.

* [ ] B.2.5 Implement removal and destruction. HOW: validate commands server-side and apply configurable material recovery, damage, and destruction outcomes.

* [ ] B.2.6 Integrate autonomous construction. HOW: let pixels with the `Build` capability construct structures using existing graph grammars, material requirements, and construction claims.

* [ ] B.2.7 Prevent construction conflicts. HOW: resolve overlapping placement and construction claims deterministically using existing cooperation and conflict rules.

* [ ] B.2.8 Test placement. HOW: verify valid placement, invalid placement rejection, correct resource costs, concurrent placement requests, and absence of duplicate structures.

## **Phase B.3: Spatial Index and Collision**

## Goal: make structure queries efficient for pixels and projectiles.* [ ] B.3.1 Index structures spatially. HOW: reuse the existing spatial grid where practical and register every occupied cell of a structure's footprint.

* [ ] B.3.2 Update the index incrementally. HOW: update spatial registration only when structures are placed, removed, rotated, or resized; never rebuild the entire index every tick.

* [ ] B.3.3 Unify collision queries. HOW: let collision queries return terrain, structures, and pixels through a shared interface without requiring them to share an entity class.

* [ ] B.3.4 Integrate pixel movement. HOW: prevent movement through blocking structures while supporting configurable traversal rules for doors, gates, bridges, and similar objects.

* [ ] B.3.5 Integrate projectiles. HOW: extend Phase A collision queries to detect structures using swept collision tests and the spatial index.

* [ ] B.3.6 Support impact interactions. HOW: reuse generic material and impact rules for damage, bouncing, penetration, and destruction instead of adding weapon-specific logic.

* [ ] B.3.7 Ensure deterministic collision resolution. HOW: use geometric impact order and stable tie-breaking rules when multiple targets can be hit during a tick.

* [ ] B.3.8 Test collision and indexing. HOW: test movement blocking, open gates, projectile impacts, destruction, and multi-chunk footprints without scanning all structures.

## **Phase B.4: Materials and Capabilities**

## Goal: make structures configurable without hard-coded classes.* [ ] B.4.1 Reuse material definitions. HOW: support relevant properties such as hardness, durability, flammability, opacity, permeability, and impact resistance through existing data-driven systems.

* [ ] B.4.2 Implement durability and damage. HOW: route damage from attacks, projectiles, and environmental effects through shared interaction rules.

* [ ] B.4.3 Implement configurable collision. HOW: support properties such as blocks movement, blocks projectiles, blocks vision, permits fluid flow, and permits climbing.

* [ ] B.4.4 Implement destruction reactions. HOW: support material drops, debris, explosions, and world modification through reusable reactions with bounded processing.

* [ ] B.4.5 Add optional capabilities. HOW: support inventory, storage, production, energy, targeting, and scheduled behavior as optional components; structures without these capabilities must incur no unnecessary processing cost.

* [ ] B.4.6 Implement doors and gates. HOW: store open/closed state and update collision, traversal, and relevant replicated fields when state changes.

* [ ] B.4.7 Integrate inventories. HOW: reuse existing transfer and inventory systems, validating access and preventing item duplication.

* [ ] B.4.8 Integrate production. HOW: process recipes using scheduled updates or events rather than the full pixel decision system.

* [ ] B.4.9 Integrate graph grammars. HOW: allow grammar rules to reference structure definitions, footprints, material requirements, connection rules, and compatibility tags.

* [ ] B.4.10 Test capability combinations. HOW: verify that structures can combine compatible capabilities, such as storage and production, without requiring new Python classes.

## **Phase B.5: Multiplayer Replication**

## Goal: synchronize structures efficiently and securely.* [ ] B.5.1 Define protocol messages. HOW: add messages for structure entry/creation, changed fields, and removal using the existing MessagePack protocol.

* [ ] B.5.2 Integrate interest management. HOW: group structures by occupied chunk and send full state when they become relevant to a client, then only changed fields.

* [ ] B.5.3 Handle newly visible chunks. HOW: send current authoritative structure state when clients enter a region, including changes made while they were away.

* [ ] B.5.4 Handle removal correctly. HOW: distinguish destruction from leaving a client's interest region so clients remove structures for the correct reason.

* [ ] B.5.5 Minimize network traffic. HOW: never resend unchanged positions or properties for stationary structures every tick.

* [ ] B.5.6 Enforce visibility and privacy. HOW: filter private inventories, hidden traps, and restricted properties on the server before replication.

* [ ] B.5.7 Match placement previews to authoritative results. HOW: use stable structure IDs or command correlation rather than matching created structures by arrival order.

* [ ] B.5.8 Keep rendering client-side. HOW: render structures exclusively from replicated client state; never access server-side `Simulation` or `StructureManager` objects from the renderer.

* [ ] B.5.9 Test synchronization. HOW: run multiple clients and verify placement, damage, state changes, destruction, chunk transitions, and missing-update recovery.

## **Phase B.6: Persistence and Lifecycle**

## Goal: preserve structures across saves and support explicit transitions between object types.* [ ] B.6.1 Save structures. HOW: persist IDs, blueprint references, ownership, position, rotation, mutable state, and required capability data.

* [ ] B.6.2 Integrate world loading. HOW: restore terrain and structure definitions before rebuilding structure occupancy and spatial indexes.

* [ ] B.6.3 Define lifecycle transitions. HOW: document transitions between inventory items, structures, pixels, and projectiles; preserve IDs when the same logical object continues to exist and allocate new IDs for newly created objects.

* [ ] B.6.4 Support structure-to-pixel transitions. HOW: transfer relevant state and capabilities explicitly, removing structure occupancy before registering the pixel to prevent duplicate representations.

* [ ] B.6.5 Support persistent projectile impacts. HOW: allow projectiles that land or embed to become recoverable world objects when required; keep short-lived projectiles lightweight.

* [ ] B.6.6 Handle ownership changes and disconnects. HOW: define what happens when owners die, disconnect, or lose control; do not automatically delete persistent structures because an owner leaves.

* [ ] B.6.7 Test persistence. HOW: save and reload structures with inventories, damage, open doors, and production state; verify correct IDs, ownership, and behavior.

## **Phase B.7: Performance and Determinism**

## Goal: support large settlements without making stationary structures expensive.* [ ] B.7.1 Measure baseline performance. HOW: log structure count, query costs, collision checks, tick duration, serialization time, and bytes sent per client.

* [ ] B.7.2 Avoid unnecessary updates. HOW: passive structures must not run pixel movement, needs, perception, relationships, or decision systems.

* [ ] B.7.3 Optimize spatial queries. HOW: profile occupancy lookup and footprint queries before introducing caching or alternative data structures.

* [ ] B.7.4 Bound expensive work. HOW: enforce server-side limits on production rates, inventory sizes, construction claims, and cascading reactions to prevent unbounded work per tick.

* [ ] B.7.5 Optimize replication independently. HOW: measure initial state transfer, update frequency, chunk-boundary traffic, and per-client bandwidth before changing the network architecture.

* [ ] B.7.6 Add load tests. HOW: simulate thousands of structures, dense settlements, large walls, concurrent construction, and heavy projectile impacts; record sustainable counts at the target tick rate.

* [ ] B.7.7 Preserve determinism. HOW: test identical initial worlds and command sequences across repeated runs. Ensure indexing, caching, batching, and optimization changes do not alter authoritative outcomes.

## **Phase B.8: End-to-End Tests**

## Goal: verify that structures work with existing simulation and multiplayer systems.* [ ] B.8.1 Test a fence. HOW: place it, block movement, damage it, destroy it, and recover materials.

* [ ] B.8.2 Test a wall. HOW: block movement and projectiles, apply damage, destroy it, and synchronize all changes across clients.

* [ ] B.8.3 Test a gate. HOW: open and close it and verify collision, traversal, and replication.

* [ ] B.8.4 Test a storage structure. HOW: transfer resources, validate access, save and reload inventory, and verify no duplication.

* [ ] B.8.5 Test a factory. HOW: process resources on schedule without running a full pixel update loop, including when no client can see it.

* [ ] B.8.6 Test graph grammar construction. HOW: build a multi-part structure cooperatively and resolve incompatible construction claims.

* [ ] B.8.7 Test projectile interactions. HOW: launch a rock at a wall and verify deterministic impact, damage, destruction, and material recovery.

* [ ] B.8.8 Test visibility. HOW: verify structures appear when entering a region and private state is never leaked.

* [ ] B.8.9 Test persistence. HOW: restart the server and restore structures, inventories, ownership, and mutable state without duplication.

* [ ] B.8.10 Test performance. HOW: compare the cost of thousands of stationary structures against thousands of active pixels.

## **Completion Criteria**

## - Structures have stable IDs, ownership, footprints, and serialization.

- Placement, modification, and destruction are validated by the server.

- Structures remain separate from terrain tiles and ordinary pixels.

- Pixel movement and projectile collision query structures efficiently.

- Materials and optional capabilities define behavior without one class per structure.

- Passive structures incur no unnecessary per-tick simulation cost.

- Multiplayer replication is chunk-aware, incremental, and privacy-safe.

- Structures survive save/load and remain correct outside client visibility.

- Lifecycle transitions do not duplicate or lose logical objects.

- Determinism, integration, and load tests pass.**Implementation rule:** Inspect the existing codebase before changing files. Reuse existing managers, protocol messages, spatial indexes, inventory systems, blueprint definitions, and interaction rules where practical. Implement one subsection at a time, run its tests, and fix regressions before continuing. Do not rewrite unrelated systems or introduce speculative abstractions without a demonstrated need.-
Writing

# **Phase A: Projectiles**

## Goal

Implement a lightweight, server-authoritative projectile system that lets pixels launch arbitrary objects and materials. Minimize simulation and network costs, support emergent interactions, and allow projectiles to become persistent world objects when needed.

### Decisions (already made)

- The server owns all projectile movement, collision, damage, and gameplay outcomes.
- Projectiles are separate from ordinary pixels and structures.
- Payload, motion, and impact behavior are independently configurable.
- Reuse existing materials, items, properties, commands, and interaction rules.
- Short-lived projectiles use event-driven replication; persistent or unpredictable projectiles receive state updates when necessary.
- Projectiles continue simulating outside player visibility.
- Use the existing fixed timestep, seeded RNG, spatial index, and networking architecture.
- Do not create a separate projectile class for each object type.
- Optimize based on profiling, not assumptions.

## Phase A.1: Projectile Model

Goal: represent projectiles without invoking the full pixel simulation.

- [ ]A.1.1 Create `projectiles.py`. HOW: define a lightweight projectile representation with a unique ID, position, velocity, source ID, owner ID, payload, lifetime, and relevant collision properties.
- [ ]A.1.2 Separate payload from motion. HOW: describe what the projectile carries independently of its trajectory and movement properties.
- [ ]A.1.3 Define impact behavior. HOW: reuse configurable properties and shared interaction rules to determine what happens on collision.
- [ ]A.1.4 Support arbitrary payloads. HOW: allow rocks, seeds, water, sand, bullets, shoes, and existing objects without introducing type-specific projectile classes.
- [ ]A.1.5 Define lifecycle and ownership. HOW: specify ID allocation, owner tracking, expiration, termination, and transitions to and from persistent entities.
- [ ]A.1.6 Test serialization. HOW: ensure projectile state uses ordinary serializable values and supports reliable save/load when persistence is required.

## Phase A.2: Simulation and Launching

Goal: launch projectiles through one reusable server-side operation.

- [ ]A.2.1 Implement `ProjectileSystem`. HOW: register it with `Simulation` and `systemRunner`; use the existing fixed timestep and seeded RNG without rendering dependencies.
- [ ]A.2.2 Implement `launch`. HOW: accept a source, payload, origin, velocity or direction, and applicable properties; use this operation for all projectile types.
- [ ]A.2.3 Validate launch requests. HOW: check ownership, permissions, payload availability, technology unlocks, resource costs, and server-enforced velocity and range limits.
- [ ]A.2.4 Integrate commands and behaviors. HOW: allow player commands and autonomous pixel behaviors to invoke the same launch operation.
- [ ]A.2.5 Preserve object identity. HOW: launching an existing object must transfer it into projectile simulation without duplicating it; define explicit rules for allocating IDs when creating new projectiles.
- [ ]A.2.6 Distinguish object operations. HOW: keep `spawn` for creating objects, `transfer` for moving existing objects, `drop` for materializing inventory into the world, and `launch` for launching objects.
- [ ]A.2.7 Test launch validation. HOW: verify valid launches, rejected commands, resource consumption, ownership checks, and the absence of duplicated payloads.

## Phase A.3: Movement and Collision

Goal: simulate projectiles efficiently and resolve impacts deterministically.

- [ ]A.3.1 Implement fixed-step movement. HOW: update active projectiles using the existing simulation timestep; begin with ballistic movement.
- [ ]A.3.2 Prevent tunneling. HOW: use swept collision tests or continuous collision detection so fast projectiles cannot pass through thin tiles, structures, or pixels between ticks.
- [ ]A.3.3 Reuse spatial indexing. HOW: query nearby collision candidates using existing spatial indexes instead of scanning the entire world for every projectile.
- [ ]A.3.4 Define collision ordering. HOW: resolve impacts by travel distance or time of impact, with stable tie-breaking when multiple targets are hit during the same tick.
- [ ]A.3.5 Support terrain and structures. HOW: detect relevant tile and structure collisions using shared collision interfaces.
- [ ]A.3.6 Support pixel collisions. HOW: query nearby eligible pixels and apply existing ownership, visibility, and targeting rules where relevant.
- [ ]A.3.7 Implement generic impact outcomes. HOW: support damage, bounce, penetration, embedding, momentum transfer, material deposition, destruction, and stopping through reusable properties and interactions.
- [ ]A.3.8 Add optional motion properties. HOW: support configurable gravity, drag, bounce, and homing through shared movement interfaces without requiring every projectile to use every feature.
- [ ]A.3.9 Handle instantaneous attacks. HOW: implement lasers and similar attacks as ray or beam interactions rather than simulating artificial moving projectiles.
- [ ]A.3.10 Test collision behavior. HOW: verify fast impacts, multiple collision candidates, material interactions, bounce, penetration, and deterministic resolution.

## Phase A.4: Object Transitions and Persistence

Goal: allow projectiles to become persistent world objects when necessary.

- [ ]A.4.1 Support pixel-to-projectile transitions. HOW: allow existing pixels to be thrown or launched by transferring them into projectile simulation while preserving their identity and relevant state.
- [ ]A.4.2 Support projectile-to-pixel transitions. HOW: allow projectiles to land, embed, or otherwise become persistent pixels when required; restore their relevant properties and ownership.
- [ ]A.4.3 Handle material impacts. HOW: allow payloads to modify terrain, deposit materials, or create persistent objects through shared world modification and interaction systems.
- [ ]A.4.4 Keep transient projectiles lightweight. HOW: projectiles that disappear on impact must not incur full entity creation, inventory, AI, or persistence costs.
- [ ]A.4.5 Define terminal states. HOW: ensure expired, destroyed, embedded, or otherwise terminated projectiles cannot move, collide, or apply effects again.
- [ ]A.4.6 Handle owner lifecycle. HOW: define behavior when the source pixel dies, its owner disconnects, or the projectile travels outside every client's visibility range.
- [ ]A.4.7 Test transitions. HOW: verify that thrown objects can be recovered, embedded seeds can grow, and persistent objects retain the correct identity without duplication.

## Phase A.5: Multiplayer Replication

Goal: replicate only the projectile information each client needs.

- [ ]A.5.1 Integrate interest management. HOW: determine relevant clients using server-side visibility and interest rules, including projectiles crossing chunk boundaries.
- [ ]A.5.2 Replicate short-lived projectiles as events. HOW: send launch events containing sufficient trajectory and visual information, followed by authoritative impact or termination events.
- [ ]A.5.3 Replicate persistent projectiles selectively. HOW: send quantized snapshots or changed fields when projectiles are steerable, unpredictable, persistent, or otherwise require authoritative state updates.
- [ ]A.5.4 Avoid unnecessary updates. HOW: do not broadcast every projectile position every tick when clients can predict a sufficiently accurate cosmetic trajectory locally.
- [ ]A.5.5 Protect hidden information. HOW: filter projectile visibility, owner details, and private payload information on the server before sending messages.
- [ ]A.5.6 Integrate transient effects. HOW: reuse the existing effects system for trails, muzzle flashes, impacts, and explosions; clients may animate these locally.
- [ ]A.5.7 Keep clients non-authoritative. HOW: client-side trajectories and visuals must never determine hits, damage, ownership, or other gameplay outcomes.
- [ ]A.5.8 Test replication. HOW: verify launch, impact, expiration, chunk transitions, reconnects, and visibility filtering across multiple clients.

## Phase A.6: Performance and Reliability

Goal: keep projectile processing proportional to active projectiles and prevent pathological workloads.

- [ ]A.6.1 Measure performance. HOW: log tick duration, active projectile count, collision checks, serialization time, and bytes sent per client.
- [ ]A.6.2 Avoid unnecessary processing. HOW: update only active projectiles and exclude them from full pixel decision, needs, relationship, and inventory processing unless explicitly required.
- [ ]A.6.3 Handle expiration efficiently. HOW: remove terminal projectiles promptly and avoid repeatedly processing expired objects.
- [ ]A.6.4 Bound expensive work. HOW: enforce server-side limits on creation rates, lifetime, velocity, collision work, and recursive or cascading effects without unnecessarily restricting legitimate gameplay.
- [ ]A.6.5 Preserve off-screen simulation. HOW: keep authoritative projectiles moving and interacting correctly outside client visibility; optimize only when correctness is preserved.
- [ ]A.6.6 Profile before optimizing. HOW: if measurements show a bottleneck, consider persistent structure-of-arrays storage, batched movement, or compiled hot loops without rebuilding arrays every tick unnecessarily.
- [ ]A.6.7 Test network scaling. HOW: measure bandwidth and processing costs under dense projectile bursts, multiple clients, and frequent chunk-boundary crossings.
- [ ]A.6.8 Preserve determinism. HOW: repeat identical initial worlds and command sequences; ensure collision ordering, indexing, batching, and optimizations do not change authoritative outcomes.

## Phase A.7: End-to-End Tests

Goal: verify that projectiles work with existing simulation, inventory, materials, and multiplayer systems.

- [ ]A.7.1 Test thrown objects. HOW: throw a rock, verify its trajectory and impact, and recover it without duplicating its identity.
- [ ]A.7.2 Test material interactions. HOW: launch water and sand at terrain and verify that shared interaction rules produce the correct world changes.
- [ ]A.7.3 Test embedding. HOW: launch a seed, embed it in valid terrain, and verify that it can transition into a persistent object and grow.
- [ ]A.7.4 Test combat. HOW: launch bullets at pixels and structures; verify collision, damage, destruction, and ownership rules.
- [ ]A.7.5 Test invalid commands. HOW: attempt unauthorized launches, unavailable payloads, invalid targets, and excessive velocities; ensure the server rejects them safely.
- [ ]A.7.6 Test projectile bursts. HOW: create many simultaneous projectiles and verify bounded tick time, collision processing, and network traffic.
- [ ]A.7.7 Test multiplayer visibility. HOW: verify that nearby clients receive appropriate events, distant clients do not receive unnecessary updates, and hidden projectiles remain private.
- [ ]A.7.8 Test deterministic replay. HOW: replay the same commands with the same initial state and seed; verify identical authoritative impacts, damage, and world changes.
- [ ]A.7.9 Test extensibility. HOW: add a new projectile behavior using existing properties and interaction rules without creating a new projectile class or rewriting the system.

## Completion Criteria

- [ ]Projectiles support arbitrary payloads and configurable motion and impact behavior.
- [ ]All authoritative movement, collision, and gameplay effects run on the server.
- [ ]Collision detection is efficient and prevents tunneling.
- [ ]Existing objects can transition into and out of projectile simulation without duplication.
- [ ]Short-lived projectiles use event-driven replication wherever practical.
- [ ]Persistent and unpredictable projectiles receive appropriate state updates.
- [ ]Projectiles continue simulating correctly outside client visibility.
- [ ]Projectile processing avoids unnecessary full-entity costs.
- [ ]Performance, determinism, ownership, and multiplayer tests pass.

**Implementation rule:** Inspect the existing codebase before making changes. Reuse existing systems and interfaces wherever practical. Implement one subsection at a time, run relevant tests, and fix regressions before continuing. Do not rewrite unrelated systems or introduce speculative abstractions without a demonstrated need.

Writing

# **Phase 11: Main Menu and Multiplayer Lobby**

## Goal

Allow players to start singleplayer games, host multiplayer games, or join existing servers. Hosted games use an authoritative waiting lobby where players configure nations and game settings before starting.

### Decisions (already made)

- The server owns authoritative lobby state and validates all changes.
- Singleplayer uses a local server and the same client/server architecture as multiplayer.
- The host controls shared game settings and starts the game.
- Each player configures their own nation and personal preferences.
- Lobby state is synchronized through the existing WebSocket and MessagePack protocol.
- Clients never directly modify authoritative server state.

## Phase 11.1: Main Menu

Goal: provide working entry points for every supported game mode.

- [ ]11.1.1 Update the main menu. HOW: add `Singleplayer`, `Host Server`, and `Join Server` options.
- [ ]11.1.2 Implement singleplayer. HOW: start a local server, connect the client as the first player, and enter the lobby or startup flow.
- [ ]11.1.3 Implement hosting. HOW: start a network server, assign the host a player ID, and open the lobby.
- [ ]11.1.4 Implement joining. HOW: accept a server address, connect to the server, and handle connection failures with clear error messages.
- [ ]11.1.5 Handle loading and errors. HOW: display connection status and prevent duplicate connection attempts or multiple unintended local servers.
- [ ]11.1.6 Test menu navigation. HOW: verify that all three options reach the correct state and can recover from failed connections.

## Phase 11.2: Waiting Lobby

Goal: synchronize players and settings before gameplay begins.

- [ ]11.2.1 Create the lobby screen. HOW: display connected players, connection status, nation settings, readiness, and shared game settings.
- [ ]11.2.2 Implement player readiness. HOW: let players indicate readiness and broadcast changes through the server; define whether the host can start before everyone is ready.
- [ ]11.2.3 Add host controls. HOW: allow only the host to change shared settings and start the game.
- [ ]11.2.4 Synchronize lobby state. HOW: send the complete current lobby state when a player joins and incremental updates when it changes.
- [ ]11.2.5 Validate lobby commands. HOW: reject unauthorized setting changes, invalid player IDs, and commands issued in the wrong game phase.
- [ ]11.2.6 Test lobby synchronization. HOW: connect multiple clients and verify that player lists, readiness, settings, and start availability remain consistent.

## Phase 11.3: Nation Configuration

Goal: allow each player to customize their nation before starting.

- [ ]11.3.1 Add nation settings. HOW: allow each player to choose a nation name, color, and icon.
- [ ]11.3.2 Validate nation names. HOW: enforce length limits, reject invalid characters or prohibited names, and enforce uniqueness according to the game's rules.
- [ ]11.3.3 Validate nation colors and icons. HOW: accept only supported formats and predefined or validated icon identifiers.
- [ ]11.3.4 Synchronize nation settings. HOW: broadcast validated changes to all lobby participants using the existing protocol.
- [ ]11.3.5 Handle duplicate names. HOW: reject or request a new name when another nation already uses it, and revalidate changes on the server.
- [ ]11.3.6 Test nation configuration. HOW: verify valid edits, invalid inputs, duplicate names, disconnects, and consistent display across clients.

## Phase 11.4: Lobby Settings

Goal: configure the shared world and individual player preferences.

- [ ]11.4.1 Add world settings. HOW: expose the world seed and supported `GenerationSettings` fields through the lobby UI.
- [ ]11.4.2 Add tutorial preferences. HOW: provide a how-to-play popup toggle that each player controls independently.
- [ ]11.4.3 Validate shared settings. HOW: validate seed formats, numeric ranges, and supported generation options on the server before accepting them.
- [ ]11.4.4 Apply host authority. HOW: reject shared setting changes from non-host players while allowing clients to update their own preferences.
- [ ]11.4.5 Freeze settings at game start. HOW: finalize the accepted settings before generating the authoritative world and reject later changes unless explicitly supported.
- [ ]11.4.6 Test settings. HOW: verify that all clients receive identical shared settings while personal tutorial preferences remain independent.

## Phase 11.5: Lobby Protocol and Lifecycle

Goal: handle lobby transitions and failures without inconsistent state.

- [ ]11.5.1 Add protocol messages. HOW: implement messages for lobby state, setting changes, player readiness, nation updates, and game start using the existing protocol conventions.
- [ ]11.5.2 Track the game phase. HOW: maintain an authoritative server-side phase such as `lobby`, `placement`, and `playing`; validate commands against the current phase.
- [ ]11.5.3 Handle disconnects. HOW: remove disconnected players from active lobby state and update the remaining clients.
- [ ]11.5.4 Handle host departure. HOW: define whether the server closes or transfers host authority; implement one consistent policy and notify all clients.
- [ ]11.5.5 Prevent late joins. HOW: reject new players after gameplay starts unless late joining is explicitly implemented.
- [ ]11.5.6 Handle failed connections. HOW: clean up partially initialized players and resources so failed joins cannot leave stale lobby entries.
- [ ]11.5.7 Test lifecycle transitions. HOW: test host departure, player disconnects, reconnect attempts, simultaneous setting changes, and repeated start requests.

---

# **Phase 12: Game Start and Colony Placement**

## Goal

Let players preview the entire world, choose starting colony locations during a timed placement phase, and begin gameplay when placement finishes. Include a developer mode for testing.

### Decisions (already made)

- The server owns the authoritative game phase, countdown, colony placement, and starting resources.
- The world is generated from shared settings and a seed, then verified using the existing checksum system.
- The placement preview reveals the map temporarily without permanently changing exploration state.
- Colony placement is a validated server command.
- All clients must agree on the game phase and colony ownership.
- Developer controls must not bypass normal server validation for ordinary players.

## Phase 12.1: World Preview

Goal: generate and synchronize the starting world before colony placement.

- [ ]12.1.1 Finalize world generation. HOW: when the host starts the game, validate settings and generate or finalize the authoritative world using the agreed seed.
- [ ]12.1.2 Synchronize world identity. HOW: broadcast the seed, generation settings, and checksum; require clients to generate matching terrain and handle mismatches with a clear error.
- [ ]12.1.3 Reveal the entire map temporarily. HOW: enable a separate preview visibility state for all clients without modifying persistent nation exploration data.
- [ ]12.1.4 Transition into placement. HOW: move the authoritative game phase from `lobby` to `placement` only after the world is ready and required clients have synchronized according to the chosen policy.
- [ ]12.1.5 Test world preview. HOW: verify matching terrain, temporary full-map visibility, and correct recovery from checksum mismatches.

## Phase 12.2: Placement Countdown

Goal: provide a synchronized, server-authoritative placement window.

- [ ]12.2.1 Implement the countdown. HOW: start a configurable 20–30 second timer when placement begins.
- [ ]12.2.2 Synchronize countdown state. HOW: broadcast the authoritative end time or remaining duration and let clients derive their displayed countdown from server timing.
- [ ]12.2.3 Handle countdown updates. HOW: avoid sending a message every frame; send phase changes and sufficient timing information for clients to display the timer smoothly.
- [ ]12.2.4 Define early completion. HOW: start gameplay early when every eligible player has placed a colony, if that is the selected game rule.
- [ ]12.2.5 Handle timer expiry. HOW: prevent late placement commands and execute the documented fallback for players who have not placed a colony.
- [ ]12.2.6 Test timer behavior. HOW: verify synchronization across clients, early completion, expiry, and delayed or duplicated commands.

## Phase 12.3: Colony Placement

Goal: let each player select and place one valid starting colony.

- [ ]12.3.1 Add placement previews. HOW: show the proposed colony footprint and clearly distinguish valid and invalid locations using client-side visuals.
- [ ]12.3.2 Implement `place_colony`. HOW: accept a placement request containing the target location and validate it on the server.
- [ ]12.3.3 Validate placement. HOW: check the current phase, player eligibility, terrain suitability, world bounds, minimum spacing, and placement limits.
- [ ]12.3.4 Resolve simultaneous requests. HOW: process placement commands in a deterministic order and revalidate the location immediately before committing it.
- [ ]12.3.5 Prevent duplicate colonies. HOW: track each player's placement status and reject repeated or conflicting placement commands.
- [ ]12.3.6 Define repositioning. HOW: explicitly decide whether players can move their colony before the countdown expires and validate repositioning without duplicating entities or resources.
- [ ]12.3.7 Test placement validation. HOW: test invalid terrain, overlapping colonies, minimum spacing, simultaneous requests, and repeated commands.

## Phase 12.4: Colony Initialization

Goal: create starting colonies through existing systems.

- [ ]12.4.1 Create colonies. HOW: use existing pixel, structure, blueprint, and entity creation systems rather than introducing a separate colony entity type unless required.
- [ ]12.4.2 Assign ownership. HOW: associate each colony and its starting assets with the correct player and nation.
- [ ]12.4.3 Grant starting resources. HOW: initialize resources through existing inventory and resource systems using validated game settings.
- [ ]12.4.4 Record placement state. HOW: persist the colony location, ownership, and completion status in authoritative game state.
- [ ]12.4.5 Test initialization. HOW: verify correct ownership, resources, IDs, placement locations, and replication without creating duplicate assets.

## Phase 12.5: Start Gameplay

Goal: transition every client into normal simulation consistently.

- [ ]12.5.1 Implement the phase transition. HOW: start normal gameplay when all eligible players finish placement or the authoritative countdown expires.
- [ ]12.5.2 Define missing-player fallback. HOW: choose a deterministic policy for players without colonies, such as automatic valid placement or removal from the active match.
- [ ]12.5.3 Activate normal commands. HOW: enable gameplay commands only after the server transitions to `playing`.
- [ ]12.5.4 Activate fog of war. HOW: disable temporary full-map preview visibility and initialize normal nation visibility from starting colonies.
- [ ]12.5.5 Broadcast game start. HOW: send the authoritative phase transition and required initial state so every client enters gameplay consistently.
- [ ]12.5.6 Test game start. HOW: verify that clients cannot issue normal commands early and that no player can place a colony after gameplay begins.

## Phase 12.6: Developer Mode

Goal: accelerate startup and test world initialization without weakening normal multiplayer security.

- [ ]12.6.1 Add developer configuration. HOW: provide a developer-only launch option or configuration setting for skipping lobby waits, shortening or bypassing the countdown, and revealing the map.
- [ ]12.6.2 Support test colony placement. HOW: allow privileged test workflows to create colonies and initial assets using the same underlying creation systems.
- [ ]12.6.3 Validate privileged actions. HOW: keep developer operations separate from ordinary player commands and enforce authorization on the server.
- [ ]12.6.4 Prevent accidental release access. HOW: ensure developer privileges cannot be enabled by an untrusted client in a normal hosted game.
- [ ]12.6.5 Test developer workflows. HOW: verify rapid startup, deterministic test setup, and normal gameplay behavior when developer mode is disabled.

## Phase 12.7: End-to-End Tests

Goal: verify the complete startup flow.

- [ ]12.7.1 Test singleplayer startup. HOW: launch a local server, generate the world, place the colony, and enter gameplay.
- [ ]12.7.2 Test hosted multiplayer. HOW: connect multiple clients and verify shared world state, independent colony ownership, and synchronized phase transitions.
- [ ]12.7.3 Test disconnects. HOW: disconnect players during the lobby, countdown, and placement phases and verify the selected lifecycle rules.
- [ ]12.7.4 Test placement conflicts. HOW: submit simultaneous and invalid placement requests and verify deterministic results.
- [ ]12.7.5 Test timer expiry. HOW: verify that unplaced players follow the defined fallback and that late requests are rejected.
- [ ]12.7.6 Test developer mode. HOW: verify accelerated startup without affecting normal client permissions.
- [ ]12.7.7 Verify synchronization. HOW: confirm that all clients agree on the game phase, colony positions, ownership, and initial resources.

---

# **Phase 13: Fog of War**

## Goal

Reveal the entire map during starting placement. Once gameplay begins, obscure undiscovered terrain and reveal explored areas independently for each nation. Enforce visibility on the server to prevent information leaks.

### Decisions (already made)

- Exploration and current visibility are separate states.
- Discovery persists after a location becomes unseen.
- Each nation has independent exploration state.
- Temporary world preview does not permanently reveal terrain.
- The server determines which entities and sensitive state each client may receive.
- Visibility updates use chunks or compact masks instead of repeatedly transmitting the entire map.

## Phase 13.1: Exploration State

Goal: track discovered terrain independently for each nation.

- [ ]13.1.1 Add per-nation exploration data. HOW: store discovered tiles or chunks separately for each nation, reusing the existing chunk grid where practical.
- [ ]13.1.2 Separate discovery from visibility. HOW: track whether a tile has ever been discovered independently of whether it is currently visible.
- [ ]13.1.3 Persist exploration state. HOW: include discovery data in the appropriate save format and restore it when a game or player reconnects.
- [ ]13.1.4 Initialize discovery. HOW: begin normal gameplay with only the areas revealed by starting colonies and other initial vision sources.
- [ ]13.1.5 Test exploration state. HOW: verify independent nation discovery, persistence, and correct initialization after world preview.

## Phase 13.2: Visibility Calculation

Goal: calculate current visibility efficiently as entities move and interact.

- [ ]13.2.1 Identify vision sources. HOW: calculate visibility from owned pixels, colonies, and other entities with vision capabilities.
- [ ]13.2.2 Implement visibility updates. HOW: recalculate affected areas when vision sources move, appear, disappear, or change vision properties instead of recalculating the entire map every tick.
- [ ]13.2.3 Update exploration. HOW: mark newly visible tiles as discovered and preserve their discovery state after they become unseen.
- [ ]13.2.4 Reuse spatial indexing. HOW: use existing spatial and chunk structures to limit visibility calculations to affected regions.
- [ ]13.2.5 Define visibility rules. HOW: document how terrain opacity, obstacles, vision range, stealth, and detection capabilities affect visibility, reusing existing sensing systems where appropriate.
- [ ]13.2.6 Test visibility calculation. HOW: verify movement, overlapping vision sources, destroyed vision sources, and newly discovered regions.

## Phase 13.3: Fog Rendering

Goal: render unexplored, discovered, and currently visible areas correctly.

- [ ]13.3.1 Add fog rendering. HOW: display undiscovered terrain as unexplored, discovered but unseen terrain as fogged, and currently visible terrain normally.
- [ ]13.3.2 Preserve last-known terrain. HOW: retain previously discovered terrain information without treating hidden changes as currently visible.
- [ ]13.3.3 Separate rendering from simulation. HOW: keep fog visualization in the client renderer and never make gameplay outcomes depend on client-side fog state.
- [ ]13.3.4 Integrate selection and interaction. HOW: prevent normal player interactions from exposing hidden information through tooltips, selection, previews, or contextual commands.
- [ ]13.3.5 Test rendering. HOW: verify all three visibility states during movement, discovery, and loss of vision.

## Phase 13.4: Server-Side Visibility and Security

Goal: prevent clients from receiving information they are not allowed to know.

- [ ]13.4.1 Filter entity replication. HOW: send entity state according to the receiving nation's visibility and existing interest-management rules.
- [ ]13.4.2 Protect hidden entities. HOW: prevent unseen enemies, stealth units, hidden traps, and private entity properties from leaking through network messages.
- [ ]13.4.3 Filter world information. HOW: ensure terrain changes and resource information outside the permitted visibility rules are not unintentionally disclosed.
- [ ]13.4.4 Validate commands against visibility. HOW: check relevant targets and information-sensitive actions on the server instead of trusting client-side fog.
- [ ]13.4.5 Handle stale knowledge. HOW: distinguish remembered terrain and previously observed entities from currently visible authoritative state.
- [ ]13.4.6 Test information leaks. HOW: inspect messages received by opposing clients and verify that hidden entities, private fields, and undiscovered information are not transmitted.

## Phase 13.5: Preview and Placement Integration

Goal: transition from full-map preview to normal nation visibility without corrupting discovery state.

- [ ]13.5.1 Enable temporary reveal. HOW: allow all players to see the entire map during the placement phase using a separate preview flag or visibility mode.
- [ ]13.5.2 Preserve discovery state. HOW: do not mark every tile discovered merely because it was visible during preview.
- [ ]13.5.3 Disable preview reveal. HOW: remove temporary visibility when the server enters the `playing` phase.
- [ ]13.5.4 Initialize normal visibility. HOW: calculate discovery from each nation's starting colonies and other vision sources after gameplay begins.
- [ ]13.5.5 Test transitions. HOW: verify that preview visibility disappears correctly and that each nation begins with only its legitimately discovered areas.

## Phase 13.6: Multiplayer Synchronization

Goal: transmit fog updates efficiently and restore correct state after reconnects.

- [ ]13.6.1 Replicate discovery changes. HOW: send changed exploration chunks or compact tile masks rather than the entire map on every tick.
- [ ]13.6.2 Replicate current visibility. HOW: send incremental visibility updates when affected areas become visible or unseen.
- [ ]13.6.3 Handle chunk transitions. HOW: ensure clients receive the correct fog and discovery state when entering new regions.
- [ ]13.6.4 Handle reconnects. HOW: restore the reconnecting player's authorized exploration and current visibility state without revealing another nation's discoveries.
- [ ]13.6.5 Minimize network traffic. HOW: batch visibility changes and avoid resending unchanged masks or chunks.
- [ ]13.6.6 Test synchronization. HOW: verify consistent fog across multiple clients, chunk boundaries, reconnects, and simultaneous visibility changes.

## Phase 13.7: End-to-End Tests

Goal: verify exploration, rendering, and information security together.

- [ ]13.7.1 Test temporary reveal. HOW: verify that all terrain is visible during placement without permanently revealing the map.
- [ ]13.7.2 Test independent exploration. HOW: move two nations through different regions and verify that their discovery states remain independent.
- [ ]13.7.3 Test persistent discovery. HOW: leave a previously explored region and verify that its terrain remains remembered but is no longer currently visible.
- [ ]13.7.4 Test moving vision sources. HOW: move, create, and destroy vision-providing pixels and verify correct visibility updates.
- [ ]13.7.5 Test stealth and hidden entities. HOW: verify that fog and server-side visibility rules prevent unauthorized entity replication.
- [ ]13.7.6 Test reconnects. HOW: reconnect clients and verify correct restoration of discovery and visibility.
- [ ]13.7.7 Test performance. HOW: measure visibility calculation time, update volume, and bandwidth with large maps, many vision sources, and multiple nations.

## Completion Criteria

- [ ]Players can start singleplayer games, host multiplayer games, and join existing servers.
- [ ]Lobby state, nation configuration, readiness, and shared settings are authoritative and synchronized.
- [ ]All clients generate or verify the same world before placement.
- [ ]Colony placement is validated, deterministic, and protected against duplicate requests.
- [ ]Gameplay starts consistently when placement completes or the countdown expires.
- [ ]Developer mode supports testing without exposing privileged controls to ordinary clients.
- [ ]Fog distinguishes unexplored, discovered-but-unseen, and currently visible terrain.
- [ ]Each nation has independent exploration state, and temporary preview visibility does not persist.
- [ ]Server-side visibility prevents hidden entities and sensitive state from leaking.
- [ ]Fog updates are incremental, chunk-aware, and restored correctly after reconnects.

**Implementation rule:** Inspect the existing codebase before changing files. Reuse existing lobby, protocol, world-generation, command, interest-management, rendering, and persistence systems wherever practical. Implement one subsection at a time, run relevant tests, and fix regressions before continuing. Do not rewrite unrelated systems or introduce speculative abstractions without a demonstrated need.