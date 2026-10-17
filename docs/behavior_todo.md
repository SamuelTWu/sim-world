# Sim World: Pixel Life Cycle + Command Unification
Goal: every pixel runs the same loop, and a player command is just "do this action now".

    stats -> needs -> decision -> site (where) -> travel -> perform -> update -> (stats changed, decide again)

Work top to bottom. Each step says WHAT to do and HOW. Don't start a phase until the one above works. These phases are independent of Phases 10-12 (persistence, distribution, web), but 16.3 (saving actions) should be done before or together with 10.2.

Conventions for all new code (from project_layout.md): relative imports only, no comments or docstrings, longer lines over more lines, snake_case files, an `__init__.py` in every folder, pygame only in `client/`. Dependency direction stays `shared < world < content < sim < server`.

---

## 13.1 Audit result (DONE: all six files read, then simplified in 13.1b)

I could read the code that uses these files, but not the files themselves: the copies available to me are stubs written for testing (`NeedSystem.update` does nothing, `MemorySystem` is four empty methods, `DecisionSystem` and `Task` match the real shape). So the table says what is proven by callers and what is still unknown. Paste or attach the five real files and I will fill the unknown rows.

| File | What the callers prove | Still unknown |
|---|---|---|
| `need_system.py` (READ, real file) | `Need` dataclass: `name, value, rate, urgency (callable or None), minimum, maximum`. `Need.update(dt)` does `value += rate*dt`, clamped to min/max. `get_urgency()` returns `urgency(value)` or the raw `value`. `to_dict`/`from_dict` exist. `NeedSystem` is a thin set of helpers over `entity.needs`: `add`, `remove`, `get`, `value`, `urgency`, `satisfy` (value goes DOWN, floor at minimum), `increase` (value goes UP, cap at maximum), `update(entity, dt)` (updates every need), `most_urgent`. The model is "value rises toward max = more urgent; satisfy pushes it back down". | Whether anything calls `most_urgent` (no behavior I can see does). |
| `decision_system.py` (READ, real file) | `Action(name, data)`, `Decision(action, score)`. `DecisionSystem.register(action_name, consideration)` keeps a list per action NAME (shared by every pixel). `evaluate`: each consideration's `read` is clamped to 0..1, passed through its `curve`, clamped again, and multiplied; stops at 0; then adds the compensation term `(1 - result) * (1 - 1/n) * result`. `evaluate_all`, `decide` (best score above 0, else `None`), and `rank` (all decisions, best first). | Nothing. |
| `considerations.py` (READ, real file) | `Consideration(read, curve, name)` where `read(entity, action, context)` returns 0..1 and `curve` maps it. Curves: `linear`, `quadratic`, `inverse` (1 - x), `ramp(low, high)`, `step(threshold)`, `logistic(midpoint, steepness)`; the last three are closures. `Consideration.to_dict()` saves only the name. A module-level `score(entity, action, context, considerations)` repeats the scoring in `DecisionSystem.evaluate`. | Whether `score()` is called anywhere (I found no caller in the code I have). |
| `memory_system.py` (READ, real file) | `Memory(type, data, strength, importance, age)` with `to_dict`/`from_dict`. `MemorySystem` keeps `memories: {entity_id: [Memory]}` OUTSIDE the entity, with `initialize`, `remove`, `remember`, `recall(type, limit)` (sorted by `strength * (1 + importance)`), `strongest`, `update(dt)` (ages, decays strength by `decay_rate`, drops memories under 0.01), `forget`, `clear`, and whole-system `to_dict`/`from_dict`. Nothing in any behavior reads or writes it. | Nothing. |
| `relationship_system.py` (READ, real file) | `Relationship(source, target, trust, fear, affection, resentment, familiarity)` in a flat dict keyed `(source, target)`. `get` CREATES an entry when it does not exist, even on a read. `update` loops every relationship and lowers only `familiarity` (0.001/s). `remove_entity(id)` scans every key. `all_for` scans every relationship. Only the runner calls it (`update`, `remove_entity`). No behavior reads or writes it. | Nothing. |
| `task.py` (READ, real file) | `Task(**data)` with `data`, `elapsed`, `tick` (adds `dt` to `elapsed`, calls `step`), `step` (default DONE), `cancel`, and `to_dict`/`from_dict` (`name`, `data`, `elapsed`). Statuses are the strings `running`, `done`, `failed`. | Nothing. |

