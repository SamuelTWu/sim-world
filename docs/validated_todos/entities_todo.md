# Part 0 of 3: Entity Foundation (one cheap entity for everything)

Build order: **0. Foundation (this file)**, then 1. Actions (`1_actions_todo.md`), 2. Items (`2_items_todo.md`), 3. Structures (`3_structures_todo.md`).

Goal: everything is an entity (units, items, blocks, trees), the base entity is as cheap as possible, and expensive systems only visit the entities that are flagged to use them. A wall, an item or a tree costs memory and nothing per tick; a unit that thinks costs what it costs today.

Parts 1 and 2 of this file change only how the simulation loops (no changes to `Entity`), so they are low risk and give most of the speed. Part 3 is the big refactor of `Entity` itself and gives most of the memory saving. Do them in order and stop whenever the numbers are good enough.

After this file, `2_items_todo.md` and `3_structures_todo.md` need a rewrite: items and structures become plain entities with a small component, not a separate "slim record" and not a separate block layer. Ask for that rewrite when Part 3 is done (or earlier, the plan below says what they will look like).

Conventions: relative imports only, no comments or docstrings, longer lines over more lines, snake_case files, an `__init__.py` in every folder, pygame only in `client/`. Dependency direction `shared < world < content < sim < server`. Run every existing check, `check_sim_determinism` and `audit_determinism` after each step.

How to read a step: **Do** is what to change, **Done when** is how you know it works.

---

## The idea in one page

An entity is a small **base** plus optional **components**. A component exists only on entities that have it. Systems keep **membership sets** and loop over those sets, never over "all entities".

**Base (every entity, always):** `id`, `kind`, a reference to its `template`, position, `owner`, `alive`, a `flags` bitmask (`visible`, `blocks_movement`, `blocks_sight`, ...), `born_tick`, and the current `health` and `energy`.

**Template (shared by every entity of one blueprint, read-only):** `name`, `sprite_id`, `max_health`, `max_energy`, `tags`, `props`, `traits` and their values, `reactions`, `size`, `slots`. An entity reads these from its template. When one entity changes its own copy (the player edits a trait, a status changes a prop) it gets a private copy first (copy-on-write).

**Components (lazy, only when present):**

| component | holds | is in the set |
|---|---|---|
| `needs` | the `Need` objects | `needy` |
| `think` | the running `task`, `task_score`, the think timer, memory (kept in `MemorySystem`) | `thinkers` (has action traits or a task) |
| `inventory` | resources, `cargo`, `carried_by` | none (only touched by ops) |
| `statuses` | active status effects | `statused` |
| `scratch` | `components` dict (heading, grudges...) | none |
| `item` / `structure` | what the items and structures files add: resource and amount, or resource and cell | none |

**The sets and what "awake" means.** Two different things, named differently:
- **capable**: the entity has the components a system needs (it *can* think). This is data and changes only when a component is added or removed.
- **awake**: it currently needs to be visited. A capable entity that has nothing to do goes to sleep (this exists today, 9.3) and leaves the awake set; waking (a command, a nearby change, an interrupt, a need threshold) puts it back.

`SystemRunner.update` loops over the awake entities in id order and nothing else. Items, blocks and trees are never capable of anything, so they are never visited.

**Targets for this file** (measure them in Part 0):
- adding 20,000 inert entities adds under 1 ms to the tick;
- an inert entity uses under 300 bytes (today every entity is about 1,160);
- bytes sent per client stay flat tick to tick when 5,000 inert entities are in view;
- no existing check regresses and the determinism checks stay identical.

---

## Part 0: Measure first

- [ ] **0.1 A baseline workload with many inert entities**
  **Do:** add a `--statics N` option to `tools/profile_sim.py` and `tools/loadtest.py`: spawn N entities that have no traits and no needs (a stand-in for items and blocks), spread over the world, next to the normal units. Record, for N of 0, 5,000 and 20,000: tick time (p50 and p95), memory per entity (RSS before and after, or `tracemalloc`), and bytes sent per client per tick.
  **Done when:** the three numbers per N are written in `LOADTEST_RESULTS.md` under "Foundation baseline".
