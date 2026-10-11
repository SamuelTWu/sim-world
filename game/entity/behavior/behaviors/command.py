from ..behavior import Behavior, Param


class Command(Behavior):
    """Not an action: the permission for a player to give this pixel orders.

    "traits": {"command": {"attack": true}} lets the player order the pixel to attack. The pixel also needs the
    behavior itself (an "attack" trait); a pixel with the behavior but not this permission does it only on its own
    (a wild animal, say). Add a line to `params` when a new command is added.
    """

    name = "command"
    kind = "permission"
    tier = 0
    base_cost = 0.0
    description = "Lets the player order this pixel to do the things it can do."

    params = {
        "move": Param(default=False, description="Player may order it to go somewhere"),
        "attack": Param(default=False, description="Player may order it to attack"),
        "spawn": Param(default=False, description="Player may order it to create another pixel"),
        "pickup": Param(default=False, description="Player may order it to pick up another pixel"),
        "drop": Param(default=False, description="Player may order it to put resources on the ground"),
    }