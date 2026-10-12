# **Sim World**

This engine is meant to give you the tools to recreate any fantasy land, from Lord of the Rings to Dune to Conway's Game of Life. The key is that all aspects, from world generation to civilizations to entities, are customizable and allow for complex behaviors with simple implementation.

The world is generated procedurally, populated by autonomous entities, and simulated before the player enters. Civilizations emerge as entities move, gather resources, build structures, cooperate, fight, trade, and adapt to their environment. The player can pause the simulation and join the world at any time, becoming part of an ecosystem that already exists.

The core idea is that **everything is a pixel**. A pixel is a single entity with properties, behaviors, and motivations. Players research new attributes, modify existing ones, and combine them to engineer their own creations. A pixel standing on stone and extracting stone might be called a miner by one player and a stone factory by another. A pixel that eats grass might be a cow, a biological machine, or something entirely different.

The game provides presets as starting points, not fixed classes. Players are encouraged to experiment, discover combinations, and create their own solutions. There are no hard-coded warriors, animals, factories, or civilizations. These emerge from the properties and behaviors of pixels and how they interact with the world.

The key files are below:


### **Game Engine**

    game.py

    main.py

    menu.py

    simulation.py

This is responsible for running the game and coordinating the simulation. `Simulation` owns the world, `entityManager`, `systemRunner`, `eventBus`, and seeded random number generator. It advances the world independently of rendering, allowing the same simulation to run in singleplayer, multiplayer, or headless mode. The player can pause the simulation, inspect the world, and take control without resetting the existing world.


### **Rendering**

    camera.py

    entity_renderer.py

    renderer.py

    world_renderer.py

    rendering/selection.py

The rendering system is responsible for displaying the world and interpreting player input. Camera manages viewport position, zoom, mouse dragging, coordinate conversion, visible tile bounds, and hovered-tile detection. Renderer draws the visible world and entities, using cached sprites or procedurally generated appearances. Entity rendering reads from the client's replicated state rather than directly accessing the simulation.

The world uses a fixed `TILE_SIZE` of 32 pixels. Zoom changes displayed tile and entity sizes without changing world coordinates. Rendering runs independently of simulation ticks, allowing a 20 Hz simulation to render at 60 FPS or higher. Entity positions are interpolated between server updates to keep movement smooth.

Mouse interaction is part of the control system. Players can click a pixel to issue an action, drag to select multiple pixels, right-click to issue contextual commands, and recall selected pixels to a home point. The same command system supports both direct control and autonomous behavior.


### **World Generation**

    generator.py

    noise.py

    world.py

The `WorldGenerator` creates a complete world from a `GenerationSettings` configuration. Generation begins with terrain and procedural maps, then creates continents, elevation, water, temperature, wetness, biomes, and environmental features.

The world is generated before civilizations are introduced. Terrain and biome information determine which resources are available.


### **Maps**

    map_types.py

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

    tile_types.py

Tiles represent the physical world. A tile contains attributes describing its material, shape, surface, biome, temperature, permeability, opacity, hardness, structural role, and tags.

Each tile acts as a feature vector rather than simply a visual block. Systems use these attributes to determine what can move through a tile, what resources it contains, what can be extracted from it, and what can be built on it.

Tiles may contain resources, and resources may also exist as items carried by pixels or stored in structures. A resource can therefore exist as part of the environment, as an inventory item, or as a material used in construction.

All world edits go through a single world modification function. This allows changes to be recorded, synchronized across multiplayer clients, and saved to disk.


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

There is only one entity type: **Pixel**. Every pixel owns data describing its current state, attributes, inventory, ownership, identity, and active orders. Independent systems determine how those properties interact and what the pixel does autonomously.

A pixel can become a warrior, bullet, spawner, plant, miner, spy, bomb, animal, vehicle, mechanism, or something that has no real-world equivalent. These are not separate entity classes. They are combinations of properties, actions, reactions, and motivations.

Pixels can move, perceive their surroundings, gather resources, attack, build, reproduce, transport other pixels, communicate, and influence one another. Their capabilities depend on the attributes they have unlocked and the parameters assigned to them.

Players begin with a small set of presets, such as Gatherer, Scout, and Warrior. These are saved attribute configurations rather than special classes. Players can research their components, adjust their parameters, and save their own blueprints. Creating a new kind of pixel is an engineering problem rather than a class-selection problem.

All pixels have stable unique IDs and an owner. The owner determines who can issue commands to them, while their attributes and behaviors determine what they can do autonomously.


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

