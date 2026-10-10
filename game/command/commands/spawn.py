from ..command import Command, Outcome, Rejected, as_blueprint, as_ids, as_point, clean_args, command, issue_order, select_pixels


def gate_spawnable(ctx, parent, blueprint_id, definition):
    """A blueprint can opt out with "spawnable": false."""
    return None if definition.get("spawnable", True) is not False else "that blueprint cannot be spawned"


SPAWN_GATES = [gate_spawnable]


@command
class Spawn(Command):
    """Order pixels to create ANOTHER pixel. args: {"ids": [pixel ids], "blueprint": blueprint id, "target": [x, y] (optional)}.

    This is a command for pixels, like `move`: only pixels you own, that are alive and that carry the "command"
    trait for "spawn" obey it (the others are skipped). The player creating a pixel is `place` instead.
    Like `move`, a valid command only stores an order on each obeying pixel:
    {"kind": "spawn", "blueprint", "x", "y", "tick", "issuer"} ("x"/"y" are left out when no target was given, meaning
    "next to the parent"), and emits "order_issued". Nothing carries it out yet: when a behavior does, it should call
    ctx.spawn(definition, pixel.owner, x, y) and charge the parent the spawn cost (the cost itself
    is still undecided). Spawning never needs inventory: it creates a NEW pixel. Moving something that exists is
    `transfer`; making something from the inventory exist in the world is `drop`; the player creating one is `place`.

    SPAWN_GATES are checks on the blueprint itself: functions (ctx, parent, blueprint_id, definition) that return a
    reason to refuse, or None. They run once per command, with parent=None.
    """

    name = "spawn"

    def run(self, ctx, player_id, args):
        keys = ("ids", "blueprint", "target") if "target" in args else ("ids", "blueprint")
        clean_args(args, *keys)
        ids = as_ids(args["ids"])
        blueprint_id, definition = as_blueprint(args["blueprint"], ctx)
        point = as_point(args["target"], ctx) if "target" in args else None

        for gate in SPAWN_GATES:
            reason = gate(ctx, None, blueprint_id, definition)

            if reason:
                raise Rejected(reason)

        pixels, ignored = select_pixels(ctx, player_id, ids, self.name, self.strict)
        order = {"kind": "spawn", "blueprint": blueprint_id, "tick": ctx.tick, "issuer": player_id}

        if point is not None:
            order["x"], order["y"] = point

        for pixel in pixels:
            issue_order(ctx, pixel, dict(order))

        return Outcome(True, applied=[pixel.id for pixel in pixels], ignored=ignored)