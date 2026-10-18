# Part 3 of 3: Structures

Build order: 0. Entity foundation (`0_entity_foundation_todo.md`), 1. Actions (`1_actions_todo.md`), 2. Items (`2_items_todo.md`), **3. Structures (this file)**.

Structures are plain **entities** (`kind` "structure") on the entity foundation: a base entity from a shared template plus one small `structure` component `{resource}`. They have no traits, needs or task, so they are in no awake set and cost no per-tick time. There is no separate block layer: if thousands of blocks ever cost too much, one can be added later behind the same `build_structure` and `modify` interface (step 3.5).

Needs from the other files:
- From `0_entity_foundation_todo.md`: the roster (Part 1), templates and `own()` (Part 3), the `static` flag (4.1) and the cell index (4.3). Without the foundation the steps still work on the old `Entity`, only slower and bigger.
- From `1_actions_todo.md`: the ops, reactions with `drops`, and the pipeline (Parts 1 to 4).
- From `2_items_todo.md`: resources, `make_item`, and the `spawn` op (Parts 1 and 2).

Conventions and "Do / Done when": same as the actions file. Run every existing check after each step.

---

## The idea in one page

A **structure** is a resource placed in the world as a block (like Minecraft). Unlike an item, it **inherits properties from its resource**: stone is strong, wood burns.

- A resource file may have a `structure` block: `"structure": {"max_health": 4, "props": {"flammable": 0.8}, "tags": ["block"], "blocks_movement": true, "blocks_sight": false, "on_break": [{"requires": [{"on": "source", "stat": "inventory:axe", "op": ">", "value": 0}], "fraction": 1.0}, {"fraction": 0.5}]}`. No block, no structure (gold or seeds cannot be placed).
- At load time, each resource with a `structure` block is compiled into **one shared template** (`structure_wood`, `structure_stone`) from `content/entities/structure.json` merged with that block. The template holds the health, props, tags, sprite and the `drops` reaction that gives the resource back. Every wood block shares the `structure_wood` template, so a block costs only its base fields and a `structure` component.
- A structure is placed once at the centre of a grid cell and never moves, so nothing snaps it per tick (the `snap_to_grid` prop is not used).
- Placing one is the `spawn` op with `"resource": "wood"`, paid by the action's `cost` (`inventory:wood`).
- Breaking one is `modify health` (any attack or a `break` action, by anyone). The template's reactions drop items of its resource and remove it. How much comes back is set in the resource file by `on_break` rules (step 2.4). Nothing special in the action. Reactions fire on any entity that has them, awake or not, so a block never needs to be woken.

**JSON only:** a new structure is one resource file with a `structure` block. A new structure kind with extras (a door, a chest) is another JSON entity file that has a `structure` key. No Python.

---

## Part 1: The data

- [ ] **1.1 The `structure` block in resource files**
  **Do:** extend the resource loader (items Part 1) to validate the block: allowed keys `max_health` (> 0), `props` (numbers), `tags` (strings), `blocks_movement`, `blocks_sight` (bools), `sprite_id`, `on_break` (a list of rules, see step 2.4). Refuse unknown keys with the file name in the message. Fill in `wood.json` and `stone.json` (stone: `max_health` 10, wood: `max_health` 4, `flammable` 0.8).
  **Done when:** `tests/sim/structures/check_resources.py` loads both and refuses bad blocks.
- [ ] **1.2 The `structure` entity file**
  **Do:** `content/entities/structure.json`: `kind` "structure", tag `structure`, `size` 1, no traits, no needs, `static`, and one `drops` entry that gives the resource back:

        "drops": {"stat": "health", "at_zero": {"$resource": 1}}

  `$resource` is filled in when each resource's template is compiled (step 1.3). The resource's `on_break` rules (step 2.4) replace this default when present. The `structure` key in an entity file switches the `structure` component on.
  **Done when:** the file loads through the template compiler (foundation 3.4) and has no per-tick cost.
