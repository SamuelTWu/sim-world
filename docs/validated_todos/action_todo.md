# Part 1 of 3: Actions

Build order: **1. Actions (this file)**, then 2. Items (`2_items_todo.md`), then 3. Structures (`3_structures_todo.md`).

This file builds the engine: five primitive **ops**, actions written as JSON, **reactions**, and commands as a queue. It needs no items and no structures. Items and structures plug into it afterwards.

Out of scope for all three files: movement, exploring, wandering, ranking actions by need. Travel is one stub function that flow fields replace later. Also out of scope for now: autocrafters choosing their own recipe, taking inputs from nearby containers, and the "pick the best pixel" assignment for the recipe book (a layer on top of `do`).

Conventions: relative imports only, no comments or docstrings, longer lines over more lines, snake_case files, an `__init__.py` in every folder, pygame only in `client/`. Dependency direction `shared < world < content < sim < server`: JSON lives in `content/`, the code that runs it in `sim/`.

How to read a step: **Do** is what to change, **Done when** is how you know it works. Run every existing check after each step.

---

## The idea in one page

Every action is the same pipeline, and only the data differs:

    pick target -> travel -> check requirements -> pay cost -> wait -> roll chance -> apply effects -> repeat

**Five ops** are the only things an action can do. Three exist as files today and are reworked in Part 2 (`drop`, `pickup`, `spawn`); two are written here:

| op | does | where |
|---|---|---|
| `modify` | change one stat of a thing (add or set a number, set or clear a tag, add or remove a status). Hit, water, poison, and removal (`alive` set to 0) are all this. | new, this file |
| `emit` | fire a named event; `visible: true` also sends it to clients (a shot, an impact) | new, this file |
| `drop` | carried resource or pixel goes into the world | Part 2 |
| `pickup` | a pixel in the world goes into someone's inventory or cargo | Part 2 |
| `spawn` | create a new pixel (never touches an inventory) | Part 2 |

There is no `destroy` and no `move`. A pixel that must go away is removed by a **reaction** to `modify` (health reaches 0, so `alive` is set to 0). Moving is only the travel phase of the pipeline.

**An op returns `True`, or a short reason string** (`no_room`, `target_gone`...). The pipeline turns a reason into the task's failure reason.

**Stat names** (shared with `sim/ai/stats.py`, so reading and writing use one list): `health`, `energy`, `age`, `alive`, `need:<name>`, `inventory:<resource>`, `prop:<name>`, `tag:<name>`, `status:<name>`. `modify` writes the same names `read` reads.

**Action JSON** (`content/actions/<id>.json`; everything except `id` is optional):

| field | meaning |
|---|---|
| `id` | the name = the file name. A pixel can do an action when it has a trait with that name. |
| `label`, `description`, `tier`, `cost_points` | for the editor and tech tree |
| `params` | values a player may edit: a number `{"default", "minimum", "maximum", "weight"}`, or a **row** `{"type": "row", "table": "recipes"}` that picks one row of a data table (see "Tables and rows" below). Any other field may say `"$name"` or `"$name.field"`. |
| `target` | `{"type": "pixel" \| "self" \| "point", "filter": [conditions], "range": 1, "pick": "nearest" \| "random"}`. `range` 0 = on top of it, 1 = adjacent, larger = world units. |
| `requires` | conditions on the actor: `[{"stat", "op", "value"}]`, operators `< > <= >= == !=`. An element may be a `$ref` that resolves to a list; it is spliced in (this is how a table row adds its own requirements). |
| `cost` | a map of stat to amount, for example `{"energy": 0.02}` or `{"inventory:clay": 2, "inventory:wood": 1}`; may be a `$ref` to a map. Paid at the start of each cycle, or all at once with the effects at the end of it when `cost_at` is `"end"` (default `"start"`). |
| `time` | seconds per cycle, rounded up to ticks (0.2 s = 4 ticks at 20 Hz); may be a `$ref` |
| `chance` | 0..1 per cycle |
| `effects` | list of `{"op", ...}`, each may have `"chance"` and `"if"`; `modify` accepts a map of stat to amount (also as a `$ref`) |
| `repeat` | `false`, a number (or `"$count"`) of cycles, or `"target"` (until the target is gone) |
| `variants` | overrides tried in order; the first whose `requires` pass is used |
| `click` | how a player's click can mean this action (step 6.3) |

