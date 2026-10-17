
## Phase 14: The action pipeline (site -> travel -> perform -> update)
Goal: one shared lifecycle for every action, so a new action is a small declaration, not a new task class.

- [ ] 14.1 `ActionSpec`: what a behavior declares about each action it offers.
      HOW: in `sim/behaviors/behavior.py` add `actions = {"fish": ActionSpec(...)}` next to `params`. A spec holds: `args` (typed schema: point, entity, blueprint, item, number), `site` (14.2), `perform` (14.4), `update` (14.6), `must_change` (True when the action exists to change the world or a stat, see 14.4), `relieves` (needs with no physical cause that finishing the action lowers, as fractions of range; moved here from `params["relieves"]` in 13.3b, and only for abstract actions such as `roam`), `commandable` (True/False), `failure` (the message that is in `FAILURE_REASONS` today), `click` (15.3). Which need ranks an action is not in the spec: it is the action's own consideration (`need_level("hunger")`). A behavior with no `actions` keeps working through the old generator/task path until it is ported (step 14.8), so nothing breaks midway.
- [ ] 14.2 `Site`: where an action can be done, with alternatives.
      HOW: `Site(kind="tile"|"entity"|"point", match=..., range=...)` where `range` is 0 (stand on it), 1 (adjacent) or a distance in units. An action lists alternatives in order of preference, each with a requirement on the actor: fishing = `[Site(tile has "water", range=1, needs={"item": "fishing_pole"}), Site(tile has "water", range=0)]`. The first alternative the actor satisfies wins, so the pixel with a pole stands on shore and the one without wades in. Requirements read the same stat registry (13.2) and the inventory.
- [ ] 14.3 Site finder (the only expensive new piece, so build it with Phase 9 in mind).
      HOW: `sim/navigation/sites.py`. Given actor, site, radius: return the nearest standing point that satisfies it, deterministically (sort by distance, then by tile coordinates). Do NOT scan tiles per pixel per think. Keep a per-chunk index "tile types present" built from the world (and updated by `world.set_tile`, which already feeds the delta log), so the finder visits only chunks that contain a matching tile. Cache the answer on the pixel (`action["site"]`) and re-validate it cheaply on arrival. Count it (`site_searches`, `site_tested`) and give it a per-tick budget like the think budget (9.9).
- [ ] 14.4 One `ActionTask` with fixed phases.
      HOW: phases `find_site -> travel -> perform -> resolve`. `travel` is the existing `step_toward` (and `roam` is ported onto it, so there is one mover). `perform` runs the spec's function every tick for `duration` seconds (or until it says done), with `elapsed` in `action["state"]`. Failure reasons are named once: `no_site`, `blocked`, `target_gone`, `timeout`, `refused`, `no_effect`. The pixel's current phase is data, so the client can show "walking to water" vs "fishing".
      HONEST RESULT: in `resolve`, an action whose spec sets `must_change=True` and whose `update` returned no effects ends FAILED with `no_effect`, never DONE. This is what keeps needs honest now that nothing global lowers them: a pixel that reached the spot and got nothing must not count as having succeeded. Every FAILED goes through `finish` (13.4), which records the backoff.
- [ ] 14.5 Patience and abort rules in one place.
      HOW: global caps for travel time and blocked time (replaces `BLOCKED_PATIENCE`, `WAIT_PATIENCE`, `TIMEOUT` scattered in behaviors). Re-find the site once if it became invalid (someone else took the spot, tile changed) before failing. Do not add a retry loop here: after the failure, retrying is the decision system's job, held back by the failure penalty (13.5).
- [ ] 14.6 The update step: what changes when an action finishes (or each cycle, for repeating actions).
      HOW: the spec's `update(ctx, actor, data) -> Outcome` returns a list of plain effects applied by one function: `change_stat`, `change_need` (calls `NeedSystem.change`, 13.3b; replaces the old `satisfy_need`), `consume_item`, `add_inventory`, `spawn_item`, `remove`, `remember`, `emit_event`. The applier enforces the limits (9.9: spawn caps, world pixel cap) and emits events, so tasks never touch the spawner directly. Randomness uses `context.rng` only (catch chance, quantity), so replays stay deterministic.
