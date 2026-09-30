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
- entity.py
- entityManager.py
- entity_types.py
- entityFactory.py
- attributeSystem.py
- decisionSystem.py
- memorySystem.py
- needSystem.py
- relationshipSystem.py
- systemRunner.py

    This looks complicated, but entity behavior is quite simple. The entity has a list of tasks it wants accomplish, scores those tasks, chooses one, then tries to accomplish that task. Every so often, it reevaluates and the cycle loops. 

    This somewhat convoluted cycle helps me accomplish 3 things:
    1) The entity system us so abstract that I can (somewhat) easily implement ANY behavior. This is not just simple enemy move, dodge, track behavior, but also more niche concepts, like conways game of life rules, or population growth simulation, etc. I want to be able to create anything, and have them interact. 

    2) A big goal of this project is to have entities build complex and INTERESTING procedural structures. I want to use wave function collapse ANDO/OR graph grammers. And i dont want them to simply generate, i want them to ATTEMPT to build them, which can go wrong, and also get angry if other entities build in their territory, or gather resources, etc. 

    3) This system allows for easy *emergent behavior*, through interactions, conflict, and cooperation. Entities are able to store memory, have a personality, and react to others.

### Tiles:
- tile.py
- tile_types.py

TODO: make sprites for tiles
TODO: make more variety in mapsssss. I dont want it to all be the same thing, some regions need some specifics....