An effect says who it applies to with `on`: `self`, `target`, or `area` (everything within `radius` of the target, optional `tag`).

**Tables and rows.** A table is a folder of JSON files in `content/` (for now only `content/recipes/`), one row per file, each with an `id`. An action with a `row` param does not know what the table is for: the command sends the row's id (`{"recipe": "brick"}`), and `$recipe.inputs` resolves to that row's `inputs` field. A `$ref` may stand for a whole map or list, not only a number. This is how one `craft` action covers every recipe, and how later actions (build from a table of blueprints, plant from a table of seeds) work with no new engine code. Rows are validated at load time against the action that uses them (unknown stat, resource or op is refused with the file name). The tech tree unlocks rows (a row's `tier`), not actions.

**Reactions are only for an object's own consequences** (a tree drops wood when hit, a pixel is removed at 0 health, a block breaks). They are data on the blueprint, there is exactly one trigger, and most of them come from defaults or a shorthand, so you never write a rule per event:

    {"on": "stat_changed", "when": {"stat": "health", "mode": "reaches", "at": 0}, "if": [conditions], "do": [ops]}

`stat_changed` fires whenever `modify` changes a stat; the event carries the old and new value and the `source` (the pixel that caused it). `mode` is `any`, `down`, `up`, or `reaches` (with `at`: fires once when the stat crosses to `at` or below). `if` is checked after the change. Two things remove the need to write rules by hand: a table `DEFAULT_REACTIONS` (every pixel with health gets "health reaches 0 -> `modify alive set 0`"), and a `drops` shorthand on a blueprint (step 3.6).

**Behavior is not a reaction.** Fighting back, running away, calling for help: those are decisions, made by the decision loop. Events only mark a pixel to rethink and write what happened into its memory and needs (Part 6b):

    events + senses -> stats / needs / memory -> decide -> travel -> arrive (sense) -> action -> update -> (decide again)

---

## Part 1: Set up (no behavior changes)

- [ ] **1.1 Create the folders**
  **Do:** add `sim/ops/`, `sim/actions/`, `content/actions/`, `tests/sim/actions/`, each with an `__init__.py`. Add `tests/sim/actions/` to `tools/run_checks.py`.
  **Done when:** the game and every check run exactly as before.
- [ ] **1.2 Create `sim/ops/op.py`**
  **Do:** move `Param` and `BlueprintError` into `op.py` (from `behavior.py`), and make `behavior.py` import them from there so nothing else breaks (old behaviors keep working until Part 7). Add the `Op` base class: `name`, `params` (a dict of `Param` for the effect's fields), `validate(effect) -> dict`, and `run(context, actor, target, effect) -> True | reason`. Add a registry: an `OPS` dict, an `@op` decorator, and `load_ops()` that imports every module in `sim/ops/`.
  **Done when:** a throwaway op registers and `OPS` lists it.
- [ ] **1.3 Rename `sim/commands/` to `sim/player_actions/`**
  **Do:** rename the folder and fix imports. Rename `load_commands` and `COMMANDS` to match. Keep the wire message names for now.
  **Done when:** the command checks pass unchanged.

## Part 2: Writing stats, `modify`, `emit`

- [ ] **2.1 The stat writer**
  **Do:** in `sim/ai/stats.py` add `modify(entity, name, add=None, set=None) -> (old, new)`, using the same address space as `read` and the same name validator. Clamp to the stat's own range (health 0..max, need min..max, inventory >= 0). An add to `inventory:<resource>` that does not fit is refused with the reason `no_room`, using the inventory API's own capacity check (confirm its name), never clamped silently. `alive` only accepts `set 0` (call `entity_manager.kill`; removal still happens at the end of the tick). After a change, emit `stat_changed(entity, stat, old, new)` on the event bus.
  **Done when:** `tests/sim/actions/check_modify.py` passes: every stat family, clamping, `alive`, and the event fires with old and new.
- [ ] **2.2 Conditions**
  **Do:** `sim/actions/conditions.py` with `check(actor, target, conditions) -> reason | None`, built on `stats.read`. Operators `< > <= >= == !=` (extend the table in `rules.py`; it is the same table). A condition can name `self` or `target` (default: self for `requires`, target for `filter`).
  **Done when:** `check_conditions.py` passes.
- [ ] **2.3 The `modify` op**
  **Do:** `sim/ops/modify.py`: `{"on", "stat", "add" | "set"}`, or `{"on", "add": {stat: amount, ...}}` (one map, applied all-or-nothing: if one stat is refused, for example `no_room`, none change). `on: area` finds neighbors through `context.proximity` (never scan every pixel). Returns `True`, or a reason.
  **Done when:** `check_ops.py` shows modify on self, target and area.
- [ ] **2.4 The `emit` op**
  **Do:** `sim/ops/emit.py`: `{"event", "data", "visible"}`. It emits on the event bus; with `visible: true` it also writes a transient event (the existing capped log, 256 per tick, for clients).
  **Done when:** `check_ops.py` shows both the bus event and the transient event.

## Part 3: Reactions (object consequences only)

- [ ] **3.1 `reactions` on the pixel**
  **Do:** add a `reactions` list to the blueprint format and to the entity (plain data). Validate it in the entity factory (`rules.validate_rules`, which now knows one trigger). Include it in `to_dict`.
  **Done when:** a blueprint with a bad reaction is refused with a readable message, and a good one loads.
- [ ] **3.2 The `stat_changed` trigger**
  **Do:** in `rules.py` keep only this trigger (`when`: `stat`, `mode`, `at`; `if` checked after the change). The event carries `entity`, `stat`, `old`, `new` and `source` (the actor of the `modify`, or `None`).
  **Done when:** a test pixel with a reaction on `health`, `down` fires on each hit and not on healing, and `source` is the hitter.
- [ ] **3.3 Ops only, and delete the old triggers and effects**
  **Do:** a rule's `do` is a list of ops from `OPS`. Delete the old effects (`die`, `damage_area`, `spawn`, `set_need`, `status`, `emit_stimulus`, `anger`) and `hurt()`. Delete the other triggers (`death`, `hurt`, `click`, `signal`, `trespass`, `timer`, `contact`) and move what each did: `click` is a player action (Part 6), `signal`, `trespass` and `contact` are perception (Part 6b), `death` and `hurt` are covered by `stat_changed`, `timer` is dropped (nothing uses it). `anger` becomes the event table in 6b.5.
  **Done when:** `rules.py` has one trigger, and no code outside the ops kills a pixel or changes health directly.
- [ ] **3.4 Depth guard**
  **Do:** in `dispatch`, stop a reaction chain deeper than 8 and count it (`reaction_depth_limit`).
  **Done when:** two pixels whose reactions trigger each other end the chain instead of recursing forever (the one gap the 9.9 limits did not cover).
- [ ] **3.5 `DEFAULT_REACTIONS`**
  **Do:** a table in `rules.py`, applied at spawn like `DEFAULT_NEEDS`: any pixel with `health` gets "health reaches 0 -> `modify alive set 0`".
  **Done when:** a pixel hit to 0 health is removed with no reaction in its blueprint.
- [ ] **3.6 The `drops` shorthand**
  **Do:** a blueprint field `"drops": {"stat": "prop:durability", "per_hit": {"wood": 1}, "at_zero": {"wood": 5}}` expands at load time into two reactions: each `down` change that leaves the stat above 0 spawns the `per_hit` items at the pixel, and reaching 0 spawns the `at_zero` items and sets `alive` to 0. Either part may be left out. It needs the `spawn` op with `item` (items file, step 2.7), so test it with a stub op until then.
  **Done when:** `check_reactions.py`: a target with `drops` of 10 durability goes 10 -> 9 and drops one item; at 0 drops five more and is removed; the expanded reactions are what `to_dict` saves.
- [ ] **3.7 Delete `react.py`**
  **Do:** move any blueprint that used the `react` trait to `reactions` or `drops` (a short one-time script is fine), then delete `sim/behaviors/react.py`.
  **Done when:** `grep -rn '"react"' src content` finds nothing.
- [ ] **3.8 Check**
  **Do:** `tests/sim/actions/check_reactions.py`: death at 0, `down` and `reaches` modes, `if` after the change, `source`, the depth guard, `drops`, two seeded runs identical.
  **Done when:** it passes with `check_sim_determinism`.

## Part 4: The action engine

- [ ] **4.1 `ActionDef` and the loader**
  **Do:** `sim/actions/action_def.py`: one action from JSON, with `validate(values)`, `cost(values)` (copy these from the old `Behavior`), `$param` and `$name.field` substitution (4.1b), `cost_at`, and `variants`. `sim/actions/loader.py` reads every `content/actions/*.json` in name order and refuses bad files at load time (unknown op, unknown stat, bad `on`, unknown field) with the file name in the message.
  **Done when:** `check_loader.py` loads a good file and refuses five kinds of bad file.
- [ ] **4.1b Tables, rows and `$ref`**
  **Do:** `sim/actions/tables.py`: `load_tables()` reads every row file of each table folder (for now `content/recipes/*.json`, one row per file, `id` required, file name = id) and refuses bad rows with the file name. In `ActionDef`: a param of type `row` accepts only an id that exists in its table; `resolve(values)` replaces `$name`, `$name.field` and `$name.field.sub` anywhere in the action (strings, maps, lists); a `$ref` that is an element of a list and resolves to a list is spliced in. A missing row or field is a load-time error when the value is a literal and a task failure `bad_row` when it came from a command. Rows are validated against the action that uses them at load (stats, resources and ops must exist). Keep the substitution table-agnostic (it must not mention recipes); only `recipes` exists as a table for now.
  **Done when:** `check_tables.py`: a row param accepts a good id and refuses an unknown one; `$recipe.inputs` resolves to a map, `$recipe.time` to a number, and a list `$ref` is spliced; a bad row file is refused with its name; a made-up second table works with no engine change.
- [ ] **4.2 `ActionManager`**
  **Do:** `sim/actions/action_manager.py` with the same methods the tech tree and editor use on `BehaviorManager` today (`get`, `all`, `names`, `by_tier`, `ordered`, `cost`, `breakdown`). Run it beside the old manager (do not delete the old one yet); a pixel's traits are looked up in both.
  **Done when:** the editor lists a new JSON action with no code edit.
- [ ] **4.3 Targets**
  **Do:** `sim/actions/targets.py` resolves a `target` spec to a thing and a standing point: `pixel` (through `context.proximity`, filters through `conditions`), `self`, `point`. Ties break by distance, then id. Count the work (`target_searches`, `target_tested`) and give it a per-tick budget like the think budget.
  **Done when:** `check_targets.py` shows range, filters, tie-breaking, and the budget.
- [ ] **4.4 `travel()`**
  **Do:** one function `travel(entity, goal, context, delta_time) -> "arrived" | "moving" | "blocked"`, wrapping `step_toward` in `sim/navigation/movement.py` (keep that file).
  **Done when:** it is the only place the pipeline moves a pixel. The flow field will replace this function and nothing else.
- [ ] **4.5 The pipeline task**
  **Do:** `sim/actions/pipeline.py`: one `ActionTask(Task)` with phases `target -> travel -> check -> pay -> wait -> roll -> effects -> repeat`. With `cost_at: "end"` the `pay` step moves to after `roll` and is done together with `effects` as one all-or-nothing step (re-check the cost, pay, apply; if anything fails nothing changes and the inputs stay with the pixel). All its progress lives in `task.state` (phase, target id, progress, cycles done), so it saves. Failures use `task.fail(code)`: `no_target`, `blocked`, `requirements`, `cannot_afford`, `target_gone`, `timeout`, or an op's reason. `finish()` releases anything claimed. One global patience limit for travel and blocked time.
  **Done when:** `check_pipeline.py` runs a made-up action (`poke`: modify a prop on a nearby pixel) through every phase and every failure code.

## Part 5: Port the first actions (they need only `modify` and `emit`)
For each: write the JSON, write `tests/sim/actions/check_<name>.py` (target found, travel, effect applied, two seeded runs identical), then delete the old code.

- [ ] **5.1 `attack`**
  **Do:** `attack.json`: target `pixel` filtered by `health > 0` and `tag:hostile`, `time` 0.5, `chance` 0.9, `repeat: "target"`, effects `modify health -$damage` on the target and `emit hit` (visible). Move the 9.7 nearest-first target test and the proximity grid into the `pixel` target resolver. A ranged attack is the same file with a larger `reach` and a `shot` emit.
  **Done when:** the old attack checks pass. Then delete `sim/behaviors/attack.py`, `attack_method.py`, `attack_methods/` and the attack parts of `CommandContext`.
- [ ] **5.2 `water`**
  **Do:** `water.json`: target a pixel with `tag:plant`, `requires inventory:water > 0`, `cost {"inventory:water": 1}`, effect `modify prop:moisture +0.3`.
  **Done when:** its check passes (and fails with `cannot_afford` with no water).
- [ ] **5.2b `spread`**
  **Do:** `spread.json`: effect `modify status:poison add $strength` with `on: area` and `radius: $radius`.
  **Done when:** its check passes; everyone within the radius is affected, nobody outside.

- [ ] **5.3 `craft`**
  **Do:** `content/recipes/brick.json` (and two more rows as test data) and `content/actions/craft.json`, sketch:
  ```json
  {"id": "craft", "label": "Craft", "params": {"recipe": {"type": "row", "table": "recipes"}, "count": {"default": 1, "minimum": 1, "maximum": 99}},
   "target": {"type": "self"}, "requires": ["$recipe.requires"], "cost": "$recipe.inputs", "cost_at": "end",
   "time": "$recipe.time", "repeat": "$count", "effects": [{"op": "modify", "on": "self", "add": "$recipe.outputs"}]}
  ```
  A recipe row: `{"id": "brick", "label": "Brick", "category": "building", "tier": 1, "inputs": {"inventory:clay": 2}, "outputs": {"inventory:brick": 2}, "time": 4, "requires": [{"stat": "tag:furnace", "op": "==", "value": 1}]}`. A row with no station requirement is a hand recipe. A station is an ordinary blueprint with an inventory, the `craft` trait and a tag, and it crafts the same way (`target: self`); pixels feed it and collect from it with `drop` and `pickup` (items file). The crafted output goes into the actor's inventory through `modify`, so a full inventory fails the cycle with `no_room`, and the inputs stay with the pixel.
  **Done when:** `check_craft.py`: a hand recipe turns its inputs into its outputs after `time`; `count` 3 runs three cycles and stops early with `cannot_afford` when inputs run out; a full inventory fails with `no_room` and loses nothing; cancelling mid-cycle keeps the inputs; a station recipe is refused on a pixel without the tag and works on a station pixel; a new recipe file works with no code edit; two seeded runs identical.
## Part 6: Commands become "do this action now"

- [ ] **6.1 The queue**
  **Do:** `entity.queue` is a list of `{"id", "data"}`. A command goes to the front and starts at once (the running action is cancelled through `Task.cancel`); the rest wait below and run in order; a self-chosen action never enters the queue. Cap its length (a new `Limits` entry, say 8) and count refusals. It is plain data, so it saves.
  **Done when:** `check_queue.py` passes.
- [ ] **6.2 The `do` command**
  **Do:** `sim/player_actions/do.py`: `{"name": "do", "args": {"ids" | "box", "action": "attack", "data": {...}, "queue": "front" | "back" | "replace"}}`. Validate the action id against the pixel's traits and `data` against the action's params and target spec. The only gates are `owner` and `alive`. Keep box selection, `MAX_IDS`, wake-on-command (9.3) and the inbox limits (9.9).
  **Done when:** the old command checks are rewritten for `do` and pass.
- [ ] **6.3 Clicks**
  **Do:** an action may declare `"click": {"on": "pixel", "priority": 10, "if": [...]}`. `act` collects the actions the selected pixels have, asks each for a match at the point, takes the highest `priority`, and calls `do`.
  **Done when:** a click on a hostile pixel means `attack` and a click on empty ground does nothing, with no code edit to `act` for a new action.
- [ ] **6.4 Abilities for the client**
  **Do:** `inspect` returns the actions a pixel can do (id, label, params, what target it needs). For a `row` param it also returns the rows the pixel can do right now and, for the rest, the first reason they cannot (`requires`, `cannot_afford`, `no_room`), so the client can build a recipe book from one action. The client builds its menu from that. Bump the protocol version once for `do`, `abilities` and `action_failed`.
  **Done when:** the client menu lists actions that are only in JSON.
- [ ] **6.5 Remove the old command system**
  **Do:** delete the per-pixel command files (`move`, `attack`, `drop`, `pickup`, `spawn` commands), the old `act` resolvers, the `command` trait with `gate_trait` and `gate_behavior`, `orders.py` with `components["order"]`, `FAILURE_REASONS` and `task_score == inf`. `order_failed` becomes `action_failed` carrying the task's reason. Fix `gui/blueprints.py` (it special-cases the `command` trait).
  **Done when:** `grep -rn "order_failed\|ORDER_SCORE\|\"command\"" src` finds nothing.
- [ ] **6.6 Tests**
  **Do:** a command interrupts a running action; the interrupted one is dropped and the queue below runs next; `back` appends; an action the pixel lacks is refused; a bad target is refused with a readable reason; a box selects only pixels that have the action; the queue cap holds.
  **Done when:** all pass.

## Part 6b: Perception and interrupts (generic hooks; fight and flee scoring comes later)
This part makes events feed the decision loop. It builds the mechanism only: how a pixel notices something happened, rethinks, and knows exactly who did it. What it does about it (attack back, flee, call for help) is decided by considerations, which are deliberately left for later.

- [ ] **6b.1 `source` on every change**
  **Do:** every op that changes another pixel passes the actor as `source` (`modify` into `stat_changed`; later ops likewise).
  **Done when:** a test shows the victim's event names the attacker's id, also when the attacker is out of sight.
- [ ] **6b.2 The `rethink` flag**
  **Do:** `entity.rethink` (a runtime bool, not saved). `mark_rethink(entity, reason)` sets it and counts `rethink_marked`. In `SystemRunner`: a flagged pixel skips the think interval and wakes if asleep (9.3), the flag clears when it thinks, and in `over_think_budget` flagged pixels go first and the rest keep the rotating priority. The 9.9 cap still holds: a pixel over budget keeps its flag for the next tick.
  **Done when:** a test flags 1000 pixels in one tick and no tick makes more than `max_thinks` decisions, and every flagged pixel has thought within a few ticks.
- [ ] **6b.3 What interrupts: one editable table**
  **Do:** `INTERRUPTS` in `sim/ai/interrupts.py`, a list like `{"event": "stat_changed", "when": {"stat": "health", "mode": "down", "needs_source": true}}`, `{"event": "need_threshold"}`, `{"event": "task_finished", "when": {"status": "failed"}}`. A listener on the event bus marks the pixel when an entry matches. Nothing else interrupts. (Add `need_threshold` itself later, with the 16.1 sleep work.)
  **Done when:** damage with a source flags the victim, healing and damage with no source do not.
- [ ] **6b.4 Who is protected, and anti-flip-flop**
  **Do:** a commanded task (`source == "command"`) ignores interrupts. For self-chosen tasks: the existing `SWITCH_MARGIN` decides whether a new best action replaces the running one, a minimum commit time (`MIN_COMMIT`, in seconds, kept in `task.state`) stops a switch right after starting, and an action may declare `"interruptible": "cycle"` in its JSON so it only switches at a cycle boundary (for actions that pay cost every cycle).
  **Done when:** a pixel does not switch back and forth between two near-equal actions over 100 ticks, and a commanded pixel keeps its command while being hit.
- [ ] **6b.5 Events become memory, relationships and needs: one editable table**
  **Do:** `EVENT_EFFECTS` in `sim/ai/interrupts.py`, for example `{"hurt": {"memory": {"type": "event", "ttl_importance": 0.8}, "relationship": {"resentment": 0.3, "fear": 0.1}, "needs": {"safety": 0.2}}}` (the numbers are placeholders). A function `note_event(entity, kind, source, context)` writes a keyed `Memory` (`event:<kind>:<source id>`, with the source's last known position) through `MemorySystem.remember`, adjusts `RelationshipSystem` and raises the needs. Hook it to the same listener as 6b.3. This replaces the old `anger` effect and `components["grudges"]`.
  **Done when:** after one hit the victim has a memory naming the attacker, a higher `resentment` toward that id, and a higher `safety` need; a second hit reinforces the same memory instead of adding another.
- [ ] **6b.6 Targets from memory as well as from sight**
  **Do:** let a `target` spec say where candidates come from: `"from": ["sense", "memory:event"]` (default `["sense"]`). Remembered ids come first, then the nearest sensed ones, deduplicated. A pipeline task may start with an explicit target id; its travel phase goes to the remembered position, and the pixel must sense the target within range before an effect lands. If it cannot, the task fails `target_lost`.
  **Done when:** a victim whose attacker is out of sight gets the attacker as a candidate with its exact id; if the attacker is not found on arrival the task fails `target_lost` and the memory fades.
- [ ] **6b.7 Hooks for later (build nothing yet)**
  **Do:** make sure each of these has one obvious place to be added, and write the place down in the project layout doc: perception writing derived stats (such as `threat`) at the sensing rate (`PERCEPTION_STATS`, empty for now); considerations that read relationships and memory (`resentment`, `fear` of the target); alarm signals between pixels (the old `signal` trigger); territory trespass (the old `trespass` trigger).
  **Done when:** the layout doc lists them.
- [ ] **6b.8 Tests**
  **Do:** `tests/sim/actions/check_interrupts.py`: an event with a source flags a sleeping pixel and it rethinks next tick; the running action continues unless a new one beats the margin; a commanded pixel is not interrupted; 1000 flagged pixels stay inside the think budget; a hit leaves the attacker's id in memory and relationships; the attacker is a candidate when out of sight; two seeded runs identical.
  **Done when:** it passes with `check_sim_determinism` and `check_limits`.

**Left for later on purpose (the generic part is done, the tuning is not):** how fight and flee are scored, what courage and fear mean, whether `flee` is an action or a mode, group reactions and alarms, a panic override for commands, and the actual numbers in `EVENT_EFFECTS`.

## Part 7: Remove the old behaviors (finish this after *Parts 2 and 3 of the items file*, because `drop`, `pickup` and `spawn` are still old behaviors until then)

- [ ] **7.1 `move.py` and `roam.py`**
  **Do:** `max_speed` becomes a plain blueprint prop (`"props": {"max_speed": 1.5}`); migrate every blueprint that used `roam.speed` or `move.speed`, and show it in the editor as a property. Delete both files. Pixels then no longer wander on their own (that returns with flow fields and the needs work), so give checks, `profile_sim` and the load test a replacement workload: place pixels near each other and `do` commands on them.
  **Done when:** every check and `tools/loadtest.py` run with that workload.
- [ ] **7.2 `adapt.py` and `build.py`**
  **Do:** run `grep -rn "adapt\|build_index\|\"build\"" src tests tools content`, and check blueprints and `gui/` for traits named `adapt` or `build`. If nothing depends on them, delete them. If something does, tell me what it is for and we express it as an action.
  **Done when:** both files are gone and nothing imports them.
- [ ] **7.3 The old machinery**
  **Do:** when the last old behavior is ported, delete `behavior.py` and `behavior_manager.py`, and point the tech tree and editor at `ActionManager`.
  **Done when:** `grep -rn "BehaviorManager\|behaviors\." src` finds nothing.

## Part 8: Scale, save, show

- [ ] **8.1 Limits.** Cap effects applied per tick, targets searched per tick, `repeat` cycles per action, and queue length; defer in order, count, extend `check_limits`.
- [ ] **8.2 Save.** Add a registry so `load_task` can rebuild an `ActionTask` from `{"name", "data", "state"}`; save `entity.queue` and `entity.reactions` with the pixel (needed by 10.2).
- [ ] **8.3 Replicate.** Send the action id and phase (a small enum) in the pixel entry, only when it changes; show it in the client over the pixel and in the inspect panel.
- [ ] **8.4 Sleep.** A pixel with nothing to do and an empty queue sleeps; a command wakes it.
- [ ] **8.5 Needs hook.** Add a `satisfies` field to the action JSON and apply it with `NeedSystem.completed` when a task ends DONE (the runner edit from the 13.3 patch). That replaces the `SATISFIES` table; ranking by need is the next project.
- [ ] **8.6 Load test.** A scenario in `tools/loadtest.py` with a population commanded to `attack`; record the result in `LOADTEST_RESULTS.md`.
- [ ] **8.7 Docs.** Put the five ops, the field list and the stat names in the project layout doc. Adding an action is "write a JSON file and add the trait to a blueprint"; adding a recipe is "write a JSON file in `content/recipes/`".

---

### Reused as they are
`Task` (state, reason, `fail`, `finish`), `stats.py` (read side), `MemorySystem`, `ProximityIndex`, 9.9 `Limits`, the transient event log, `Param` and the editor, `movement.step_toward` (behind `travel()`).

### Open questions
- Should anything override a command (a panic when health is very low), or are commands always obeyed? (Part 6b protects commands; a panic rule can be added later.)
- `MIN_COMMIT` and `SWITCH_MARGIN`: keep the current 1.3 margin, and what minimum commit time?
- A command interrupts a pixel's own action: dropped (this plan) or pushed down the queue?
- `cost` is paid at the start of each cycle by default (a failed cast loses its bait) and at the end with `cost_at: "end"` (crafting: an interrupted craft keeps its inputs). Right defaults?
- The shortest action is 4 ticks (200 ms at 20 Hz). Fine?
- Do you want a one-time script to migrate blueprint traits named after the old behaviors (`roam`, `move`, `command`, `react`), or edit by hand?
- What did `adapt.py` and `build.py` do?