# Sim World
This engine is meant to give you the tools to recreate any fantasy land, from Lord of the Rings, to Dune, to Conways Game of Life. The key is that all aspects, from world generation to civilizations to entities, are customizable and allow for complex behaviors with simple implementation. 

The key files are below:
### Game Engine:
- game.py
- main.py
- menu.py

    This is responsible for running the game. 

### Rendering:
- camera.py
- renderer.py

    The rendering system is split between camera.py and renderer.y: Camera manages the viewport position, zoom, keyboard movement, mouse dragging, coordinate conversion between world pixels and screen pixels, visible tile bounds, and hovered-tile detection, while Renderer owns the Pygame display and uses the camera to draw only the currently visible portion of the world. The world uses a fixed TILE_SIZE of 32 pixels, with each tile converted from world coordinates to screen coordinates through Camera.world_to_screen(), and zooming changes both the displayed tile size and entity sizes without changing the underlying world coordinates. Renderer.render() chooses between the normal world view, a map-debug view, or a biome-debug view, then optionally draws entities on top; entities are sorted by their sprite layer before rendering and can use either cached image sprites or simple procedurally drawn characters such as ants. Map and biome debug modes are cycled with M and B, respectively, while the camera handles WASD movement, left-mouse dragging, and mouse-wheel or keyboard zooming. Images are cached in self.images so each image path is loaded only once, and biome debug colors are deterministically generated from the biome name so they remain consistent between frames. The main rendering loop should therefore follow the pattern of processing events with handle_events(), advancing the camera with update(delta_time), rendering the current world/debug state with render(...), and using tick() to obtain frame delta time and maintain the desired FPS.

### World Generation:
- generator.py
- noise.py
- world.py

    The WorldGenerator creates a complete World from a GenerationSettings configuration. Generation starts by creating a defined "water"-filled world, generating arbitrary procedural maps through MapManager, then sequentially generating things like land, biomes, water features, vegetation, entities, etc. For example, ocean generation uses the height map to replace specific tiles with water tiles. Similarly, desert tiles use wetness and temperture maps to generate sand tiles.  

### Maps:
- map.py
- map_types.py

### Features:
- feature.py
- featureManager.py
- featureSelectionStrategy.py

    Features are anything placed in the world (biomes, structures, etc). A feature takes maps and tiles, and chooses what to place based on noise levels. Blending can also be set for features. 
    favor_strength: weight is 1 + favor_strength * noise, clamped at 0. Perlin noise mostly stays within about ±0.7, so 0.6 gives weights of roughly 0.6 to 1.4. Grassland at 0.6 gets a 40% penalty in its worst regions, which is enough for its neighbors to win there. Use 1.0 or more for dramatic swings.
    favor_scale: controls how big the favored and suppressed regions are. Smaller values give continent-sized regions, and larger ones give patchy variation. Give commonly competing features different scales so their favored regions don't line up.

### Entities
    ok, i have a new concept for entities. I want there to be only 1 entity called pixel. First, pixels are kind of like pikmin, spawning and then moving around randomly. But, by chaning by changing its properties/behaviors, it can become anything: warriors, bullets, spawners, plants, miners, spies, bombs, livestock, birds, mechanisms, etc. The end goal is to make pixel something players can add/edit properties/behaviors of IN GAME, in order to create everything in the game. In that way, you unlock the ability to edit certain properties/behaviors, and then editing those properties/behaviors will cost currency. Additionally, players can save configs IN GAME, to create their own 'blueprints' that can be used to instantly spawn that pixel. features include:
    - interacting with mouse clicks
    - being able to get aggroed
    - being able to spawn other pixels
    - moving around
    - being aware of its environment
    - visibility (can turn invisible)
    - gathering resources
    - attacking other pixels
    - influencing other pixel's behaviors
    This game will then be like Civ 5 or Polytopia, in that you build civilizations and control units, but in this case it is more open world. Player compete to grow their civilization and complete one of a couple of objectives. 

### Tech Tree:
Every properties/behavior should be one of four kinds, so players learn one grammar:

Body: passive stats like health, speed, size, lifespan and capacity.
Sense: what the pixel can perceive (range, filter, hidden things).
Action: something it can do (move, extract, attack, spawn, build).
Reaction: "when X happens, do Y" (on death, on contact, on timer, when hurt). This is the "edge of coding" part, and it stays data-shaped, with no scripting.

Player idea	Decomposed
Stone factory	Immobile, stands on a stone tile, converts tile → stone resource (cost: energy)
Cow	Wanders, eats pixels tagged "grass" → energy, turns energy → milk resource, spawns a calf when energy is high
Bomb	Moves toward the nearest pixel, reaction: on contact → area damage + die
Spy	Stealth, high speed, sight, no attack, reaction: on seeing → report to owner
Spawner	Immobile, converts resource → new pixel from a saved blueprint
Plant	Immobile, converts sunlight tile → energy, spawns seeds on a timer

### Tiles:
- tile.py
- tile_types.py

TODO: 

- how to optimize pixel behavior/ make it scale well. Are there games that can run on a basic machine (mac/pc) that run this many entities? (fortnight)
- idea of trading by having pixels drop items to other pixels. 
- being able to trigger events using mouse (click pixel, make it drop object. click in general area of pixels, make them attack, drag click highlight pixels, make them come back to base)
- Make spawner entity, player id
- spawn pixels, make them fight
- make pixels be able to carry other pixels
- 