- [ ] **0.2 List every place that visits all entities**
  **Do:** `grep -rn "\.all()\|entities()\|for .* in .*entities" src` and make a table in the project layout doc: file, what it does, how often (every tick, on an event), and whether it can use an index instead. Expect at least: `SystemRunner.update`, `ProximityIndex` (rebuilt per tick), the replication diff, `rules.nearby`, `visibility`, `pick_entity` in commands, `activity`.
  **Done when:** the table exists and every row has a planned fix (a step number below, or "fine").

## Part 1: Membership sets (the `Entity` class does not change)

- [ ] **1.1 The roster**
  **Do:** `sim/core/roster.py`: a `Roster` with ordered membership per system (`thinkers`, `needy`, `statused`) and an `awake` set, all as insertion-ordered dicts (never a plain `set`, for determinism). API: `sync(entity)` recomputes which sets the entity belongs to from its current components, `drop(entity)`, `sleep(entity)`, `wake(entity)`, and `active_list()` returning the awake capable entities sorted by id (cached, rebuilt only when something changed). For now `sync` reads the existing fields: `thinkers` if `entity.traits` or `entity.task`, `needy` if `entity.needs`, `statused` if `entity.statuses`.
  **Done when:** `check_roster.py` (step 1.4) passes on a world built with the old `Entity`.
- [ ] **1.2 Call `sync` at every change**
  **Do:** call `roster.sync(entity)` at spawn, after traits change (blueprint apply, `edit_property`), when a need is added or removed, when a status is added or expires, and when a task starts or ends. Put these calls behind one function each (`add_need`, `add_status`...) so there is one place to fix.
  **Done when:** `grep` shows no code writing `entity.needs[...]`, `entity.statuses.append` or `entity.traits[...]` outside those functions (the consistency test in 1.4 catches the rest).
- [ ] **1.3 The loop visits only the roster**
  **Do:** in `SystemRunner.update`, replace `entities = self.entities()` with `self.roster.active_list()` for the per-entity phase. `cleanup_removed` still handles removals from the full manager and also calls `roster.drop`. Entities in no set are not visited at all (they are not aged, not asked for activity state, not given a think slot).
  **Done when:** with `--statics 20000` the tick time is within 1 ms of `--statics 0`, and every old check passes.
- [ ] **1.4 The consistency check**
  **Do:** `tests/sim/check_roster.py`: run random operations (spawn, add and remove a trait, add a need, add and expire a status, start and end a task, sleep, wake, kill), and after each batch rebuild the sets from scratch and assert they equal the live ones, in the same order. Assert that iteration is by id.
  **Done when:** it passes for 10,000 random operations on three seeds.
- [ ] **1.5 Sleeping leaves the awake set**
  **Do:** make `activity` call `roster.sleep(entity)` when a pixel goes to sleep and `roster.wake(entity)` from `wake()`, from `moved()` (a pixel arriving next to sleepers), from commands (9.3), and from the interrupt flag (6b.2 of the actions file). Keep the time a sleeper is owed exactly as it works now.
  **Done when:** 10,000 sleeping pixels cost about as little per tick as 10,000 inert ones, and the existing sleep checks (`check_sleep`, `check_activity`) pass unchanged.
- [ ] **1.6 Measure again**
  **Do:** rerun 0.1.
  **Done when:** the target "20,000 inert entities add under 1 ms" is met, and the result is recorded.

## Part 2: Timers instead of per-tick checks

- [ ] **2.1 A timer heap**
  **Do:** `sim/core/timers.py`: `schedule(tick, kind, entity_id)` and `due(tick)` returning the entries for that tick in the order they were scheduled (a heap keyed by `(tick, sequence)`). A timer for an entity that no longer exists is skipped when it comes due. Timers are not saved: they are rebuilt from entity data on load.
  **Done when:** `check_timers.py`: order is by tick then schedule order, a removed entity's timer is skipped, a 100,000-timer test runs fast.