**Who reads or writes needs (all behaviors and rules I can see):**

| Need | Read by | Written by |
|---|---|---|
| `aggression` | `attack` consideration (`aggression`) | nothing writes it in the code I have |
| `reproduction` | `spawn` consideration (`reproduction`) | nothing writes it in the code I have |
| `exploration` | `roam` consideration (`restlessness`, default 0.5) | `roam` task (`satisfy(.., 0.05)` on arrival) |
| `safety` | none | `rules.py`: `SetNeed` effect and `Anger` effect (`increase`) |
| anything | `rules.py` `SetNeed` effect (raises or satisfies by name) | blueprint `needs` block sets start value and `rate` |

**Findings in `need_system.py` (things 13.3 must fix)**
1. **Urgency is not normalized.** `get_urgency()` returns the raw `value`, and `DecisionSystem` clamps every consideration to 0..1. With the default `maximum=1.0` that is fine, but `hunger` with `maximum=10` reads as 1.0 as soon as it reaches 1, so it stops mattering. Urgency should be `(value - minimum) / (maximum - minimum)` before any curve.
2. **The `urgency` curve is lost on save and in blueprints.** It is a callable, so `to_dict` leaves it out and `from_dict` and `entity_factory` never set it. Every pixel's urgency is the raw value, always. A curve must be stored by NAME (`"curve": "squared"`) and looked up in a table, so it saves, replicates and can be edited.
3. **Missing needs are silent.** `satisfy` and `increase` do nothing if the pixel never declared that need, and `urgency` returns the default. So `roam`'s `satisfy("exploration")` does nothing unless the blueprint lists `exploration`, and a fishing pixel without `hunger` would never fish. The design needs a rule: either a shared table of needs every pixel gets by default, or an explicit "this pixel has no such need" that is clearly different from 0.
4. **Rate is a constant.** `rate` is a fixed number per pixel, so hunger cannot rise faster while moving or fighting. Handle this as modifiers (`rate * multiplier from the action being performed`), not a callable per need.
5. **No threshold events.** Nothing fires when a need crosses a line, so a sleeping pixel (9.3) never wakes up because it got hungry. Add a `need_threshold` event or a scheduled wake (16.1).
6. **Cost.** Each pixel owns one `Need` object per need, updated every needs-tick through a dict walk. That is fine at current counts but is the first thing to measure with 5000 pixels and 5+ needs each; it may want `__slots__` or a flat list.
7. **Stale import.** `from ..entities.entity import Entity` is the old layout; it becomes `from ...world.entity` or wherever `Entity` lives now (type-only, so a `TYPE_CHECKING` import avoids a cycle).

**Findings in `relationship_system.py`**
1. **Reading creates data.** `get` stores a blank relationship for any pair asked about, so a pixel that merely looks at 500 others adds 500 entries.
2. **Unbounded and never pruned.** Entries are never deleted except on death, and `update` walks all of them each global tick.
3. **Every lookup by pixel is a full scan.** `all_for` and `remove_entity` are O(all relationships), and `remove_entity` runs on every death.
4. **No consumers.** Nothing in the behaviors, rules or territory code reads it, so it can be reshaped freely. (`rules.py` keeps grudges in `components["grudges"]`, a second place for the same idea. Decide later which one survives.)

