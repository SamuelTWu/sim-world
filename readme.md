# **Sim World**

This engine is meant to give you the tools to recreate any fantasy land, from Lord of the Rings to Dune to Conway's Game of Life. The key is that all aspects, from world generation to civilizations to entities, are customizable and allow for complex behaviors with simple implementation.

The world is generated procedurally, populated by autonomous entities, and simulated before the player enters. Civilizations emerge as entities move, gather resources, build structures, cooperate, fight, trade, and adapt to their environment. The player joins a world that already exists, becoming part of an ecosystem that continues to evolve around them.

The core idea is that **everything is a pixel**. A pixel is a single entity with properties, behaviors, and motivations. Players research new attributes, modify existing ones, and combine them to engineer their own creations. A pixel standing on stone and extracting stone might be called a miner by one player and a stone factory by another. A pixel that eats grass might be a cow, a biological machine, or something entirely different.

The game provides presets as starting points, not fixed classes. Players are encouraged to experiment, discover combinations, and create their own solutions. There are no hard-coded warriors, animals, factories, or civilizations. These emerge from the properties and behaviors of pixels and how they interact with the world.

The same principle extends to the environment. Structures, projectiles, resources, and civilizations use shared systems and configurable definitions rather than requiring a separate implementation for every possible creation.

The sections below describe the main components of the engine and how they fit together.

### **Game Engine**

game.py

main.py

menu.py

simulation.py

The game engine coordinates the game loop, simulation, and player experience. `Simulation` owns the world, `entityManager`, `systemRunner`, `eventBus`, and seeded random number generator. It advances the world independently of rendering, allowing the same simulation to run in singleplayer, multiplayer, or headless mode.

The simulation runs at a fixed tick rate independently of the rendering frame rate. This keeps gameplay consistent across different clients and allows the server to simulate the world without drawing anything.

The server is authoritative. It owns the actual world state, validates player commands, advances the simulation, and distributes updates to connected clients. Clients send commands rather than modifying authoritative state directly.

The game also has distinct phases:

- **Lobby:** Players connect, configure their nations, and prepare the game.
- **Placement:** The world has been generated, and players choose where to establish their colonies.
- **Playing:** The simulation runs normally, with autonomous entities, player commands, and fog.

A shared phase system determines which commands are valid at any given time. This prevents gameplay actions from being used before the world is ready or colony placement has finished.

### **Rendering**

camera.py

entity\_renderer.py

renderer.py

world\_renderer.py

rendering/selection.py

rendering/structures.py

rendering/fog.py

The rendering system displays the world and interprets player input. Camera manages viewport position, zoom, mouse dragging, coordinate conversion, visible tile bounds, and hovered-tile detection.

The world uses a fixed `TILE_SIZE` of 32 pixels. Zoom changes displayed tile and entity sizes without changing world coordinates. Rendering runs independently of simulation ticks, allowing a 20 Hz simulation to render at 60 FPS or higher. Entity positions are interpolated between server updates to keep movement smooth.

Entity rendering reads from the client's replicated state rather than directly accessing the simulation. Structures and fog follow the same principle: the renderer displays the information available to the client without consulting authoritative server objects.

Mouse interaction is part of the control system. Players can click a pixel to issue an action, inspect its attributes and inventory, drag to select multiple pixels, right-click to issue contextual commands, and recall selected pixels to a home point. The same command system supports both direct control and autonomous behavior.

Structure placement also uses client-side previews. A preview shows the expected footprint and rotation before placement, then resolves into the authoritative structure when the server confirms the command.

Fog rendering distinguishes between unexplored terrain, explored terrain that is no longer visible, and terrain currently visible to the player's nation. Remembered terrain remains on the map even when its current state is unknown.

### **World Generation**

generator.py

noise.py

world.py

The `WorldGenerator` creates a complete world from a `GenerationSettings` configuration. Generation begins with terrain and procedural maps, then creates continents, elevation, water, temperature, wetness, biomes, and environmental features.

World generation is deterministic: the same seed and generation settings produce the same initial world. This allows clients to generate terrain locally while verifying that their result matches the server's world checksum.

The world is generated before civilizations are introduced. Terrain and biome information determine which resources are available and where colonies can be established.

During the placement phase, clients can preview the entire generated terrain. Once the game begins, fog controls what each nation can see, while the server continues to maintain the complete world.

### **Maps**

map\_types.py

map.py

mapModifiers.py

Maps describe environmental information such as elevation, temperature, moisture, fertility, and other procedural properties. These maps influence terrain generation, biome placement, resource availability, and the behavior of entities.