- [ ] **2.2 Lifespan through timers**
  **Do:** a template prop `lifespan` (seconds) schedules a `"expire"` timer at spawn for `born_tick + ceil(lifespan / dt)`; the runner processes `timers.due(tick)` once per tick and kills what expires through the normal removal path. Remove any per-tick age check for lifespan.
  **Done when:** an entity with `lifespan` 5 s is gone after exactly 100 ticks at 20 Hz, and 20,000 entities with lifespans cost nothing between expiries.
- [ ] **2.3 Other timed things (list only)**
  **Do:** write in the layout doc which later features should use timers instead of per-tick checks: status expiry, reaction `cooldown`, item stack decay, crop growth, scheduled wakes (a need crossing a threshold).
  **Done when:** the list exists.

## Part 3: The slim `Entity`
Each step keeps the game running. Do them in order.

- [ ] **3.1 Field audit**
  **Do:** for every field of `Entity`, list which files read it and which write it (`grep`), in a table in the layout doc. The write sites are the ones that must change.
  **Done when:** the table exists.
- [ ] **3.2 Component accessors**
  **Do:** keep the same attribute names but make the lazy ones properties: a read returns the real value or a shared empty read-only value (`needs` -> an empty read-only mapping, `statuses` -> an empty tuple); a write goes through `entity.own("needs")`, which creates the real container on first use and calls `roster.sync`. Writing into the shared empty value raises, so every missing write site is found by the checks, not by silent bugs.
  **Done when:** all checks pass with the properties in place and no code writes into an empty shared value.
- [ ] **3.3 Slots and a lighter position**
  **Do:** turn `Entity` into a class with `__slots__` (it has `StatusEffect`, `Vec3` as dataclasses today: give `Vec3` and `StatusEffect` `slots=True` too). Keep `entity.position.x` working.
  **Done when:** memory per entity drops (measure with 0.1) and nothing else changes.
- [ ] **3.4 Templates (copy-on-write)**
  **Do:** `entity_factory` compiles each blueprint once into a read-only `Template` (name, sprite, max values, tags as a frozenset, props, traits with their validated values, reactions, size, slots). `entity.traits`, `props`, `tags`, `reactions`, `name`, `sprite_id` read from `entity.template`; `entity.own("props")` first copies the template's dict into the entity. Behavior `apply(entity, values)` currently writes props per entity (for example `max_speed`): move that to template compile time, so every entity of a blueprint shares the result. A pixel whose blueprint is edited in the editor gets a new template.
  **Done when:** two entities of one blueprint share the same `traits` object until one is edited, and editing one does not change the other (`check_template.py`).
- [ ] **3.5 Current values only**
  **Do:** per entity keep only what changes: `health`, `energy` (and `None` = full where that is common), position, `born_tick`. `max_health`, `max_energy` come from the template.
  **Done when:** a template-only entity (an item) has no per-entity dicts at all.
- [ ] **3.6 Age without a per-tick increment**
  **Do:** `age` becomes a property: `(clock.tick - born_tick) * clock.dt`, where `clock` is a small object the simulation owns and each entity references (one reference, no global, so two simulations in one process stay independent). Remove `entity.age += delta_time` from the loop. Statuses keep their own age but only for `statused` entities.
  **Done when:** `age` reads the same as before in the existing reaction and stat checks, and an inert entity is never aged.
- [ ] **3.7 Save only what exists**
  **Do:** `to_dict` writes the template id plus the base and the components that are present; `from_dict` accepts the old full format too.
  **Done when:** an inert entity saves in under 100 bytes of msgpack, and an old save still loads.
- [ ] **3.8 Measure**
  **Do:** rerun 0.1.
  **Done when:** an inert entity uses under 300 bytes and all four targets are met (or the missing one is written down with the reason).

## Part 4: Replication and spatial lookups