**Findings in `task.py` (this changes step 13.4)**
1. **Tasks are already almost serializable.** `to_dict`/`from_dict` exist. So 13.4 is not "replace the object with a record"; it is "finish the serialization of the task and move the extra flags onto it". The record I proposed (`name, data, phase, source, score, state`) becomes fields on `Task`, and `entity.task` stays.
2. **Subclass state is lost.** `to_dict` saves only `data` and `elapsed`. `PickupTask.blocked_for` (and any similar counter in other tasks) is not saved, so a loaded pixel restarts its patience timer. Fix with one `state` dict on `Task` that subclasses use for everything beyond `data`, instead of ad-hoc attributes.
3. **There is no way to load a saved task.** `from_dict` is a classmethod of the subclass, but a save only has the name. Nothing maps a name back to a class. `SystemRunner.task_factories` builds tasks from an `Action`, not from a saved dict. Add `load_task(dict)` that looks the name up in a registry (or have each factory accept a saved state).
4. **`cancel` is only called on interruption and removal.** When a task ends by `DONE` or `FAILED`, `run_task` sets `entity.task = None` without calling anything on the task. Anything a task claims at the start (a reserved fishing spot, a lock on a storage slot) would leak. Add `finish(entity, context, status)` called for every ending, which is also the natural hook for the update step (14.6).
5. **A failure has no reason.** `FAILED` is all there is, so `orders.py` guesses the message from the action name (`FAILURE_REASONS`). Let `step` return a status plus a reason code, or set `self.reason`, and delete `FAILURE_REASONS`.
6. **Source, score and phase are not on the task.** They live on the entity (`task_score`) and in `components["order"]`, with `inf` meaning "commanded". Put `source`, `score` and `phase` on `Task` (so they save and replicate with it) and remove the `inf` trick.
7. **The task name is the action name by convention only.** `think()` compares `decision.action.name == current.name`, so a task whose `name` differs from its action would be restarted every think. Make the registry set the name, not the subclass.
8. **Exceptions become `FAILED` silently.** `run_task` catches and prints. Count them (`task_errors`) so a broken behavior shows up in metrics (9.1) instead of only in the log.

**Findings in `considerations.py`**
1. **Curves are code, not data.** Closures have no name or parameters, so a curve cannot be saved, shown in the editor, chosen per need (`need_system.py` finding 2), or set by a blueprint. Replace them with a `CURVES` table of named factories and store `{"curve": "logistic", "midpoint": 0.6, "steepness": 8}`. The existing functions become the table entries unchanged.
2. **Scoring exists twice.** `score()` here and `DecisionSystem.evaluate` run the same maths. Delete one (keep `evaluate`, which is the one in use) so a fix cannot land in only one.
3. **`logistic` can overflow.** `math.exp(-steepness * (value - midpoint))` raises `OverflowError` for a large steepness (about 1400 at the ends). Fine while only code sets it, a crash when a player can edit it. Clamp the exponent (for example to +-60) and put min/max on the `steepness` param.
4. **`logistic` never reaches 0 or 1.** With the defaults it gives 0.0067 at 0 and 0.993 at 1, so a pixel with no hunger still scores about 0.007 for eating. Because scores multiply, that floor is small, but it does mean a "do nothing" action is never exactly 0. Rescale it to hit 0 and 1 at the ends, or use `step`/`ramp` where an exact zero matters.
5. **No difference between "per pixel" and "per candidate" considerations.** `restlessness` (reads one need) is evaluated again for every roam candidate (6 times), though it gives the same answer. Add `scope = "entity" | "action"` so entity-scope values are computed once per think and reused. `jitter` is the opposite case (random per candidate) and should be marked so it is never cached.
6. **No weights or description.** A consideration has only a name, so the inspect panel and the editor have nothing to show and a player cannot say that one matters twice as much. Add `weight` (an exponent on the value, a standard trick) and `description`.
7. **`to_dict` has no `from_dict`** and saves nothing useful. It becomes `{"name", "curve", params}` once finding 1 is done.

**Findings in `decision_system.py` (things the new pipeline depends on)**
1. **An action with no considerations scores 0 and is never chosen.** This is silent. It is why `move`, `pickup` and `drop` only run from orders (they have no considerations or generators), and a new action without considerations would just never happen. The pipeline should fail loudly: an `ActionSpec` that is self-choosable (not command-only) and has no considerations is an error at load time.
2. **Ties are broken by list order.** `max(..., key=score)` returns the first best. Order comes from behavior module name, then generator order, then candidate order, which is deterministic but arbitrary: two equal scores (`attack` 0.6 vs `eat` 0.6) always resolve the same way. Add an explicit tie-break (a `priority` on the `ActionSpec`, then action name).
3. **No importance bands.** Everything is one 0..1 scale, so nothing guarantees that survival beats comfort. A `hungry 0.9` fish and a `curious 0.95` roam compete as equals. Add a `tier` (or weight) per action: higher tier wins outright, scores only compare inside a tier. This is the standard fix and it is small.
4. **Considerations are per action name, not per pixel.** Two pixels with the `fish` behavior score identically for the same needs. Personality can only come from needs and params. That is fine for now; if you want "lazy" vs "hardworking" pixels, add a per-pixel `weights` trait that scales a consideration, not a new system.
5. **Scoring cost is `candidates x considerations`** per think (roam is 6 x 4 = 24 evaluations plus an RNG call each for `jitter`). Fine under the 9.9 think budget, but it will multiply as every action gets site candidates (14.3). Cap candidates per generator.
6. **`jitter` consumes the shared RNG during scoring**, so the RNG stream depends on how many candidates every pixel evaluated. It is still deterministic from sim state, but any change to candidate count or order changes every later random draw in the world. Treat candidate counts as part of the determinism contract (`check_sim_determinism` already covers it).
7. **No explanation.** `rank` exists but nothing keeps per-consideration scores, so "why did this pixel pick fishing?" cannot be answered. Add `explain(entity, action)` returning `[(consideration name, raw, curved)]` for debugging and for the inspect panel.
8. **No link between actions and needs.** Nothing says which needs an action helps. Each behavior writes its own considerations by hand (`aggression`, `reproduction`). The planned `satisfies` entry on `ActionSpec` (14.1) should generate the need consideration automatically: urgency of the needs it satisfies, times how much it satisfies.
9. **Stale import** (`..entities.entity`), same as the others.

