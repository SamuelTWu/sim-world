# TODO
## This is a detailed, step by step guide for implementation. Everything is specific and thought out


## Definitions:
Action: something an entity can do, as defined by : an entity completes the 'fishing' action, it references fishing.json, 
Task: the action an entity wants to do. Wraps (Move, action, outcome) in one.


## Behavior (13):
Every entitiy, from a worker, a bee, a Dune Worm, Santa, a boat, a bicycle and a mobster, follows this loop:

    stats -> needs -> decision -> site (where) -> travel -> perform -> update -> (stats changed, decide again)

a player command is just "do this action now".

- [x] 13.1 Audit the real `need_system.py`, `decision_system.py`, `considerations.py`, `memory_system.py`, `task.py`.
      HOW: list what each stores, what is already data vs code, and which behaviors read or write needs. Write the result at the top of this file. If the need system is still the stub (`update` does nothing), 13.3 is a full build, not a tweak.
- [x] 13.2 One stat registry (delivered in `p13_1/`: `stats.py`, `check_stats.py`, `PATCH_13.2.md`; remaining: switch `rules.py` per the patch, and use `reader(...)` for new considerations).
      HOW: `sim/ai/stats.py` with `STATS = {name: function(entity) -> float}`. Start from the table already in `rules.py` (`health`, `energy`, `age`, `carried`), add `hunger`-style readings of needs and `inventory:<resource>`. `rules.py` conditions, considerations and needs all read through it, so "what can I compare" is defined once and shows up in the editor.
- [x] 13.3 Needs table and what satisfies them (delivered in `p13_1/`: `need_system.py`, `check_needs.py`, `PATCH_13.3.md`; remaining: the one runner edit).
    NOTE: satisfies is a placeholder for now. It doesn't reflect the real world, and thus will be replaced by external feedback for tasks. A FAILURE flag will be sent to prevent looping. 
- [] 13.4 From that table, grab the highest rated need. Make the task persistent 