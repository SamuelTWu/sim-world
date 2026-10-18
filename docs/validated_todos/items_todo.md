# Part 2 of 3: Items

Build order: 0. Entity foundation (`0_entity_foundation_todo.md`), 1. Actions (`1_actions_todo.md`), **2. Items (this file)**, then 3. Structures (`3_structures_todo.md`).

Items are plain **entities** (`kind` "item") built on the entity foundation: a base entity from the shared `item` template plus one small `item` component `{resource, amount, dropped_by}`. They have no traits, no needs, no task, so they are in no awake set and cost no per-tick time. Their lifespan is a timer, and merging stacks uses the spatial index.

Needs from the other files:
- From `0_entity_foundation_todo.md`: Parts 1 to 3 (the roster, the timer heap, the slim entity with templates and `own()`) and step 4.2 (the spatial index). If you build items first, use the old `Entity` and the old per-tick lifespan check, and swap when the foundation lands: only steps 2.1, 2.3 and 2.4 touch it.
- From `1_actions_todo.md`: the ops base (`sim/ops/op.py`), `modify`, reactions with `stat_changed`, the action loader and the pipeline (Parts 1 to 4). Parts 1 and 2 below (resources, item entities, the three ops) can be built and tested with no pipeline at all; Part 3 uses it.

Conventions and "Do / Done when": same as the actions file. Run every existing check after each step.

---

## The idea in one page

| word | what it is | where it lives |
|---|---|---|
| **resource** | a generic name: `wood`, `stone`, `gold`, `seeds`, `fish`. Carried as a number. | `entity.inventory["wood"] = 3` |
| **item** | a resource dropped into the world as an entity (like Minecraft). All items behave the same: nothing comes from the resource except its name and amount. | an entity from the `item` template with an `item` component `{"resource": "wood", "amount": 3, "dropped_by": 12}` |
| **structure** | a resource placed as a block that inherits the resource's properties | see `3_structures_todo.md` |

Wood is one resource that has an item form and a structure form.

**Gathering never touches the inventory.** `mine` and `chop` only `modify` a target's durability. The tree or ore has its own **drops** (a shorthand for reactions) that drop items: one wood per hit, five at zero and then it is removed. Actions and reactions stay separate: the action knows nothing about wood. A player then picks the items up (a `pickup` action).

**Three ops** are reworked here as files in `sim/ops/` (the old `sim/behaviors/drop.py`, `pickup.py`, `spawn.py` stay until Part 4). "Pixel" in the table below means any entity:

| op | does | fields |
|---|---|---|
| `drop` | inventory -> world. A resource becomes an item pixel on the ground, a carried pixel is set down. With `to: "target"` it goes straight into another pixel's inventory (give). | `by`, `what` (`{"resource", "amount"}` or a pixel: `self`/`target`), `to` (`ground` default, or `target`) |
| `pickup` | world -> inventory. An item pixel becomes `inventory:<resource>`; any other pixel goes into cargo (a passenger into a car). | `by` (the holder: `self` or `target`), `what` (`self` or `target`) |
| `spawn` | creates a NEW pixel; never touches an inventory. | `blueprint`, or `item: {"resource", "amount"}`; `at`: `self`, `target` or a point |

Like every op they return `True` or a reason string (`no_room`, `too_far`, `not_enough`, `limit`).

**The resource file** (`content/resources/wood.json`):

    {"id": "wood", "label": "Wood", "item": {"stack": 100, "lifespan": 300}, "slots": 0.1, "structure": {"max_health": 4, "props": {"flammable": 0.8}}}

`item` makes it droppable (a resource with no `item` key is undroppable: `drop` returns `not_droppable`, and it exists only as an inventory number or a structure); `stack` is the most one item entity holds (configurable per resource, default 100 when omitted); `lifespan` is seconds before an item on the ground disappears; `slots` is how much inventory room one unit takes; `structure` is used only by the structures file.

