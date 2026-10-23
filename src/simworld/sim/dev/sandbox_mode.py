from .layout import build_sandbox_entities

SANDBOX_SEED = 0


def prepare_sandbox(sim, seed=None):
    section_seed = SANDBOX_SEED if seed is None else seed
    sim.generation_settings.mode = "sandbox"
    sim.sandbox = True
    sim.sandbox_gen = {"seed": section_seed, "disabled_features": set(), "disabled_maps": set()}
    return section_seed


def populate_sandbox(sim, max_player_pixels=None, max_world_pixels=None, max_spawns_per_tick=None, max_thinks_per_tick=None):
    def unlimited(value):
        return 0 if value is None else value

    sim.systems.limits.configure(unlimited(max_player_pixels), unlimited(max_world_pixels), unlimited(max_spawns_per_tick), 0, unlimited(max_thinks_per_tick))
    return build_sandbox_entities(sim)