# Crafting

Crafting is something pixels do, not something the player does from a global menu. The player still gets a simple, fast way to ask for things, and the game decides who does the work. It is built on the action engine (`actions_todo.md`), with no crafting-specific code in the engine.

## Goals

- Open ended and sandboxy: crafting gives pixels more to do, supports specialization, logistics and trading.
- Quick to pick up: the player says what they want, not which pixel walks where.
- Cheap and consistent: one recipe format, one `craft` action, no special cases for furnaces or machines.
- Agnostic: the engine knows "an action can pick a row from a data table", not what a recipe is.

## Core rules

1. **Crafting is one action.** `craft` is an action JSON like any other (`content/actions/craft.json`). A pixel with the `craft` trait can craft every recipe it is allowed to, so the ability needs no list of recipes.
2. **Recipes are table rows.** One file per recipe in `content/recipes/`. The action has a `row` parameter over the `recipes` table, and refers to the chosen row with `$recipe.inputs`, `$recipe.outputs`, `$recipe.time` and `$recipe.requires`. The command sends `{"action": "craft", "data": {"recipe": "brick", "count": 20}}`.
3. **No searching for ingredients.** A crafter uses only its own inventory (and, later, a few nearby containers found through the structure index). It never scans the ground. Fetching items is a separate job done by `pickup` and `drop`, which chain through the normal decision scoring.
4. **Inputs are paid at the end of a cycle.** The craft action uses `cost_at: "end"`: it re-checks, pays the inputs and adds the outputs as one all-or-nothing step. An interrupted craft keeps its inputs.
5. **Inventory limits batch size, not availability.** A recipe is always visible. If it cannot run, the UI says why (`requires`, `cannot_afford`, `no_room`). A full inventory fails the cycle with `no_room` and loses nothing.
6. **Stations are pixels.** A furnace is a blueprint with an inventory, the `craft` trait and a tag. It has no locomotion. A recipe says which tag it needs with an ordinary `requires` condition.
7. **Batches are one task.** `count` becomes the action's `repeat`, so `craft planks x20` is a single repeating task, not 20 commands. It stops early, with a reason, when the inputs run out.
8. **The tech tree unlocks recipes.** A row's `tier` is what the tree gates, not the action.

## Recipe sketch

A row in `content/recipes/brick.json`:

```json
{
  "id": "brick",
  "label": "Brick",
  "category": "building",
  "tier": 1,
  "inputs": {"inventory:clay": 2},
  "outputs": {"inventory:brick": 2},
  "time": 4,
  "requires": [{"stat": "tag:furnace", "op": "==", "value": 1}]
}
```

A recipe with no `requires` is a hand recipe. `time` is in seconds. Fuel is just another input.

The action in `content/actions/craft.json`:

```json
{
  "id": "craft",
  "label": "Craft",
  "params": {"recipe": {"type": "row", "table": "recipes"}, "count": {"default": 1, "minimum": 1, "maximum": 99}},
  "target": {"type": "self"},
  "requires": ["$recipe.requires"],
  "cost": "$recipe.inputs",
  "cost_at": "end",
  "time": "$recipe.time",
  "repeat": "$count",
  "effects": [{"op": "modify", "on": "self", "add": "$recipe.outputs"}]
}
```

## Who crafts what

| Kind | Performed by | Inputs come from | Notes |
|---|---|---|---|
| Hand recipe | a pixel with the `craft` trait | the pixel's own inventory | no station needed |
| Station recipe | the station itself | the station's own inventory | pixels only feed it and collect from it |
| Autocrafter | a station with a recipe set on it | its own inventory | repeats the recipe; until pixels can choose their own actions, it is started with a `do` command and a count |

Pixels never craft "at" a furnace. They `drop` inputs into it and `pickup` outputs with the existing actions. That keeps all item movement in one place.

## Player flow

One craft button (or `C`) opens the recipe book. The player picks a recipe and a count. The book is built from one action: the client asks for the pixel's abilities, and for the `craft` action's `recipe` param gets the rows the pixel can do now, plus the first reason each of the others cannot be done.

- **Something selected:** the selected pixel does it. Explicit control always wins.
- **Nothing selected:** the game assigns the best candidate among the player's own pixels that have the `craft` trait and are not busy. It scores by how much of the input they already carry and how close they are, and looks only at the nearest handful, never everything on screen. A highlight or line shows who took it. This is a layer on top of the `do` command, not part of the engine.
- **A station clicked:** the same recipe book, filtered to that station.
- **Nobody can do it:** the recipe shows the reason.

All three entry points send the same `do` command, so there is one code path.

## Later: work orders

Instead of assigning at click time, the request goes on a work-order board and idle pixels with the craft ability pick it up through normal utility scoring (as in RimWorld or Dwarf Fortress). The recipe book stays the same. It adds latency and a board to manage, so it comes after the basics.

## Build order

1. In the action engine (`actions_todo.md`): `modify` with a map and a capacity check (2.1, 2.3), `cost_at` and the pipeline (4.1, 4.5), tables, rows and `$ref` (4.1b), then the `craft` action and its check (5.3).
2. Stations as blueprints with an inventory, the `craft` trait and a tag, with timed recipes (furnace, kiln). Needs `drop` and `pickup` from the items file.
3. Abilities that return row choices and reasons (6.4), then the recipe book UI with the assignment rule above.
4. Nearby-container lookup (small radius, capped item count). Costs read only the actor's own stats today, so this needs a new way to name a source.
5. Autocrafters that choose their own recipe, and autonomous crafting (a pixel crafts when something it needs is craftable). These wait for the decision and need-ranking work.
6. Work orders (optional).

Steps 1 to 3 give the whole player experience. The rest is optional depth.

## Open questions

- Should the player feed and collect stations by hand at first, or is automatic hauling needed in the first version? (The plan assumes by hand.)
- Are all recipes available from the start, or unlocked through the tech tree? (The current plan: all visible, gated by `tier`, the `craft` trait and `requires`.)
- Does a station need power or fuel beyond a recipe input?
- Are crafted outputs always resource counts (as in the sketch), or can a recipe produce item pixels? Item pixels need the `spawn` and `pickup` path from the items file.