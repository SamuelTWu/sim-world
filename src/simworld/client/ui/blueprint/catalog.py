"""What behaviors exist and what their parameters are, for the blueprint editor.

The editor must offer exactly what the server will accept, so this reads the behavior framework itself
(BehaviorManager.to_dict()) instead of keeping a second list. It is plain data: name -> {kind, tier, base_cost, requires,
params: {key: {default, minimum, maximum, weight, choices, description}}, description}. If the behaviors cannot be
loaded the catalog is empty and the editor says so. This is the only place in the GUI that touches behavior code; when
the client should learn the catalog from the server instead (a joined game running different behaviors), change it here.
"""
_catalog = None


def behavior_catalog():
    global _catalog

    if _catalog is None:
        try:
            from src.simworld.sim.behaviors.behavior_manager import BehaviorManager

            _catalog = BehaviorManager().to_dict()["behaviors"]
        except Exception as problem:  # the editor still opens; it just has nothing to add
            print(f"[gui] could not load the behavior catalog: {problem}")
            _catalog = {}

    return _catalog