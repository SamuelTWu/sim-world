# Crafting

Crafting is something pixels do, not something the player does from a global menu. The player still gets a simple, fast way to ask for things, and the game decides who does the work.

## Goals

- Open ended and sandboxy: crafting gives pixels more to do, supports specialization, logistics and trading.
- Quick to pick up: the player says what they want, not which pixel walks where.
- Cheap and consistent: one recipe format, one craft action, no special cases for furnaces or machines.

## Core rules

1. **Crafting is an action.** `craft` is an action spec like any other, so it can be commanded, chosen by a pixel on its own, and shown in the UI.
2. **No searching for ingredients.** A crafter uses only its own inventory (and, later, a few nearby containers found through the structure index). It never scans the ground. Fetching items is a separate job done by `pickup` and `deposit`, which chain through the normal decision scoring.
3. **Recipes are data.** One file per recipe in `content/recipes/`, so anyone can add one. A recipe lists inputs, outputs, an optional time, an optional required station tag, and fuel (fuel is just another input).
4. **Stations are pixels.** A furnace is a blueprint with an inventory and the craft ability, filtered by a station tag. It has no locomotion. It is not a special system.
5. **Inventory limits batch size, not availability.** A recipe is always visible. If it cannot run, the UI says why (missing items, no station, no pixel with the ability, no room for the output). Crafting skill or tier, from the tech tree, decides what a pixel can make.
6. **Batches are one task.** `craft planks x20` is a single repeating task, not 20 commands.

## Recipe sketch

```json
"brick": {
  "inputs": {"clay": 2},
  "outputs": {"brick": 2},
  "time": 80,
  "station": "furnace"
}
```

A recipe with no `station` is a hand recipe.

## Who crafts what

| Kind | Performed by | Inputs come from | Notes |
|---|---|---|---|
| Hand recipe | a pixel with the craft ability | the pixel's own inventory | no station needed |
| Station recipe | the station itself | the station's own inventory | pixels only feed it and collect from it |
| Autocrafter | a station with a recipe set on it | its own inventory | crafts whenever its inputs are present |

Pixels never craft "at" a furnace. They `deposit` inputs and `pickup` outputs with the existing actions. That keeps all item movement in one place.

## Player flow

One craft button (or `C`) opens the recipe book. The player picks a recipe and a count.

- **Something selected:** the selected pixel does it. Explicit control always wins.
- **Nothing selected:** the game assigns the best candidate among the player's own pixels that can craft and are not busy. It scores by how much of the input they already carry and how close they are, and looks only at the nearest handful, never everything on screen. A highlight or line shows who took it.
- **A station clicked:** the same recipe book, filtered to that station.
- **Nobody can do it:** the recipe shows the reason.

All three entry points create the same craft request, so there is one code path.

## Later: work orders

Instead of assigning at click time, the request goes on a work-order board and idle pixels with the craft ability pick it up through normal utility scoring (as in RimWorld or Dwarf Fortress). The recipe book stays the same. It adds latency and a board to manage, so it comes after the basics.

## Build order

1. Recipes as data, and a `craft` action that works from the pixel's own inventory, with a count.
2. Stations as structures with timed recipes (furnace, kiln).
3. Nearby-container lookup (small radius, capped item count).
4. Recipe book UI with the assignment rule above.
5. Autocrafters (a station with a set recipe).
6. Autonomous crafting: a pixel crafts when something it needs is craftable.
7. Work orders (optional).

Steps 1 to 4 give the whole player experience. The rest is optional depth.

## Open questions

- Should the player feed and collect stations by hand at first, or is automatic hauling needed in the first version? (The plan assumes by hand.)
- Are all recipes available from the start, or unlocked through the tech tree? (The current plan: all visible, gated by ability and station.)
- Does a station need power or fuel beyond a recipe input?