Maps are separate from the visible tile grid. Multiple maps can influence the same location, allowing the world to contain complex environmental gradients rather than isolated biome regions.

### **Features**

feature.py

featureManager.py

featureSelectionStrategy.py

Features are anything placed in the world during generation, including biomes, vegetation, resources, structures, and other environmental elements. Features use maps, tiles, and selection strategies to determine where and how they appear.

Feature blending allows different environmental regions to transition naturally. Favor strength determines how strongly a feature prefers certain noise values, while favor scale controls the size of favored and suppressed regions.

Generated features provide the initial conditions for the simulation. After generation, entities can modify the world by extracting resources, placing structures, changing tiles, and interacting with other features.

### **Tiles**

tile.py

tile\_types.py

Tiles represent the physical world. A tile contains attributes describing its material, shape, surface, biome, temperature, permeability, opacity, hardness, structural role, and tags.

Each tile acts as a feature vector rather than simply a visual block. Systems use these attributes to determine what can move through a tile, what resources it contains, what can be extracted from it, and what can be built on it.

Tiles may contain resources, and resources may also exist as items carried by pixels or stored in structures. A resource can therefore exist as part of the environment, as an inventory item, or as a material used in construction.

All world edits go through a single world modification function. This allows changes to be recorded, synchronized across multiplayer clients, and saved to disk.

Tile properties also contribute to collision and visibility. Terrain can block movement, stop projectiles, or obstruct vision depending on its properties.

### **Entities**

entity.py

entityManager.py

entities/entityFactory.py