**JSON only:** a new resource is one file in `content/resources/` and nothing else. The `item` entity template is also one JSON file (`content/entities/item.json`), shared by every resource: the resource name and amount are in the component, the sprite comes from the resource id, the lifespan from the resource file.

---

## Part 1: Resources

- [ ] **1.1 The resource table**
  **Do:** create `sim/items/` and `content/resources/` (with `__init__.py`). `sim/items/resources.py` loads every `content/resources/*.json` in name order, validates it (unknown keys, bad numbers, `stack` >= 1) and refuses a bad file with its name in the message. Write `wood.json`, `stone.json`, `fish.json`.
  **Done when:** `tests/sim/items/check_resources.py` loads the three files and refuses five kinds of bad file.
- [ ] **1.2 Resources in an inventory**
  **Do:** in `inventory.py` add `add_resource(entity, name, amount) -> added` (respects the free slots; unknown resource id -> 0) and `take_resource(entity, name, amount) -> taken`. They are the only code that edits `entity.inventory`. Reuse the slot rules that already exist (a resource takes `slots` per unit).
  **Done when:** `check_items.py` shows: add stops at the free slots, take stops at what is there, amounts never go negative.

## Part 2: Item entities and the three ops

- [ ] **2.1 The `item` template and component**
  **Do:** `content/entities/item.json`: `kind` "item", tag `item`, `size` 1, no traits, no needs, no reactions, `static` (it never moves). Add the `item` component to the entity (`entity.item`, a small slots object with `resource`, `amount` and `dropped_by`, created through `own("item")`, saved only when present). The `item` key in a blueprint switches the component on, so another user can make a different item kind in JSON. `dropped_by` is the id of the entity that dropped it (`None` for items a tree or ore drops); it is only a record and never limits who can pick the item up. The sprite id is the resource id, set when the item is made. Items are never snapped to the grid: they lie where they fell.
  **Done when:** a hand-made item entity appears in the world, is in no roster set (it is never visited per tick), and saves and loads with its resource and amount. With the old `Entity` it goes to sleep at once instead (9.3).
- [ ] **2.2 `make_item`**
  **Do:** `sim/items/items.py`: `make_item(context, resource, amount, x, y, dropped_by=None) -> item | reason`. Look in the spatial index (cell index, foundation 4.3) for an item of the same resource within one tile with room (below `stack`) and add to it; otherwise create a new entity from the `item` template through `create_pixel` (so the 9.9 limits apply). Split anything above `stack` into several items. Items merge only when `dropped_by` is the same, so a stack never mixes droppers. Count `items_merged`. Return `limit` when the caps refuse. Merging does not change the existing item's lifespan timer.
  **Done when:** dropping 3 then 4 wood at one spot gives one item of 7; dropping 250 gives three items (100, 100, 50); two different droppers at one spot give two items; the caps stop it past the limit.
- [ ] **2.3 Item lifespan (a timer)**
  **Do:** when an item is created, schedule an `"expire"` timer (foundation 2.2) at `tick + ceil(lifespan / dt)` using the resource's `lifespan`; when it fires, remove the item through the normal removal path. Items with no lifespan never expire. With the old `Entity` (no timer heap yet) use the one cheap check in `age_entity` instead.
  **Done when:** an item is gone after exactly its lifespan in ticks, 2,000 items cost nothing between expiries, and no other entity is affected.
- [ ] **2.4 Item limits**
  **Do:** add `max_items_in_world` (for example 2000) to `Limits`, counted separately from `MAX_PIXELS_IN_WORLD` (which counts capable entities) so a pile of drops cannot starve real pixels. Refuse with `limit` and count it (`item_refused`).
  **Done when:** `check_limits` covers it.