**Findings in `memory_system.py` (things to fix when memory gets its first use, 14.6)**
1. **Unbounded.** `remember` always appends. A pixel that remembers every fish or every enemy it sees grows its list without limit, and the only cap is decay (a memory lasts about 4600 s, ~77 min, at the default rate). That is exactly the "unbounded memory" 9.9 is about. Add a per-pixel cap (drop the weakest) and a per-tick cap on new memories.
2. **No de-duplication.** Remembering the same lake twice stores two memories. A memory needs a `key` (for example `("water", tile_x, tile_y)`) so remembering it again reinforces the existing one (resets `strength`, bumps `importance`) instead of adding another.
3. **Recall is by type only.** "Where was the nearest water I know of?" needs a filter on `data` (position, kind) and a distance sort. Add `nearest(entity, type, x, y, kind=None)`, and keep place memories as `{"x", "y", "kind"}`. This is what lets the site finder (14.3) use memory first and scan the world only when memory has nothing.
4. **Decay depends on step size.** `strength *= 1 - decay_rate * dt` is linear per step, so a far pixel updated every 20 ticks decays slightly differently from a near pixel updated every tick, and a large `dt` can hit zero. Use `strength *= exp(-decay_rate * dt)` (or `(1 - decay_rate) ** dt`) so the rate tiers (9.4) give the same result.
5. **`update` allocates every call.** It rebuilds each pixel's list even when nothing expired. Only rebuild when something is below the threshold.
6. **`forget` compares by value.** `memory in list` and `list.remove` use dataclass equality, so two memories with equal fields are indistinguishable and the first match is removed. Compare by identity or by key.
7. **State is not on the entity.** Memories live in the system, not in `Entity` or `Entity.to_dict()`, so saving a pixel (10.2) will not save what it remembers unless the save also calls `MemorySystem.to_dict()`. The system-level `to_dict`/`from_dict` already exists, so this is only a step in 16.3, but it must not be forgotten. Entity ids as dict keys become strings in `to_dict` and are converted back in `from_dict` (already handled).
8. **Stale import.** Same old `..entities.entity` path as `need_system.py`.

**What this changes in the plan**
- Needs are NOT only a stub idea: a blueprint already declares needs with a per-pixel `rate`, `minimum` and `maximum`, and the editor already displays them (`gui/blueprints.py`). Step 13.3 therefore builds on `Need` objects instead of the plain-value dict I proposed: keep `Need` as the stored value, add `to_dict()`/`from_dict()` (needed by 10.2 and 16.3), and add the shared table of defaults (which needs exist, their curve, and what satisfies them) on top.
- No behavior currently WRITES the needs that decisions depend on (`aggression`, `reproduction` only change if a blueprint gives them a `rate`). So today a pixel's wants come only from per-blueprint rates. The new work is mostly "who satisfies a need, and how" (the `satisfies` entry in `ActionSpec`, step 14.1), not "how a need grows".
- `memory_system` is complete and serializable but has no consumers at all, so it can be reshaped freely in step 14.6 (`remember` effect). Its first real job is remembering places (water, storage, food) so pixels do not rescan the world; see the findings above for the changes that needs.
- `command` permissions leak into the UI (`gui/blueprints.py` special-cases the `command` trait), so deleting the permission in 15.5 also needs an edit there.

---

## What exists today (analysis)