**behavior/**

behavior.py

behaviorManager.py

**system/**

attributeSystem.py

decisionSystem.py

eventBus.py

identitySystem.py

memorySystem.py

needSystem.py

relationshipSystem.py

rules.py

simContext.py

stimulus.py

systemRunner.py

task.py

territory.py

territoryRules.py

There is only one primary entity type: **Pixel**. Every pixel owns data describing its current state, attributes, inventory, ownership, identity, and active orders. Independent systems determine how those properties interact and what the pixel does autonomously.

A pixel can become a warrior, bullet, spawner, plant, miner, spy, bomb, animal, vehicle, mechanism, or something that has no real-world equivalent. These are not separate entity classes. They are combinations of properties, actions, reactions, and motivations.

Pixels can move, perceive their surroundings, gather resources, attack, build, reproduce, transport other pixels, communicate, and influence one another. Their capabilities depend on the attributes they have unlocked and the parameters assigned to them.

Players begin with a small set of presets, such as Gatherer, Scout, and Warrior. These are saved attribute configurations rather than special classes. Players can research their components, adjust their parameters, and save their own blueprints. Creating a new kind of pixel is an engineering problem rather than a class-selection problem.

All pixels have stable unique IDs and an owner. The owner determines who can issue commands to them, while their attributes and behaviors determine what they can do autonomously.

Pixels can also be temporarily in flight as projectiles. In this state, an existing pixel remains the same logical entity but is removed from ordinary movement and perception systems until it lands.

#### **Attributes and Systems**

Entity primarily stores data. Independent systems interpret that data and implement the rules governing the simulation. Attribute dependencies are defined through configuration or an attribute graph rather than hard-coded references between individual attribute classes.

Attributes can be base, derived, temporary, environmental, or historical. For example, anger might depend on patience, stress, and provocation. Damage might temporarily reduce health, while environmental temperature influences energy consumption.

The main systems are:

- **AttributeSystem:** Calculates derived attributes and updates temporary or environmental modifiers.
- **NeedSystem:** Tracks requirements such as energy, safety, resources, and reproduction.
- **DecisionSystem:** Chooses actions based on needs, available capabilities, motivations, and current conditions.
- **RelationshipSystem:** Tracks cooperation, hostility, trust, allegiance, and other relationships.
- **MemorySystem:** Remembers locations, events, targets, and previous experiences.
- **IdentitySystem:** Classifies pixels based on their attributes, behaviors, relationships, and experiences.
- **TerritorySystem:** Tracks claims, borders, influence, and territorial rules.
- **EventBus:** Communicates events such as damage, death, resource extraction, construction, and spawning.
- **Scheduler:** Handles delayed work such as production cycles, countdowns, and projectile expiration without requiring every system to scan for timers on every tick.
- **DamageSystem:** Provides a shared damage pathway for attacks, projectiles, and other sources of damage.

Systems operate on shared entity data. This keeps the engine extensible: adding a new attribute or behavior should not require rewriting unrelated systems.

#### **Behaviors and Actions**

Behaviors are reusable, data-driven rules. They can be activated autonomously by the `DecisionSystem` or pinned to an entity through a player command. A command is therefore an instruction to perform a behavior, not a separate implementation of that behavior.

The main world-changing actions include:

- **Spawn:** Creates a new pixel from a blueprint. A cannon spawns a projectile, a creature produces an egg, and a factory creates a vehicle. Spawning can consume resources or energy and may have a cooldown.
- **Transfer:** Moves an existing resource or entity between inventories, owners, or locations without duplicating it.
- **Drop:** Materializes a carried resource as a world object or modifies the environment using the existing inventory.
- **Place:** Creates a pixel or structure at a valid location, subject to ownership, unlocks, costs, terrain, and occupancy rules.
- **Launch:** Removes a payload from an inventory and sends it through the projectile simulation.
- **Build:** Allows a capable pixel to construct a structure using the same placement rules available to players.

These actions are deliberately separate. Spawning creates an entity, transferring moves something that already exists, dropping places something into the world, and launching sends a payload into motion.

Behaviors can also be combined with conditions and reactions. For example, a pixel might extract stone only while standing on stone, transfer it when its inventory is full, and return home when its energy is low.

### **Civilizations and Structures**

Civilizations are not hard-coded objects with fixed rules. They emerge from groups of pixels that share motivations, relationships, resources, building preferences, and patterns of behavior.

Each player establishes a nation and places a colony in the generated world. A nation records its player owner, name, color, icon, and colony. Its identity provides a consistent basis for ownership, visibility, and relationships between civilizations.

For autonomous players, or CPU civilizations, structure preferences are motivations rather than mandatory building templates. A CPU might prefer defensive structures, organic growth, dense settlements, isolated shelters, or no structures at all. Its preferences influence decisions without completely determining them.

#### **Structures**

Structures are stationary world objects managed separately from pixels. A structure has its own unique ID, blueprint, owner, anchor position, rotation, health, and mutable state.

Unlike pixels, structures do not need to participate in ordinary entity movement or per-tick position replication. They interact with the world through their footprint, capabilities, and registered occupancy.

A structure blueprint defines its footprint, material, maximum health, collision properties, placement requirements, and capabilities. A structure with no active capabilities can remain a passive object without requiring regular simulation work.

Structure definitions and runtime state are separate. The blueprint describes what a structure can do, while the instance stores information such as current health, whether a door is open, what a container holds, or how far production has progressed.

Structure footprints are defined relative to an anchor tile. Rotating a structure changes the occupied cells, allowing the same blueprint to support different orientations. A shared footprint calculation keeps placement previews, movement, collision, and server validation consistent.

Structures use their own ID counter, separate from pixel IDs. References that can target either type identify the object's kind as well as its ID.

#### **Construction and Placement**

Structure placement is validated by the server. A placement must satisfy the player's permissions, technology unlocks, resource costs, world boundaries, terrain requirements, and occupancy constraints.

The placement operation checks all requirements before spending resources. If placement fails, the player is not charged. If multiple players attempt to occupy the same area, the server resolves the requests in a deterministic order and rechecks occupancy when committing each placement.

Structures can be removed by their owner, destroyed through damage, or transformed as part of other world interactions. Deconstruction may return a portion of the original materials, while destruction can produce drops or debris according to the blueprint.

Pixels with the appropriate capabilities can use the same construction pathway. Autonomous construction therefore follows the same ownership, resource, and placement rules as player construction.

Structures can also contain inventories, produce resources, or provide specialized interactions. Their capabilities are defined by their blueprints rather than by separate hard-coded structure classes.

#### **Materials and Capabilities**

Materials define properties such as hardness, durability, flammability, opacity, and permeability. These properties influence how terrain, structures, and projectiles interact.

A structure can have several capabilities:

- **Door:** Can be opened or closed, changing whether its footprint blocks movement.
- **Storage:** Holds resources through the same inventory system used by pixels.
- **Producer:** Converts inputs into outputs according to a recipe and production duration.

Capabilities are registered independently, so systems only process structures that need their services. A passive wall does not incur the same ongoing cost as an active factory.

Storage transfers preserve resource totals. Moving an item from a pixel to a structure removes it from the source and adds it to the destination as one operation, with rollback if the transfer fails.

Production uses scheduled events rather than checking every factory every tick. A producer schedules work when its inputs are available, verifies those inputs when production completes, and schedules another cycle when appropriate.

#### **Graph Grammars**

Graph grammars define the rules used to generate and extend complex structures. They are intended to support data-driven combinations of building rules without requiring arbitrary scripting.

Example grammars include:

- Village architecture
- City architecture
- Forest and organic growth
- Defensive fortifications
- Industrial structures
- Haunted or corrupted architecture

Each grammar defines possible components, connection rules, structural constraints, and required or preserved block tags. Building blocks carry attributes describing their material, shape, role, and compatibility.

These constraints allow grammars to blend. A defensive settlement and an organic forest civilization might combine stone walls with living structures if their rules permit it. Incompatible components remain separate or require a valid transition.

Initially, larger constructions can consist of multiple independently placed structures. More advanced graph grammar behavior can build on the same structure and placement systems.

### **Tech Tree**

Every unlockable property or behavior belongs to one of four categories. This gives players a consistent engineering language while allowing them to create increasingly complex pixels without scripting.

- **Body:** Passive properties such as health, speed, size, lifespan, and capacity.
- **Sense:** What a pixel can perceive, including range, filters, and hidden entities.
- **Action:** What a pixel can do, such as move, extract, attack, spawn, transfer, or build.
- **Reaction:** What happens when an event occurs, such as death, contact, a timer, or damage.

Players research attributes through a technology tree. Presets provide starting configurations, but researching an attribute unlocks the ability to understand and modify it. Adjusting parameters and saving blueprints may also cost currency or require resources.

The tree should teach increasingly complex forms of engineering: movement and sensing first, then resource management, conversion, targeting, reactions, and finally conditional and social behavior.

#### **Tier 0: Fundamentals**

Five starting attributes establish the basic building blocks of a pixel.

- **Speed (Body):** How quickly it moves.
- **Sight (Sense):** How far it can perceive.
- **Health (Body):** How much damage it can survive.
- **Tether (Behavior):** Keeps it within a radius of a home point or owner.
- **Grab (Action):** Collects a resource from the tile it occupies.

These attributes are enough to create simple scouts, workers, and patrols. They introduce movement, perception, and interaction with the world.

#### **Tier 1: Basic Specialization**

- **Carry (Body):** How many resources or entities it can transport.
- **Deposit (Action):** Transfers carried resources to a home point or structure.
- **Strike (Action):** Damages a target, with configurable damage, range, and cooldown.
- **Lifespan (Body):** Limits how long the pixel survives.
- **Appearance (Body):** Controls color, size, shape, and visual identity.
- **Energy Store (Body):** Determines how much energy it can hold.

These attributes support gatherers, basic combat units, couriers, temporary units, and simple resource networks.

#### **Tier 2: Conversion and Targeting**

- **Filter (Sense):** Restricts targets by tile, pixel, resource, tag, or team.
- **Extract (Action):** Converts a tagged tile or environmental feature into a resource at a specified rate.
- **Consume (Action):** Consumes a tagged pixel or resource to obtain energy or another benefit.
- **Produce (Action):** Converts energy or resources into a different resource.
- **Identity Tag (Identity):** Assigns tags that other pixels can use to recognize or target it.
- **Spawn (Action):** Creates a pixel from a saved blueprint, with configurable costs and cooldowns.

This tier allows players to engineer resource converters, livestock, factories, spawners, and specialized combat units.

#### **Tier 3: Reactions and Social Behavior**

- **On Death (Reaction):** Triggers an effect when the pixel dies.
- **On Contact (Reaction):** Triggers an effect when it touches a target.
- **On Timer (Reaction):** Triggers an effect after a specified interval.
- **On Hurt (Reaction):** Triggers an effect when it takes damage.
- **Area Effect (Action):** Affects multiple targets within a radius.
- **Follow / Flock (Action):** Moves relative to a chosen pixel or group.
- **Aggro (Behavior):** Defines which targets provoke hostility and which targets it pursues.
- **Stealth (Body):** Reduces or removes visibility, with detection counters.
- **Click Action (Action):** Defines what happens when the player clicks the pixel.

This tier enables bombs, hunters, guards, flocking creatures, traps, and more sophisticated control schemes.

#### **Tier 4: Advanced Engineering**

- **Status Effect (Action):** Applies temporary effects such as slow, rally, weaken, or shield.
- **Build (Action):** Places tiles or structures using construction rules.
- **Signal (Sense / Action):** Sends or receives named messages over a channel.
- **Condition (Logic):** Restricts a behavior or reaction to conditions, such as energy above a threshold or an enemy within range.
- **Memory (Sense / State):** Remembers locations, targets, and relevant events.
- **Mutate (Reaction):** Changes a pixel into another blueprint when a condition is met.
- **Extra Rule Slots / Capacity Boost (Body):** Allows a pixel to support more behaviors, conditions, and reactions.

This tier enables coordinated armies, evolving organisms, programmable factories, autonomous settlements, and complex interactions between civilizations.

Attributes should be independently unlockable where practical, with prerequisites defining the progression. The exact costs and dependencies can be balanced later.

#### **Example Blueprints**

- **Gatherer:** Speed + Sight + Grab + Carry + Deposit.
- **Scout:** Speed + Sight + Tether.
- **Warrior:** Health + Strike + Sight + Aggro.
- **Stone Factory:** Immobile, extracts stone while standing on a stone tile, and converts energy into stone resources.
- **Cow:** Wanders, consumes pixels tagged as grass for energy, produces milk, and spawns a calf when its energy is high enough.
- **Bomb:** Moves toward a target, triggers area damage on contact, and dies.
- **Spy:** Uses stealth, high speed, and sight to observe enemies and report information to its owner.
- **Spawner:** Consumes resources to create pixels from saved blueprints.
- **Plant:** Remains stationary, converts environmental energy into stored energy, and spawns seeds on a timer.

These are examples rather than special entity types. Each blueprint is a configuration of attributes, behaviors, conditions, and reactions. Players can rename their creations, alter their parameters, and invent entirely new combinations.

### **Projectiles**

entity/projectiles.py

entity/projectileTypes.json

command/commands/launch.py

rendering/transient\_events.py

Projectiles allow objects to travel through the world and interact with terrain, structures, and pixels. Unlike hitscan attacks, which resolve their effects immediately, traveling projectiles can be dodged, blocked, deflected, or intercepted.

A projectile separates three concepts:

- **Payload:** What it carries, such as an item, an existing pixel, or a quantity of material.
- **Motion:** How it travels, including velocity, drag, optional homing, and lifetime.
- **Impact:** What happens when it reaches a target, such as dealing damage, penetrating, bouncing, embedding, or depositing material.

Projectile presets define reusable motion and impact properties. New projectile types can be introduced through data without requiring a separate movement implementation for each one.

Launching a projectile is a server-validated action. Ownership, source state, payload availability, technology unlocks, and cooldowns are checked before the payload is consumed and the projectile is created.

Projectiles move through the simulation using swept collision tests. The system checks the path between the previous and next positions rather than testing only the destination, preventing fast projectiles from passing through thin obstacles.

Terrain, structures, and pixels share a collision interface. When several objects intersect a projectile's path, the earliest collision determines the outcome, with deterministic tie-breaking rules.

Material properties influence impact results. A projectile's payload and impact energy can determine whether a wall stops it, whether a target takes damage, or whether the projectile continues through an object.

Existing pixels can also be launched as payloads. Their identity and ownership are preserved while they are in flight, and the same entity returns to the world when it lands. No duplicate pixel is created.

Short-lived projectiles use transient events for launch and impact visuals. Longer-lived or steerable projectiles can use state replication. In both cases, the server determines collisions and outcomes; clients only render the results.

Projectiles continue simulating even when their owner disconnects or the projectile moves outside every client's visibility. This keeps gameplay independent of which clients happen to be connected or watching.

### **Multiplayer**

**server/**

client.py

commands.py

deltas.py

interest.py

protocol.py

server.py

phase.py

nations.py

lobby.py

structuresync.py

fog.py

The server owns the truth. Clients send commands, never authoritative state. The server validates commands, advances the simulation, and distributes updates to connected players.

The world is generated from a shared seed and settings. Clients generate the same terrain locally and verify it using a checksum. World changes are transmitted as deltas instead of repeatedly sending the entire world.

The simulation runs at a fixed rate of approximately 10–20 ticks per second, independently of the rendering frame rate. The transport uses WebSockets and asyncio, while messages are encoded with MessagePack to keep the protocol compatible with future non-Python clients.

The renderer reads only from the client's replicated state. It never reads directly from the authoritative `Simulation`.

The server tracks player identity, nation ownership, game phase, and which parts of the world each client is allowed to see. Shared protocol messages communicate commands, results, entity changes, structure changes, phase transitions, and visibility updates.

#### **Main Menu and Lobby**

The main menu provides three entry points:

- **Singleplayer:** Starts a local server and connects the client to it.
- **Host Server:** Starts a server that other players can join.
- **Join Server:** Connects to an existing server using its address and port.

Singleplayer uses the same server and client architecture as multiplayer. This avoids maintaining a separate simulation path for offline play.

The lobby holds the connected players, their nation settings, readiness, and shared world-generation settings. Each player can choose a nation name, color, and icon. The host controls the generation settings and starts the game.

Nation names must be valid and unique within the lobby. Colors and icons are selected from supported values, and generation settings are validated by the server before they are accepted.

Lobby state is broadcast to connected players when it changes. Once the host starts the game, the server generates the world and clients verify that their locally generated terrain matches the authoritative checksum.

The lobby closes when the game advances beyond its initial setup. New players cannot join an ongoing game through the normal lobby path, while reconnecting existing players is handled separately.

If the host disconnects, hosting can transfer to the earliest remaining player. If no players remain, the server can shut down according to its lifecycle policy.

#### **Commands**

Players interact with the world by sending commands. The server checks ownership, permissions, resources, unlocks, targets, and other requirements before applying them.

- **Move:** Assigns a movement order.
- **Act:** Interprets a click as a contextual action, such as moving, attacking, spawning, dropping, or transferring.
- **Box:** Selects a group of pixels for a command.
- **Place:** Creates a pixel or structure using a blueprint and any required resources.
- **Place Colony:** Establishes or relocates a nation's colony during the placement phase.
- **Spawn:** Instructs a pixel to create another pixel.
- **Transfer:** Moves existing resources or entities between inventories or locations.
- **Drop:** Materializes a carried resource as a world object.
- **Launch:** Sends a payload into the projectile simulation.
- **Attack:** Assigns an attack order against a valid target.
- **Edit Property:** Changes a pixel's configuration when the player has the necessary unlocks and currency.
- **Save Blueprint:** Saves a pixel configuration for later use, subject to the applicable requirements.
- **Toggle Door:** Opens or closes a structure door when the player has permission.

Placement-style commands can include a client reference so that the result can be matched to the corresponding preview. The server returns the created object IDs or a rejection, allowing the client to resolve previews without guessing which object was created.

Autonomous pixels and player-controlled pixels use the same underlying behaviors. Player commands override or guide those behaviors without requiring separate implementations.

Commands are restricted by game phase. Colony placement belongs to the placement phase, while ordinary movement, combat, construction, and other gameplay actions belong to the playing phase.

#### **World Synchronization**

World changes are recorded through a delta log. Deltas are grouped by chunk, and clients receive changes for chunks within their relevant area.

Pixel visibility is handled separately. The server tracks which pixels each client knows about and sends full state when a pixel enters visibility, changed fields when it updates, and a leave message when it is no longer visible.

Structures are synchronized through a similar process, but their stationary nature allows replication to be driven by chunks rather than per-tick position updates. When a chunk enters a client's relevant area, the server sends its structures. Subsequent messages contain only changes and removals.

Forgetting an object because it has left the client's interest area is different from destroying it. The client can discard an out-of-range structure while the server continues to preserve it in the world.

World deltas and structure changes are tracked so that clients can recover from missing updates and receive the latest state when a chunk becomes relevant again.

Bullets and short-lived effects can be sent as events rather than streamed as ordinary pixels every tick. Clients animate those events locally, while the server remains responsible for the actual outcome.

#### **Interest Management and Performance**

The server uses a spatial grid to find pixels near a player's own pixels and camera view. Each client receives only the relevant world changes and entity updates.

Structures use a tile occupancy map for collision and a per-chunk index for spatial queries and replication. This keeps them separate from the pixel spatial grid and avoids treating stationary objects as moving entities.

Performance optimization begins with measurement. Tick duration, collision work, active projectiles, structure lookups, and bytes sent per client can be tracked before expensive systems are rewritten.

Potential optimizations include:

- Simulating only active areas near players where appropriate.
- Sleeping idle pixels and waking them on relevant events.
- Updating distant pixels less frequently.
- Updating only structures with active capabilities.
- Scheduling production and delayed actions instead of scanning every tick.
- Reducing unnecessary decision and attribute calculations.
- Using NumPy arrays for bulk movement if object-based updates become a bottleneck.
- Profiling with `cProfile` before introducing Numba, Cython, or other optimizations.

Entities and projectiles outside a player's radius may continue simulating, depending on the activity level and server performance. Distance should affect simulation detail where necessary, but not arbitrarily change important outcomes.

#### **Fog**

Fog determines what each nation knows about the world. Exploration and current visibility are separate states, allowing civilizations to retain geographic knowledge after leaving an area.

Each nation maintains three concepts:

- **Explored:** Tiles that the nation has seen at least once. Exploration persists and is saved with the world.
- **Visible:** Tiles currently revealed by the nation's vision sources. Visibility changes as pixels and structures move, spawn, or disappear.
- **Preview:** The full map displayed during colony placement. Preview is a game phase, not permanent exploration data.

Pixels and structures can act as vision sources through their configured vision radius. When a source changes position or is removed, the server updates visibility using reference counts so that overlapping vision sources continue to work correctly.

Initial visibility uses a radius around each source. Line-of-sight obstruction by opaque terrain and structures can be added as an extension, allowing vision rules to become more sophisticated without changing the basic exploration model.

Newly visible tiles become explored. Explored tiles that are no longer visible retain their remembered terrain, while unexplored tiles are rendered as dark, unknown territory.

The server filters replicated pixels using the viewer nation's visibility and existing stealth rules. Enemy entities outside visible territory are not sent to the client merely because they fall within its camera or interest area.

This filtering also applies to commands. Attacks, interactions, and inspections cannot target entities the player is not permitted to see, and placement or launch commands can reject targets in unexplored territory.

Terrain synchronization respects exploration. Changes in visible territory are delivered normally, while changes in explored but currently hidden territory are withheld. When the nation sees the area again, the latest terrain state is synchronized so that remembered terrain becomes current.

Each client receives only its own nation's exploration and visibility data. Exploration is stored as compact per-chunk bitmasks, and only changed chunks need to be sent during normal play.

The client caches fog overlays by chunk and redraws them when the corresponding visibility data changes. Rendering, hovering, and selection all use replicated state rather than direct access to the server's world objects.

During placement, fog is disabled so players can choose their colony using the full terrain preview. When playing begins, visibility is initialized from the colony and starting pixels. Preview does not permanently reveal or explore the map.

The initial implementation allows clients to generate the complete terrain from the shared seed. Fog controls what the game displays and what dynamic information the server reveals, but it does not make the underlying generated terrain secret from a modified client.

### **Colony Placement**

Every player establishes a colony belonging to their nation. The host starts the game from the lobby, after which the server generates the world and waits for connected clients to confirm their terrain checksums. Once the world is ready, the server enters the placement phase and begins a countdown.

During placement, players can choose a location for their colony and see the entire map without fog. A valid location must be within the world bounds, have suitable terrain, fit the colony footprint, and maintain the required distance from other colonies.

Colony placement is validated and committed by the server. Competing requests are resolved deterministically, and occupancy and spacing are checked again when the colony is created.

The colony creation pathway is shared by normal placement, automatic placement, and developer tools. It creates the colony, assigns ownership, places starting pixels, initializes resources, and records the colony's identity and position.

Once placement finishes, normal gameplay commands become available and fog is initialized for each nation.

Developer mode provides a separate server-side path for testing. It can skip readiness checks, shorten placement, automatically place colonies, and optionally reveal the map. Privileged developer commands are unavailable to ordinary clients.

### **Saving and Persistence**

The world can be saved using its seed, generation settings, tile delta log, pixel states, player data, and blueprints. Pixel states must be serializable using ordinary data types rather than Python-specific object serialization.

Player data includes currency, technology unlocks, saved blueprints, nation information, and other progression.

Structures are saved with their runtime state and a separate structure ID counter. Their occupancy and chunk indexes are rebuilt when the world loads, ensuring that placement and collision use the same registration logic as newly created structures.

Structure state includes information such as current health, door states, inventories, and production progress. Reloading a world should preserve these details rather than resetting structures to their blueprint defaults.

Projectiles can also be saved with their motion, payload, impact settings, ownership, and lifetime. Short-lived cosmetic projectile events do not need to persist across reconnects.

Exploration is saved per nation and chunk. Current visibility is rebuilt from vision sources when the world loads, while remembered exploration is restored from the saved data.

Entity and structure identity follows explicit lifecycle rules. A resource becoming a structure receives a structure ID, and removing a structure retires that ID. If a structure becomes a pixel, the new pixel receives its own ID and can record the original structure ID as its origin. A pixel launched as a projectile retains its existing identity when it lands.

Structures persist when their owners disconnect. Reconnecting players regain control through their existing player identity, while abandoned structures remain part of the world unless another gameplay rule explicitly changes them.

The server periodically saves the world and saves again during a clean shutdown. The save format includes a version so that future changes to the serialized world can be handled explicitly.

### **Development Order**

Development proceeds in phases, with each phase building on working systems.

1. **Shared Server Foundations:** Establish game phases, nation records, command gating, command correlation, and protocol versioning.
2. **Headless Simulation:** Separate simulation from rendering, introduce stable pixel IDs and ownership, and make state serializable.
3. **Deterministic World:** Ensure the same seed produces the same terrain and implement checksums.
4. **Protocol and Transport:** Connect a client to a server and verify that both agree on the world.
5. **Main Menu and Lobby:** Support singleplayer, hosting, joining, nation customization, readiness, and shared generation settings.
6. **Colony Placement:** Implement the placement countdown, colony creation, starting resources, and automatic placement.
7. **Fog:** Add nation exploration, visibility filtering, remembered terrain, fog rendering, and persistence.
8. **Commands and Behaviors:** Implement movement, selection, attack, transfer, drop, spawn, place, launch, and blueprint editing.
9. **Structures:** Implement structure definitions, placement, occupancy, collision, capabilities, replication, and persistence.
10. **Projectiles:** Add traveling projectiles using shared collision and damage systems, with event-based and state-based replication.
11. **World Synchronization:** Synchronize tile changes, structures, and nearby pixels while enforcing visibility rules.
12. **Interest Management:** Improve spatial queries, reduce unnecessary updates, and handle reconnection.
13. **Smoothness:** Interpolate movement, quantize updates, and handle missed messages and reconnects.
14. **Performance:** Measure bottlenecks and optimize only where needed.
15. **Persistence:** Verify restoration of worlds, players, nations, structures, projectiles, exploration, and blueprints.
16. **Desktop Distribution:** Package and test clients on supported operating systems.
17. **Web Support:** Optionally add a browser client without replacing the server architecture.

### **TODO**

- Add pixel inspection for attributes and inventory.
- Restrict pixel property editing to the player's territory.
- Give every pixel a stable unique ID and an owner.
- Create Gatherer, Scout, and Warrior as configurable presets.
- Implement resource extraction, pickup, consumption, production, transfer, and placement.
- Implement spawning, including resource costs and cooldowns.
- Add the shared game phase and nation systems.
- Implement the main menu, lobby, nation customization, and host controls.
- Add deterministic colony placement, starting resources, and automatic placement.
- Implement fog, persistent exploration, and visibility-filtered replication.
- Implement structure blueprints, footprints, rotation, placement, removal, and occupancy.
- Add shared terrain, structure, and pixel collision.
- Implement structure doors, storage, production, and damage.
- Add structure replication, lifecycle handling, and persistence.
- Implement traveling projectiles, payloads, collision, impact effects, and projectile replication.
- Integrate projectile damage with the shared damage system.
- Add graph grammars and more advanced construction rules.
- Introduce CPU civilization generation and decision-making.
- Implement cooperative and adversarial action claims.
- Add relationships, memories, and needs.
- Decide how much simulation continues outside player visibility.
- Implement world deltas, structure synchronization, and entity interest management.
- Implement persistence for worlds, player progression, nations, structures, exploration, and blueprints.
- Measure server performance with thousands of pixels, structures, and projectiles before optimizing.

### **Open Questions**

- Should every pixel have one primary action per tick, with reactions processed separately?
- How should cooperating entities determine whether their graph grammars can blend?
- What happens when two incompatible civilizations try to build in the same area?
- How much should distant civilizations simulate when no player is nearby?
- How are research, currency, and blueprint editing costs balanced?
- Can players research attributes by observing existing pixels, experimenting, or reverse-engineering other civilizations?
- How do we prevent arbitrary combinations of attributes from creating runaway or broken behaviors?
- Should structures and pixels always use separate ID namespaces?
- Should colony placement remain available until the countdown ends, or become permanent after the first placement?
- Should the host role transfer automatically when the host disconnects?
- Is it acceptable for clients to know the complete generated terrain even when fog hides it?
- Should projectiles support gravity and a height axis, or remain entirely top-down?
- Should spies disguise themselves as other pixels, or simply use a different form of invisibility?
- Should structure construction take time, or should structures appear immediately when placement succeeds?
- How should structure materials interact with projectile penetration, bouncing, and destruction?
- How should long-lived projectiles and embedded payloads behave when a world is saved or a player disconnects?

The ultimate goal is a world that behaves like a living system. The engine supplies the rules, the environment supplies the constraints, and the players supply the engineering. Civilizations, creatures, machines, structures, and conflicts emerge from the same small set of configurable building blocks.