- [ ] **4.1 The `static` flag**
  **Do:** an entity that is in no awake set, has no task and cannot move is `static`. The pixel entry the server sends carries `static: true`; the server sends it once when it enters a client's view and again only when something about it changes (health, removal). The client skips interpolation for it.
  **Done when:** with 5,000 inert entities in view, bytes per client per tick are flat (measure with the 9.1 metrics).
- [ ] **4.2 The spatial index is incremental**
  **Do:** `ProximityIndex` is currently rebuilt each tick from every entity. Split it into a static layer (built once, updated only on spawn, removal and change) and a dynamic layer (rebuilt per tick from the awake movers). Interest management (7.x) and `pick_entity` use the same two layers.
  **Done when:** 20,000 inert entities add nothing to `ProximityIndex` time per tick, and the existing proximity and interest checks pass.
- [ ] **4.3 Cell occupancy**
  **Do:** a `cell_index` (grid cell to entity id) for things that occupy a cell (structures); the same incremental updates. The structures file uses it for `occupied`.
  **Done when:** it matches a full scan after a long random test.

## Part 5: Tooling and docs

- [ ] **5.1 Metrics.** Count `entities_total`, `entities_capable`, `entities_awake` and the per-phase tick times (9.1); the load test prints them.
- [ ] **5.2 Limits.** `MAX_PIXELS_IN_WORLD` counts capable entities; add a separate, larger cap for inert ones (items and structures), both in `Limits`, with counters.
- [ ] **5.3 Determinism.** Every set and heap iterates in a fixed order; run `check_sim_determinism` and `audit_determinism`; add `check_roster` and `check_timers` to `tools/run_checks.py`.
- [ ] **5.4 Docs.** Put the component table, the sets, and the rule "add a component only through `own()` or `add_*`" in the project layout doc.

---

### Decided
- `health` and `energy` stay as base fields on every entity (plain floats).
- `born_tick` is saved, and `age` is computed from it.
- The size target is under 300 bytes per inert entity (no need to go below, so `Vec3` stays).
- Editing a blueprint does not change existing entities: they keep the template they were built from (the template's `traits` are copied, not shared live). Step 3.4 already works this way: an edited blueprint compiles to a new template.

### Future requirement: everything is configurable from JSON
Every entity kind (units, items, structures, trees, ores) must be fully definable by one `.json` file in `content/`, with no Python needed, so other users can add their own. Keep this in mind in every step:
- The template compiler (3.4) reads only JSON: base fields, `tags`, `props`, `traits`, `needs`, `reactions` (including `drops`), `slots`, `size`, `lifespan`, and the `item` / `structure` components.
- Components are switched on by what the JSON contains (a `needs` key adds the `needs` component, an `item` key the `item` component). No blueprint needs a hand-written class.
- Unknown keys, bad values and missing references give a clear `BlueprintError` that names the file and key.
- Add a step when Part 3 is done: a `content/blueprints/README` or schema doc plus one example file per kind, and `check_blueprints.py` loading every file in `content/` through the compiler.

### What the other files become after this one
- **Items:** an entity from the `item` template with an `item` component `{resource, amount}` and a `lifespan` (a timer). No traits, no needs, not in any set. `make_item` merges stacks using the cell index.
- **Structures:** an entity from the `structure` template with a `structure` component `{resource}` and its own `health`; not in any set; the cell index gives `occupied` in O(1). If thousands of identical blocks ever cost too much (the structures load test will tell), a chunk-overlay block layer can replace them behind the same `build_structure` and `modify` interface.
- **Actions:** `modify`, reactions and `drops` work on any entity; reactions come from the template, so they cost no per-entity memory.

### Reused as they are
`Task`, `stats.py`, `NeedSystem`, `MemorySystem` (stored by id, outside the entity), `activity` (its sleep logic stays, it just also moves the entity in and out of the awake set), the 9.9 `Limits`, the 9.1 metrics.

### Open questions
None left in this file.