**Already good, keep it**
- `DecisionSystem`: utility scoring. Behaviors register a generator (what could I do?) and considerations (how much do I want it?). Scores multiply, with a compensation term. `SystemRunner.think()` picks the best, with `SWITCH_MARGIN = 1.3` so a running task is not dropped for a marginal gain.
- `Behavior` classes: `Param` validation, tier, cost, `apply`/`remove`, `register(runner)`. Traits are per-pixel copies. The tech tree and blueprints already read these.
- Hot-path machinery from Phase 9: `activity` rates (`needs`, `memory`, `think`), sleeping, the think budget (9.9), `ProximityIndex`, counters. The new loop must run inside these, not around them.
- Orders already reuse behavior tasks: `orders.action_of(order)` is exactly the `Action` the decision system would have picked, started with score `inf`. That is the seed of the command unification.

**Gaps that block your loop**
1. **Needs are a thin hook.** Behaviors call `context.needs.urgency(entity, "aggression")`, `satisfy(...)`, `increase(...)`, and `Entity.needs` exists, but nothing in the code I can see defines needs (hunger, boredom...), their rates, or what satisfies them. Your `hunger=10, bored=.2` has no home yet.
2. **No shared "go there, then act" step.** Every behavior re-implements its own approach: `MoveTask`, `AttackTask` (via `attack_step` + `step_toward`), `PickupTask` (`pickup_step` returns "approach"), `RoamTask` (its own movement loop, does not even use `step_toward`). A fishing behavior would be a fifth copy.
3. **Actions have no "where".** An `Action` is `name + data`. Nothing says "needs to stand next to water". Only `move` knows how to reach a point, and nothing can search the world for a place that satisfies a condition.
4. **Nothing happens after the action except `DONE`.** There is no common update step (stats, inventory, item creation, need satisfaction, memory, events), so each task does that inline, or not at all.
5. **No items on the ground.** Pixels can carry pixels (`cargo`) and resources (`inventory`), and `pickup`/`drop` exist, but nothing produces a thing that lies on the ground, and there is no "put it in storage" action or container.
6. **No chaining.** Picking up the fish after catching it only works if some generator offers "pickup" when a fish is near. `pickup` has no generator at all (orders only), and neither do `drop` or `spawn` (orders only).
7. **Action state is only half data.** `Task` has `to_dict`/`from_dict`, but nothing can load one back, subclass state such as `blocked_for` is not saved, and whether a task is a command lives elsewhere (`components["order"]` plus `task_score == inf`). It cannot be sent to the client, and the `inf` trick is a hidden special case.
8. **Commands are a second action system.** `command/commands/` has one file per action (`move`, `attack`, `drop`, `pickup`, `spawn`) plus `act` (click -> one of them) plus a `command` behavior that lists permissions again, plus the gate `gate_behavior` that checks the behavior of the same name, plus `FAILURE_REASONS` in `orders.py`. Adding an action means touching about six places. `place`, `edit_property`, `save_blueprint` and `inspect` are different (they are player operations, not pixel actions) and should stay out of this change.

Note: I could not see your current `sim/ai/need_system.py`, `decision_system.py`, `considerations.py` or `memory_system.py` in full, only the older copies where the need system is a stub. Step 13.1 is a quick check of what is really there before building on it.

---

## Phase 13: Foundations (data first)
Goal: stats, needs and the current action are plain data. Nothing new is visible in game yet.

- [x] 13.1 Audit the real `need_system.py`, `decision_system.py`, `considerations.py`, `memory_system.py`, `task.py`.
      HOW: list what each stores, what is already data vs code, and which behaviors read or write needs. Write the result at the top of this file. If the need system is still the stub (`update` does nothing), 13.3 is a full build, not a tweak.
- [X] 13.2 One stat registry.
      HOW: `sim/ai/stats.py` with `STATS = {name: function(entity) -> float}`. Start from the table already in `rules.py` (`health`, `energy`, `age`, `carried`), add `hunger`-style readings of needs and `inventory:<resource>`. `rules.py` conditions, considerations and needs all read through it, so "what can I compare" is defined once and shows up in the editor.
