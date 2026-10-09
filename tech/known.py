"""Names the game really defines, so the tech tree's `provides` lists can be checked against them.

Only categories listed here are checked; the others (props, structures, resources, and traits until the behavior
registry is added) accept any name. This file is allowed to import game code, tech.py is not.
"""


def known_names():
    from game.command.command import COMMANDS, load_commands
    from game.entity.system.rules import EFFECTS, TRIGGERS

    load_commands()
    return {"commands": set(COMMANDS), "triggers": set(TRIGGERS), "effects": set(EFFECTS)}