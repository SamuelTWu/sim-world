LOBBY, PLACEMENT, PLAYING = "lobby", "placement", "playing"
PHASES = (LOBBY, PLACEMENT, PLAYING)
WRONG_PHASE = "wrong_phase"
COMMAND_PHASES = {"place_colony": {PLACEMENT}, "lobby_*": {LOBBY}}
DEFAULT_PHASES = {PLAYING}


def phases_for(command_type: str) -> set:
    if command_type in COMMAND_PHASES:
        return COMMAND_PHASES[command_type]

    for pattern, phases in COMMAND_PHASES.items():
        if pattern.endswith("*") and command_type.startswith(pattern[:-1]):
            return phases

    return DEFAULT_PHASES


def allowed(phase: str, command_type: str) -> bool:
    return phase in phases_for(command_type)