- [ ] **1.3 One template per resource**
  **Do:** `sim/structures/templates.py`: after the resources load, for each resource with a `structure` block, merge it over `structure.json` (health, props, tags, sprite, flags as props, `$resource` filled in) and compile it once as `structure_<resource>`. Register them with the entity factory so `create_pixel` can build them by name. Reloading resources rebuilds the templates; existing blocks keep the template they were built from (foundation decision).
  **Done when:** `structure_stone.max_health` is 10 and `structure_wood` has `flammable` 0.8; two wood blocks share one template object; a resource file with no `structure` block makes no template.
- [ ] **1.4 `build_structure`**
  **Do:** `sim/structures/structures.py`: `build_structure(context, resource, x, y, owner) -> structure | reason`. Steps: look up the template (`not_placeable`); snap `x, y` to the cell centre once, using the single constant `CELL_SIZE` (32, the tile size, for now); refuse if the cell is outside the world (`out_of_bounds`), the tile is not walkable or is water (`bad_ground`), or the cell index (foundation 4.3) already holds a structure (`occupied`); create the entity through `create_pixel` from the template so the 9.9 limits apply (`limit`); set its `structure` component `{resource}` and add it to the cell index.
  **Done when:** `check_structures.py` (which also runs once with `CELL_SIZE` set to 16 to prove nothing else hard-codes 32): stone gets more health than wood, a second block in one cell is refused, water is refused, a resource with no structure block is refused.

## Part 2: The op and the actions

- [ ] **2.1 `spawn` with `resource`**
  **Do:** extend `sim/ops/spawn.py` (items Part 2) with the `resource` field, which calls `build_structure` at `at`. The op stays "creates a new entity".
  **Done when:** a test action spawns a stone block and the reason strings come back from `build_structure`.
- [ ] **2.2 `place_block`**

        {"id": "place_block", "target": {"type": "point", "range": 1}, "params": {"resource": {"default": "wood"}}, "cost": {"inventory:$resource": 1}, "time": 0.5,
         "effects": [{"op": "spawn", "resource": "$resource", "at": "target"}]}

  **Do:** make the action loader accept `$param` in a `cost` key. A failed placement must not charge the cost: pay only if the op succeeded (`"pay": "success"` on this action).
  **Done when:** a commanded pixel with 3 wood places a block and has 2 left; with 0 wood it fails `cannot_afford`; on an occupied cell it fails `occupied` and keeps its wood.
- [ ] **2.3 Breaking**

        {"id": "break", "target": {"type": "pixel", "filter": [{"stat": "tag:structure", "op": ">", "value": 0}], "range": 1}, "params": {"damage": {"default": 1, "minimum": 1, "maximum": 20}}, "time": 0.5, "repeat": "target",
         "effects": [{"op": "modify", "on": "target", "stat": "health", "add": "-$damage"}]}

  Anyone may break any structure: there is no owner or enemy check.
  **Done when:** breaking a wood block takes about four hits, leaves one wood item, removes the block, and takes it out of the cell index (it can be built on again). Structures are not `hostile`, so units ignore them; `attack` damages them only if its filter matches their tags.
- [ ] **2.4 Configurable break returns (`on_break`)**
  **Do:** a resource's `structure.on_break` is a list of rules, tried in order; the first whose `requires` all pass applies (a rule with no `requires` always passes). Each rule has `fraction` (0 to 1 of the normal amount, default 1) and optionally `amount` (items, default 1). `requires` use the usual stat conditions plus `"on": "source"` to read the breaker, so "holding a pickaxe" is `{"on": "source", "stat": "inventory:pickaxe", "op": ">", "value": 0}`; a tag, a status or a trait work the same way. Extend the reaction `if` (actions Part 3) so it can read the event's `source`. The template compiler turns the rules into reactions on the shared template. A fractional result rounds down and the leftover fraction is rolled with the seeded rng (0.5 of 1 item is a 50% chance of one), so it stays deterministic. No rule matching means nothing drops. With no `on_break` key the default is 100% (the `drops` entry from step 1.2).
  **Done when:** `check_structures.py` with a block that returns 100% with an axe and 50% without: 200 seeded breaks without give about 100 items, 200 with give 200, two runs are identical, and a resource with `on_break: []` drops nothing.