Systems operate on shared entity data. This keeps the engine extensible: adding a new attribute or behavior should not require rewriting unrelated systems.


#### **Behaviors and Actions**

Behaviors are reusable, data-driven rules. They can be activated autonomously by the `DecisionSystem` or pinned to an entity through a player command. A command is therefore an instruction to perform a behavior, not a separate implementation of that behavior.

Here are three world-changing actions of note:

- **Spawn:** Creates a new pixel at a location. A cannon spawns a projectile, a creature produces an egg, and a factory creates a vehicle. Spawning can consume resources or energy and may have a cooldown.

- **Drop:** Consumes an item or resource to create or modify something in the world. A builder constructs a wall, a worker places water into a tile, and a unit deploys a carried turret.

These actions are deliberately separate. Spawning creates an entity, transferring moves something that already exists, and placing materializes something from inventory or modifies the environment.

Behaviors can also be combined with conditions and reactions. For example, a pixel might extract stone only while standing on stone, transfer it when its inventory is full, and return home when its energy is low.


### **Civilizations and Structures**

Civilizations are not hard-coded objects with fixed rules. They emerge from groups of pixels that share motivations, relationships, resources, building preferences, and patterns of behavior.

For autonomous players, (CPU), structure preferences are motivations rather than mandatory building templates. A CPU might prefer defensive structures, organic growth, dense settlements, isolated shelters, or no structures at all. Its preferences influence decisions without completely determining them.


#### **Graph Grammars**

Graph grammars define the rules used to generate and extend structures. They are predefined and data-driven, allowing players and entities to combine building rules without requiring arbitrary scripting.

Example grammars include:

- Village architecture

- City architecture

- Forest and organic growth

- Defensive fortifications

- Industrial structures

- Haunted or corrupted architecture

Each grammar defines possible components, connection rules, structural constraints, and required or preserved block tags. Building blocks carry attributes describing their material, shape, role, and compatibility.

These constraints allow grammars to blend. A defensive settlement and an organic forest civilization might combine stone walls with living structures if their rules permit it. Incompatible components remain separate or require a valid transition.


#### **Autonomous Construction**

Construction is an action performed by pixels, subject to the same simulation rules as movement, combat, and trading. Each entity performs at most one primary action per simulation turn.

When an entity wants to build, it evaluates the target area, available materials, its structure preferences, and existing construction claims.

- If no other entity is building there, construction can proceed.

- If another entity is building there and the two cooperate, their graph grammars can blend into a shared structure.

- If they do not cooperate, the entities may compete for the area, negotiate, retreat, or fight, depending on their attributes, relationships, and available behaviors.

Cooperation is determined by more than a single faction ID. Shared goals, trust, compatible structure preferences, resource needs, and past interactions can all contribute to the decision.

Construction remains constrained by resources, terrain, grammar rules, and the entity's available actions. Civilizations therefore emerge through repeated local decisions rather than being generated as finished settlements.


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

- **Build (Action):** Places tiles or structures using graph grammar rules.

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


### **Multiplayer**