- [ ] 13.3 Needs table and what satisfies them (the `Need` object, normalized urgency and named curves are done in 13.1b).
      HOW: fill `DEFAULT_NEEDS` in `need_system.py` with the needs every pixel should have (hunger, boredom...), each `{"value", "rate", "minimum", "maximum", "curve", "curve_args"}`; `NeedSystem.initialize` adds them at spawn without overwriting what a blueprint declares. Still to do: rate multipliers while performing an action (hunger rises faster when working) and a `need_threshold` event so a sleeping pixel wakes when a need crosses a line (16.1).
- [ ] 13.4 Finish the task as the action record (Task is already almost data; see the `task.py` findings).
      HOW: keep `entity.task`, but give `Task` these fields: `source` ("self" | "command"), `score`, `phase`, and one `state` dict for everything beyond `data` (replaces `blocked_for` and similar attributes). Add a registry so `load_task(dict)` can rebuild a task from a save, add `finish(entity, context, status)` called on DONE and FAILED too, and a `reason` code on failure. Remove `entity.task_score`, `components["order"]` and the `inf` score: "is this commanded?" becomes `task.source == "command"`, and `think()` checks that instead of `follow_orders`. `Task.to_dict()` then contains everything needed to save and replicate the action.
- [ ] 13.5 Priority rules in one place.
      HOW: `can_interrupt(current, candidate)`: a command always interrupts; a self-chosen action interrupts a self-chosen one only above `SWITCH_MARGIN`; nothing self-chosen interrupts a commanded action. Move the 1.3 constant and the rule out of `think()`.
- [ ] 13.6 Test: `tests/sim/check_action_state.py`. Needs rise over time at the configured rate, round-trip through `to_dict()`, and stay identical across two seeded runs. Run the determinism checks.

## Phase 14: The action pipeline (site -> travel -> perform -> update)
Goal: one shared lifecycle for every action, so a new action is a small declaration, not a new task class.

- [ ] 14.1 `ActionSpec`: what a behavior declares about each action it offers.
      HOW: in `sim/behaviors/behavior.py` add `actions = {"fish": ActionSpec(...)}` next to `params`. A spec holds: `args` (typed schema: point, entity, blueprint, item, number), `site` (14.2), `perform` (14.4), `update` (14.6), `satisfies` (needs it helps, used as a consideration), `commandable` (True/False), `failure` (the message that is in `FAILURE_REASONS` today), `click` (15.3). A behavior with no `actions` keeps working through the old generator/task path until it is ported (step 14.8), so nothing breaks midway.
- [ ] 14.2 `Site`: where an action can be done, with alternatives.
      HOW: `Site(kind="tile"|"entity"|"point", match=..., range=...)` where `range` is 0 (stand on it), 1 (adjacent) or a distance in units. An action lists alternatives in order of preference, each with a requirement on the actor: fishing = `[Site(tile has "water", range=1, needs={"item": "fishing_pole"}), Site(tile has "water", range=0)]`. The first alternative the actor satisfies wins, so the pixel with a pole stands on shore and the one without wades in. Requirements read the same stat registry (13.2) and the inventory.
- [ ] 14.3 Site finder (the only expensive new piece, so build it with Phase 9 in mind).
      HOW: `sim/navigation/sites.py`. Given actor, site, radius: return the nearest standing point that satisfies it, deterministically (sort by distance, then by tile coordinates). Do NOT scan tiles per pixel per think. Keep a per-chunk index "tile types present" built from the world (and updated by `world.set_tile`, which already feeds the delta log), so the finder visits only chunks that contain a matching tile. Cache the answer on the pixel (`action["site"]`) and re-validate it cheaply on arrival. Count it (`site_searches`, `site_tested`) and give it a per-tick budget like the think budget (9.9).
- [ ] 14.4 One `ActionTask` with fixed phases.
      HOW: phases `find_site -> travel -> perform -> resolve`. `travel` is the existing `step_toward` (and `roam` is ported onto it, so there is one mover). `perform` runs the spec's function every tick for `duration` seconds (or until it says done), with `elapsed` in `action["state"]`. Failure reasons are named once: `no_site`, `blocked`, `target_gone`, `timeout`, `refused`. The pixel's current phase is data, so the client can show "walking to water" vs "fishing".
- [ ] 14.5 Patience and abort rules in one place.
      HOW: global caps for travel time and blocked time (replaces `BLOCKED_PATIENCE`, `WAIT_PATIENCE`, `TIMEOUT` scattered in behaviors). Re-find the site once if it became invalid (someone else took the spot, tile changed) before failing.