- [ ] **2.5 Properties really come from the resource**
  **Do:** a test that builds one block of every resource and checks each stat equals what the resource file says; add a new resource file with different values and check it works with no code change.
  **Done when:** it passes.

## Part 3: Make thousands of blocks cheap
Most of this comes free from the foundation; these steps check it and add what is structure-specific.

- [ ] **3.1 Never visited**
  **Do:** confirm a structure is in no roster set, is never aged (age comes from `born_tick`), and appears in proximity scans only through the static layer when a filter asks for `tag:structure` (foundation 4.2). Nothing to wake: damage runs through `modify` and the template's reactions.
  **Done when:** 5,000 blocks add under 1 ms to the tick in `profile_sim` (compare the same world with and without).
- [ ] **3.2 The cell index stays right**
  **Do:** the cell index (foundation 4.3) is updated in `build_structure` and on `entity_removed`. Also rebuild it from the entities on load.
  **Done when:** the index matches a full scan after a long random build-and-break test.
- [ ] **3.3 Own limits**
  **Do:** add `max_structures_in_world` and `max_structures_per_player` to `Limits`, counted separately from capable entities and from items (so walls cannot starve units, and the reverse). Refuse with `limit`; count `structure_refused`.
  **Done when:** `check_limits` covers both caps.
- [ ] **3.4 Replicate once**
  **Do:** structures are `static` (foundation 4.1): the server sends one when it enters a client's view and again only when its health changes or it is removed. Send its `structure` component (`resource`) so the client picks the sprite. The client skips interpolation for static entries.
  **Done when:** bytes per client per tick with 5,000 visible blocks stay flat (check with the metrics from 9.1).
- [ ] **3.5 Save and load, and the cheap-enough check**
  **Do:** blocks save as the template id, base fields and the `structure` component (foundation 3.7); loading rebuilds the cell index. Then run a load test in `tools/loadtest.py`: build 10,000 blocks, then run players and units around them, and record the tick time and memory in `LOADTEST_RESULTS.md`.
  **Done when:** a saved and reloaded world has the same blocks in the same cells, and the numbers are written down. **If** the load test shows tens of thousands of uniform blocks are too heavy (memory or send time), write down the number and consider a chunk-overlay block layer (blocks stored as one value per cell, changes sent as world deltas) behind the same `build_structure` and `modify` interface. Do not build it before then.

## Part 4: Data for later (no behavior yet)

- [ ] **4.1 Movement and sight flags (any entity).** Decided: structures and other entities (a boulder, a closed door, a large unit) can block movement and sight, to be used by flow fields later. So these are general entity flags, not structure-only: `blocks_movement` and `blocks_sight` can be set in any entity's JSON (template props and bits in the base `flags`). For structures the resource's `structure` block sets them. Nothing reads them yet: flow fields will use the first, line-of-sight code the second. When they do, find blockers through the static layer of the spatial index (foundation 4.2) and the cell index, never by scanning all entities. Make sure the flags are in the world checksum if you compare worlds.
  **Done when:** a non-structure entity file with `"blocks_movement": true` loads and the flag reads back from the entity.
- [ ] **4.2 Other properties.** `flammable` and any other `props` are only data. There is no fire system; when one exists it reads `prop:flammable` and needs no change here.
- [ ] **4.3 Docs.** Add the resource file format, the `structure` block (including `on_break`) and the per-resource template idea to the project layout doc, with one example JSON for a new structure and one for a different kind (a door: an entity file with a `structure` key, `blocks_movement` and `blocks_sight` true, and extra props).

---

### Decided
- Structures and other entities can block movement and sight (flags on any entity; flow fields will use them later).
- Anyone can break any structure.
- What a broken structure returns is configurable per resource (`on_break` rules: fractions, tool or other conditions on the breaker).
- The cell size is 32 (the tile size) for now, kept in one constant `CELL_SIZE` so it can change.
- More structure kinds (a door, a chest) will be added as JSON entity files with a `structure` key.

### Open questions
None left in this file.