**server/**

    client.py

    commands.py

    deltas.py

    interest.py

    protocol.py

    server.py

The server owns the truth. Clients send commands, never authoritative state. The server validates commands, advances the simulation, and distributes updates to connected players.

The world is generated from a shared seed and settings. Clients generate the same terrain locally and verify it using a checksum. World changes are transmitted as deltas instead of repeatedly sending the entire world.

The simulation runs at a fixed rate of approximately 10–20 ticks per second, independently of the rendering frame rate. The transport uses WebSockets and asyncio, while messages are encoded with MessagePack to keep the protocol compatible with future non-Python clients.

The renderer reads only from the client's replicated state. It never reads directly from the authoritative `Simulation`.


#### **Commands**

Players interact with the world by sending commands. The server checks ownership, permissions, resources, unlocks, targets, and other requirements before applying them.

- **Move:** Assigns a movement order.

- **Act:** Interprets a click as a contextual action, such as moving, attacking, spawning, dropping, or transferring.

- **Box:** Selects a group of pixels for a command.

- **Place:** Creates a pixel or structure using a blueprint and any required resources.

- **Spawn:** Instructs a pixel to create another pixel.

- **Transfer:** Moves existing resources or entities between inventories or locations.

- **Drop:** Materializes a carried resource as a world object.

- **Attack:** Assigns an attack order against a valid target.

- **Edit Property:** Changes a pixel's configuration when the player has the necessary unlocks and currency.

- **Save Blueprint:** Saves a pixel configuration for later use, subject to the applicable requirements.

Autonomous pixels and player-controlled pixels use the same underlying behaviors. Player commands override or guide those behaviors without requiring separate implementations.


#### **World Synchronization**

World changes are recorded through a delta log. Deltas are grouped by chunk, and clients receive changes for chunks within their relevant area.

Pixel visibility is handled separately. The server tracks which pixels each client knows about and sends full state when a pixel enters visibility, changed fields when it updates, and a leave message when it is no longer visible.

Visibility rules are enforced on the server so invisible pixels and spies do not automatically reveal themselves to enemies.

Bullets and short-lived effects are sent as events rather than streamed as ordinary pixels every tick. Clients animate those events locally.


#### **Interest Management and Performance**

The server uses a spatial grid to find pixels near a player's own pixels and camera view. Each client receives only the relevant world changes and entity updates.

Performance optimization begins with measurement. Tick duration and bytes sent per client are logged before expensive systems are rewritten.

Potential optimizations include:

- Simulating only active areas near players.

- Sleeping idle pixels and waking them on relevant events.

- Updating distant pixels less frequently.

- Reducing unnecessary decision and attribute calculations.

- Using NumPy arrays for bulk movement if object-based updates become a bottleneck.

- Profiling with `cProfile` before introducing Numba, Cython, or other optimizations.

Entities outside a player's radius may continue simulating, depending on the activity level and server performance. Distance should affect simulation detail where necessary, but not arbitrarily change important outcomes.


### **Saving and Persistence**

The world can be saved using its seed, generation settings, tile delta log, pixel states, player data, and blueprints. Pixel states must be serializable using ordinary data types rather than Python-specific object serialization.

Player data includes currency, technology unlocks, saved blueprints, and other progression. The server periodically saves the world and saves again during a clean shutdown.

The persistence system should support restoring an existing civilization rather than generating a new world every time a player joins.



### **Development Order**

Development should proceed in phases. Each phase must work before the next begins.

1. **Headless Simulation:** Separate simulation from rendering, introduce stable pixel IDs and ownership, and make state serializable.

2. **Deterministic World:** Ensure the same seed produces the same terrain and implement checksums.

3. **Protocol and Transport:** Connect a client to a server and verify that both agree on the world.

4. **Singleplayer Server:** Run singleplayer through the same client/server architecture.

5. **Commands and Behaviors:** Implement movement, selection, attack, transfer, drop, spawn, place, and blueprint editing.

6. **World Deltas:** Synchronize tile changes without resending the world.

7. **Interest Management:** Synchronize nearby pixels and enforce visibility rules.

8. **Smoothness:** Interpolate movement, quantize updates, and handle reconnection.

9. **Performance:** Measure bottlenecks and optimize only where needed.

10. **Persistence:** Save worlds, players, unlocks, and blueprints.

11. **Desktop Distribution:** Package and test clients on supported operating systems.

12. **Web Support:** Optionally add a browser client without replacing the server architecture.


### **TODO**

- click to view attributes. click to view inventory

- you can edit a pixel's attributes IF its in player territory

- Give every pixel a stable unique ID and an owner.

- Create Gatherer, Scout, and Warrior as configurable presets.

- Implement resource: 
    - extraction
    - pick up
    - consumption
    - production
    - placement

- Make all commands reusable as autonomous behaviors.

- Implement spawning, including resource costs and cooldowns.

- Implement graph grammars, building blocks, and structural constraints.

- Introduce CPU generation and decision making.

- Implement cooperative and adversarial action claims.

- Add relationships, memories, and needs

- Decide how (and how much) simulation continues outside player visibility.

- Implement world deltas and entity interest management.

- Implement persistence for worlds, player progression, and blueprints.

- Measure server performance with thousands of pixels before optimizing.


### **Open Questions**

- How large should the world and its chunks be?

- How many players should a server support?

- How many pixels should each player control?

- Should every pixel have one primary action per tick, with reactions processed separately?

- How should cooperating entities determine whether their graph grammars can blend?

- What happens when two incompatible civilizations try to build in the same area?

- How much should distant civilizations simulate when no player is nearby?

- How are research, currency, and blueprint editing costs balanced?

- Can players research attributes by observing existing pixels, experimenting, or reverse-engineering other civilizations?

- How do we prevent arbitrary combinations of attributes from creating runaway or broken behaviors?

- What are the win conditions, if any, or should the world remain an open-ended simulation?

The ultimate goal is a world that behaves like a living system. The engine supplies the rules, the environment supplies the constraints, and the players supply the engineering. Civilizations, creatures, machines, and conflicts emerge from the same small set of configurable building blocks.