- [ ] 14.6 The update step: what changes when an action finishes (or each cycle, for repeating actions).
      HOW: the spec's `update(ctx, actor, data) -> Outcome` returns a list of plain effects applied by one function: `change_stat`, `satisfy_need`, `add_inventory`, `spawn_item`, `remove`, `remember`, `emit_event`. The applier enforces the limits (9.9: spawn caps, world pixel cap) and emits events, so tasks never touch the spawner directly. Randomness uses `context.rng` only (catch chance, quantity), so replays stay deterministic.
- [ ] 14.7 Items on the ground.
      HOW: an item is a pixel from a blueprint with tag `item`, no behaviors, and a `size` (so the existing slots/cargo rules apply). `spawn_item(blueprint, x, y)` goes through `create_pixel`, so caps and replication already work. Add a `lifespan` or decay prop so unclaimed items do not pile up forever (a limit-9.9 concern). Add a storage container: a pixel with `slots` and tag `storage`; `deposit` is `drop` with a container target instead of a point.
- [ ] 14.8 Port the existing behaviors one at a time onto the pipeline: `move`, `roam`, `pickup`, `drop`, `spawn`, `attack`.
      HOW: after each, run its existing check and `check_sim_determinism`. `attack` keeps its attack-method code and its proximity-grid generator; only the approach loop is replaced by the shared travel phase. Leave `attack_generator`'s nearest-first test exactly as it is (it is the 9.7 fix).
- [ ] 14.9 Chaining without a planner.
      HOW: do not build GOAP. Utility AI already chains if the generators read the world after each update: after the catch there is a fish item nearby, so `pickup` offers it, with a consideration that scales with hunger and carried amount. Once carrying fish, `deposit` offers the nearest storage, with a consideration on how full the pixel is. Write each generator so its score rises when the world state calls for it. Add an optional `follow_up` hint on an ActionSpec (`fish.follow_up = "pickup"`) that adds a small score bonus to that action for a few seconds, so loops do not stall between steps.
- [ ] 14.10 Repeating actions and boredom.
      HOW: `fish` runs `duration` seconds per attempt and then re-decides, so hunger, boredom and new opportunities are re-scored each cycle. The existing hysteresis keeps a pixel from flipping between two similar actions. Boredom is a need that rises while the same action repeats and drops on a different one.
- [ ] 14.11 Full loop test: `tests/sim/check_fishing_loop.py`.
      HOW: a small world with a lake, storage and a hungry pixel with `fish`, `pickup`, `deposit`. Assert the order of events (travel -> perform -> fish item appears -> pickup -> travel -> deposit), once with a pole (stands next to water) and once without (stands in water), and that two seeded runs match.

## Phase 15: One command path
Goal: a command is "end the current action, start this one". No per-command files.

- [ ] 15.1 Define the one pixel command.
      HOW: `{"type": "command", "name": "do", "args": {"ids" | "box", "action": "fish", "data": {...}}}`. The server resolves the action name against the pixel's own behaviors, validates `data` against that `ActionSpec.args` (the same typed schema 14.1 declared), and starts a task with `source = "command"`. That is all `execute()` does for pixel actions. The protocol version bumps once (v8).
- [ ] 15.2 Gates shrink to what is really a rule.
      HOW: keep `gate_owner`, `gate_alive`. Replace `gate_trait` + `gate_behavior` with "the pixel has a behavior whose spec lists this action and `commandable=True`". The `command` permission behavior is then redundant (ownership already says who may order a pixel). Decide in step 15.5 whether to keep a way to mark a pixel as not-commandable (a wild tamed animal, an enemy-owned unit) or just delete the behavior.
- [ ] 15.3 Clicks pick the action from the specs, not a hard-coded table.
      HOW: each `ActionSpec` may declare `click(ctx, player_id, point) -> data | None` and a `click_priority`. `act` becomes: collect the commandable actions of the selected pixels, try their click resolvers in priority order (attack on a hostile pixel, pickup on your own pixel, fish on a water tile, move as the fallback), use the first that returns data. A new action gets right-click behavior by declaring `click`, with no edit to `act`.
- [ ] 15.4 Tell the client what each pixel can do.
      HOW: `inspect` (or a new `abilities` message) returns the list of commandable actions for a pixel: name, label, arg schema. The client builds the context menu from it instead of from hard-coded buttons. This is the "list all behaviors an entity can do" part.