- [ ] **2.5 The `drop` op**
  **Do:** `sim/ops/drop.py`. `what` a resource: take it from the holder with `take_resource` and `make_item` at the holder's feet (with `dropped_by` set to the holder's id) (or the target's, for `to: target` call `add_resource` on the target instead; `no_room` if it does not fit; give back what was taken on any failure). `what` a pixel: set it down using the cargo rules already in `inventory.py`. Reuse the logic in the old `behaviors/drop.py`, but drop its task, its walking, its generator and its considerations.
  **Done when:** `check_items.py`: drop to ground, drop to target, drop more than you carry (`not_enough`), drop to a full target (`no_room`, nothing lost).
- [ ] **2.6 The `pickup` op**
  **Do:** `sim/ops/pickup.py`. Anyone can pick up any item (no owner check). `what` an item entity: `add_resource` to the holder; if only part fits, leave the rest in the item (change `item.amount`); remove the entity when empty. `what` any other entity: put it in cargo with the old `inventory.load` rules. Check reach again inside the op (`too_far`). Reuse the old `pickup_step` checks (already carried, would carry itself, too big).
  **Done when:** `check_items.py`: pick up a full stack, a partial stack with a nearly full inventory, a pixel into a car, and `by: target` (the car picks up the passenger).
- [ ] **2.7 The `spawn` op**
  **Do:** `sim/ops/spawn.py`: `blueprint` goes through `create_pixel` (any JSON blueprint, not only units); `item` goes through `make_item`. `at` is `self`, `target` or a point. The cost is not in the op (an action's `cost` pays it).
  **Done when:** `check_items.py`: spawn a blueprint, spawn an item, both refused at the limits.
- [ ] **2.8 One rule that must always hold**
  **Do:** a test that drops and picks up random amounts of random resources between several pixels and checks the total amount in the world (inventories plus items) never changes except by an explicit spawn or take.
  **Done when:** it passes with `check_sim_determinism`.

## Part 3: The item actions (JSON, in `content/actions/`)
For each: write the JSON and a `tests/sim/items/check_<name>.py` (target found, travel, effect applied, two seeded runs identical).

- [ ] **3.1 `pickup`**

        {"id": "pickup", "target": {"type": "pixel", "filter": [{"stat": "tag:item", "op": ">", "value": 0}], "range": 1}, "time": 0.2,
         "effects": [{"op": "pickup", "by": "self", "what": "target"}]}

  **Done when:** a commanded pixel walks to an item and its inventory grows.
- [ ] **3.2 `drop` and `give`**

        {"id": "drop", "target": {"type": "self"}, "params": {"resource": {"default": "wood"}, "amount": {"default": 1, "minimum": 1, "maximum": 100}}, "time": 0.2,
         "effects": [{"op": "drop", "by": "self", "what": {"resource": "$resource", "amount": "$amount"}, "to": "ground"}]}
        {"id": "give", "target": {"type": "pixel", "range": 1}, "params": {same}, "time": 0.2,
         "effects": [{"op": "drop", "by": "self", "what": {"resource": "$resource", "amount": "$amount"}, "to": "target"}]}

  **Done when:** one pixel drops wood, another picks it up; one pixel gives wood to another directly.
- [ ] **3.3 `mine` and `chop`, with the target's reactions**

        {"id": "chop", "target": {"type": "pixel", "filter": [{"stat": "tag:tree", "op": ">", "value": 0}], "range": 1}, "time": 1.0, "repeat": "target",
         "effects": [{"op": "modify", "on": "target", "stat": "prop:durability", "add": -1}]}

  The tree blueprint (`content/entities/tree.json`) carries the drops (the `drops` shorthand from step 3.6 of the actions file, which expands to two reactions):

        "props": {"durability": 10},
        "drops": {"stat": "prop:durability", "per_hit": {"wood": 1}, "at_zero": {"wood": 5}}

  `mine.json` is the same with `tag:ore` and an `ore.json` blueprint dropping stone.
  **Done when:** the check shows: durability 10 -> 9 drops one wood item; at 0 five more drop and the tree is gone; the same `chop.json` works on any pixel with durability.
- [ ] **3.4 `fish` (the first tile target)**
  **Do:** add `tags` to the tile types (`water`, ...) in `tile_types.py`, a `tile` target type in `sim/actions/targets.py` (a place to stand, found through a per-chunk "tile types present" index kept up to date by `world.set_tile`, and remembered with `MemorySystem.remember`), and `fish.json`:

        {"id": "fish", "target": {"type": "tile", "filter": [{"stat": "tag:water", "op": ">", "value": 0}], "pick": "nearest"},
         "variants": [{"requires": [{"stat": "inventory:fishing_pole", "op": ">", "value": 0}], "target": {"range": 1}}, {"target": {"range": 0}}],
         "params": {"catch_chance": {"default": 0.2, "minimum": 0.02, "maximum": 1.0, "weight": 2.0}}, "time": 2.0, "chance": "$catch_chance", "repeat": "target",
         "effects": [{"op": "spawn", "item": {"resource": "fish", "amount": 1}, "at": "self"}]}

  **Done when:** with a pole the pixel stops next to water, without one it stands in it, and fish items appear at its feet at about the catch rate (seeded, so the same each run).
- [ ] **3.5 `make_unit`**

        {"id": "make_unit", "target": {"type": "self"}, "params": {"blueprint": {"default": "pixel"}}, "cost": {"energy": 0.3}, "time": 1.0,
         "effects": [{"op": "spawn", "blueprint": "$blueprint", "at": "self"}]}

  **Done when:** it replaces the old `spawn` behavior's check (cost paid, refused at the pixel caps).
- [ ] **3.6 `enter_vehicle` and `exit_vehicle`**

        {"id": "enter_vehicle", "target": {"type": "pixel", "filter": [{"stat": "tag:vehicle", "op": ">", "value": 0}], "range": 1},
         "effects": [{"op": "pickup", "by": "target", "what": "self"}]}
        {"id": "exit_vehicle", "target": {"type": "self"}, "effects": [{"op": "drop", "by": "target", "what": "self", "to": "ground"}]}

  **Done when:** a pixel enters a car, is carried with it, and exits (the slot rules in `inventory.py` limit passengers).

## Part 4: Clean up

- [ ] **4.1 Delete the old behaviors.** Delete `sim/behaviors/drop.py`, `pickup.py`, `spawn.py` once 3.1 to 3.6 pass and nothing imports them. This finishes step 7.3 of the actions file (the old behavior base and manager can then go too).
- [ ] **4.2 Replication.** Items are `static` entities (foundation 4.1): sent once when they enter a client's view and again only when the amount changes or they are removed. Send the `item` component's `resource` and `amount` with them (`dropped_by` stays on the server). Make the client draw them from the resource id (`sprite_id`) and show the amount (a small number) when it is above 1. Check that bytes per client per tick stay flat with 1000 items in view.
- [ ] **4.3 Save and load.** Items save as the template id, base fields and the `item` component (foundation 3.7); the `inventory` dicts are plain data. Expire timers are rebuilt from `born_tick` and the resource's `lifespan` on load, not saved. Add the resource ids to the world checksum inputs if you compare worlds (so a missing resource file is noticed).
- [ ] **4.4 Load test.** In `tools/loadtest.py` add a scenario that drops and picks up continuously with 1000 items on the ground. Record it in `LOADTEST_RESULTS.md`. Target: 1000 resting items add under 1 ms to the tick.
- [ ] **4.5 JSON check.** `check_resources.py` also loads `content/entities/item.json` and a made-up second resource written only as JSON, and drops and picks it up with no Python change.

---

### Decided
- Stack size is configurable per resource in `item.stack`; the default is 100.
- Anyone can pick up any item. The item records who dropped it (`dropped_by`) and nothing else uses it yet.
- Dropped items are not snapped to the grid.
- A resource with no `item` key is undroppable.

### Open questions
- What lifespan per resource? The example keeps 300 s, configurable per resource in `item.lifespan`.