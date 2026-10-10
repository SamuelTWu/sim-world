from ..command import Command, Outcome, Rejected, as_blueprint, as_point, clean_args, command

PLACE_GATES = []


def gate_placeable(ctx, player_id, blueprint_id, definition):
    """A blueprint can opt out with "placeable": false."""
    return None if definition.get("placeable", True) is not False else "that blueprint cannot be placed"


PLACE_GATES.append(gate_placeable)


@command
class Place(Command):
    """The PLAYER creates a pixel from a saved blueprint, by dropping it on the map. args: {"blueprint": blueprint id, "position": [x, y] in world units}.

    This is the player's own power, not an order to a pixel (that is `spawn`): it needs no pixel and no command trait.
    The new pixel belongs to the player. Nothing is paid and nothing has to be unlocked yet: that is what PLACE_GATES
    is for. Each gate is a function (ctx, player_id, blueprint_id, definition) that returns a reason to refuse, or None.
    Add the currency and tech-unlock checks there when they exist (Phase 5.2 / 5.5). There is also no limit on how
    many a player can place, which the cost will provide once it exists.

    "place" is a working name; to rename it, change `name` below, this file's name, and the one string in game.py.
    """

    name = "place"

    def run(self, ctx, player_id, args):
        clean_args(args, "blueprint", "position")
        blueprint_id, definition = as_blueprint(args["blueprint"], ctx)
        x, y = as_point(args["position"], ctx)

        for gate in PLACE_GATES:
            reason = gate(ctx, player_id, blueprint_id, definition)

            if reason:
                raise Rejected(reason)

        pixel = ctx.spawn(definition, player_id, x, y)
        return Outcome(True, applied=[pixel.id])