- [ ] 15.5 Delete the redundant files.
      HOW: remove `sim/commands/move.py`, `attack.py`, `drop.py`, `pickup.py`, `spawn.py`, `act.py`'s per-action resolvers, the `command` behavior, `orders.py`, `FAILURE_REASONS`, `gate_behavior`/`gate_trait`, and the `component["order"]` path in `system_runner`. Keep `place`, `edit_property`, `save_blueprint` and `inspect` as player operations, in their own folder (suggest `sim/operations/`) so "command" only means pixel actions. Keep: ids/box selection, MAX_IDS, wake-on-command (9.3), `commands_deferred` and the inbox limits (9.9), and the `order_failed` notice (rename to `action_failed`, reason comes from the failure codes in 14.4).
- [ ] 15.6 Update the checks.
      HOW: port `check_commands` / `check_act` / `check_orders` style checks to `do`. Cases: a command interrupts a running self-chosen action; a self-chosen action cannot interrupt a command; a new command replaces the old one; a bad `data` is rejected with a readable reason; a pixel without the behavior is refused; box selection still filters by "can do this action".

## Phase 16: Scale, persistence, client
Goal: the loop stays cheap, saves correctly, and shows up on screen.

- [ ] 16.1 Rates and sleeping.
      HOW: a pixel with no need pressing and no action sleeps (9.3). A need crossing a threshold wakes it (schedule the wake instead of polling). Add `site_find` and `action_update` to `activity.RATES` so far pixels run them less often.
- [ ] 16.2 Budgets.
      HOW: per-tick caps on site searches and on effects applied (alongside `max_thinks`); deferred work keeps its place in line, as the think budget does. Add `Limits` entries and counters, and extend `check_limits` with a storm test (1000 hungry pixels, one lake).
- [ ] 16.3 Save and load the action.
      HOW: `entity.task` (via `Task.to_dict()` and the `load_task` registry from 13.4) and `entity.needs` go in `to_dict()` / `from_dict()` (they are plain data after 13.4). Needed before 10.2 is finished, otherwise loading a world makes every pixel forget what it was doing.
- [ ] 16.4 Replicate the action to clients.
      HOW: add `action` (name) and `phase` (small enum) to the pixel entry, quantized and sent only on change, so replication cost stays small. The client shows an icon or text over the pixel and in the inspect panel. This is also what makes the order-feedback ("it could not reach") consistent for self-chosen actions.
- [ ] 16.5 Load test.
      HOW: add a `behaviors` scenario to `tools/loadtest.py` (a population all running the fishing loop). Record the new maximum pixel count with the loop on, and compare with the old one in LOADTEST_RESULTS.md.
- [ ] 16.6 Determinism audit.
      HOW: run `audit_determinism.py` and `check_sim_determinism` after each phase; confirm no new `random` use, no set iteration, and that site-finder ties break by coordinates.

---

### Design decisions I made (change them if you disagree)
- **Stay with utility AI, no planner.** Your fish -> pickup -> deposit example works because each step's generator reacts to the new world state. A planner (GOAP) would cost far more per think and fight the Phase 9 budgets.
- **Needs are values, rules are a table.** State in `entity.needs`, behavior of needs in one editable table. Matches how `RATES` works.
- **The task is the action record.** `Task` already has `to_dict`; finishing it is required for saving, replication, and getting rid of the `inf`-score order trick.
- **Two kinds of commands.** Pixel actions (move, attack, fish...) become "do"; player operations (`place`, `edit_property`, `save_blueprint`, `inspect`) are not actions and stay separate.
- **Site finder uses a per-chunk tile index** rather than scanning tiles, because "nearest water" per pixel per think is the first thing that would blow the tick budget.

### Open Questions
- Does a commanded action ever fail silently and return to self-chosen behavior, or should the pixel idle until re-ordered? (Today: it returns to deciding on its own.)
- Should a player be able to queue commands (shift-click), or is it always replace-current? The pipeline supports a queue later if `entity.task` becomes a list.
- Fishing: infinite fish per tile, a regrowing count, or depletion (which needs a world delta, Phase 6)?
- Are items always pixels, or do some (like wood) stay as numbers in `inventory`? Mixed is fine, but pick which one fish are.
- Is the `command` permission worth keeping for pixels the owner should not be able to order (tamed animals, allied units)?