- [ ] 14.7 Items on the ground.
      HOW: an item is a pixel from a blueprint with tag `item`, no behaviors, and a `size` (so the existing slots/cargo rules apply). `spawn_item(blueprint, x, y)` goes through `create_pixel`, so caps and replication already work. Add a `lifespan` or decay prop so unclaimed items do not pile up forever (a limit-9.9 concern). Add a storage container: a pixel with `slots` and tag `storage`; `deposit` is `drop` with a container target instead of a point.
      ITEM EFFECTS: an item blueprint may carry `"effects": {"hunger": -0.4}`, signed fractions of the need's range (the same unit as `relieves`). Consuming the item applies each entry through `NeedSystem.change` (14.6 `consume_item`). A fish, a berry and a loaf differ only in their numbers; nothing in `need_system` knows what food is.
- [ ] 14.7b `eat` action (the physical counterpart of the 13.3b `relieves` rule).
      HOW: a behavior in `sim/behaviors/eat.py` with one `ActionSpec`: site = a carried item or an adjacent item pixel that has `effects` (range 0 for carried, 1 for ground), `must_change=True`, `update` returns `consume_item` plus the item's `change_need` effects. Its consideration is `Consideration(need_level("hunger"), ramp(0.1, 1.0))`. No food in reach: `no_site`, a failure like any other, so the backoff in 13.4/13.5 applies. It is commandable, so a player can order "eat that". Add `eat` to the `applies` list for hunger in `DEFAULT_NEEDS` only for pixels that have it.
- [ ] 14.8 Port the existing behaviors one at a time onto the pipeline: `move`, `roam`, `pickup`, `drop`, `spawn`, `attack`.
      HOW: after each, run its existing check and `check_sim_determinism`. `attack` keeps its attack-method code and its proximity-grid generator; only the approach loop is replaced by the shared travel phase. Leave `attack_generator`'s nearest-first test exactly as it is (it is the 9.7 fix).
      ROAM DECISION (deferred from 13.3, settle it here): `roam` currently reads `exploration` (default 0.5 when absent). When `roam` is ported, give it `relieves: {"boredom": 0.1}` (as an `ActionSpec` field) and score it with `Consideration(need_level("boredom"), ramp(0.1, 1.0))` multiplied by `exploration`, so roamers rest until bored but blueprints that set `exploration` still tune it. If this changes how existing worlds look too much, keep the old `exploration`-only score and write the choice and the reason into this item; do not leave it unrecorded.
- [ ] 14.9 Chaining without a planner.
      HOW: do not build GOAP. Utility AI already chains if the generators read the world after each update: after the catch there is a fish item nearby, so `pickup` offers it, with a consideration that scales with `need_level("hunger")` and carried amount. Once carrying fish, `eat` (14.7b) offers it when hungry, and `deposit` offers the nearest storage with a consideration on how full the pixel is. Write each generator so its score rises when the world state calls for it. Add an optional `follow_up` hint on an ActionSpec (`fish.follow_up = "pickup"`) that adds a small score bonus to that action for a few seconds, so loops do not stall between steps.
- [ ] 14.10 Repeating actions and boredom.
      HOW: `fish` runs `duration` seconds per attempt and then re-decides, so hunger, boredom and new opportunities are re-scored each cycle. The existing hysteresis keeps a pixel from flipping between two similar actions. Boredom is a need that rises while the same action repeats and drops on a different one: implement it with `NeedSystem.change` in the repeat check (a small raise each time the same action is chosen twice in a row, a fixed drop when a different one finishes), not with a rate multiplier (those stay in 16.1). LATER, NOT IN THIS PHASE: boredom could also drop when a pixel sees new chunks (novelty); if that is wanted, add it in 16.1 as one more caller of `change`, with no change to the need system.
- [ ] 14.11 Full loop test: `tests/sim/check_fishing_loop.py`.
      HOW: a small world with a lake, storage and a hungry pixel with `fish`, `pickup`, `deposit`, `eat`. Assert the order of events (travel -> perform -> fish item appears -> pickup -> travel -> deposit), once with a pole (stands next to water) and once without (stands in water), that eating a fish lowers hunger by exactly the item's `effects` entry (not by a table value), and that two seeded runs match.
- [ ] 14.11b Starvation / no-loop test: `tests/sim/check_no_food_backoff.py`.
      HOW: a hungry pixel with `eat` and `roam` in a world with no food. Assert: `eat` ends FAILED with `no_site`, hunger is not lowered, the pixel does not retry `eat` until the cooldown from 13.4 has passed (count the `eat` task starts over N ticks: at most one per cooldown), it roams in between, hunger keeps rising to its maximum, and the cooldown grows with repeats up to `MAX_BACKOFF_STEPS`. Then drop food next to it: it eats on the next allowed attempt and hunger falls by the item's effect. Also assert a task that reaches its site but whose `update` returns nothing ends `no_effect`, not DONE. Two seeded runs match.

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