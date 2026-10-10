from ...entity.behavior.behaviors.spawn import SPAWN_GATES, refusal
from ..command import Command, Outcome, Rejected, as_blueprint, as_ids, as_point, clean_args, command, issue_order, select_pixels


@command
class Spawn(Command):
    """Order pixels to create ANOTHER pixel. args: {"ids": [pixel ids], "blueprint": blueprint id, "target": [x, y] (optional)}.

    A command for pixels, like `move`: only pixels you own, that are alive, that carry the "command" permission for
    "spawn" and have the `spawn` behavior obey (the others are skipped). The player creating a pixel is `place` instead.
    A valid command only stores the order {"kind": "spawn", "blueprint", "x", "y", "tick", "issuer"} ("x"/"y" are left out
    when no target was given, meaning "next to the parent") and emits "order_issued"; the spawn behavior carries it out
    (entity/behavior/behaviors/spawn.py) and charges the parent the spawn cost (still undecided). Spawning never needs
    inventory: it creates a NEW pixel. Moving something that exists is `transfer`; making something from the inventory
    exist in the world is `drop`; the player creating one is `place`.

    SPAWN_GATES (defined in the spawn behavior, so pixels spawning on their own obey them too) are checks on the blueprint itself: functions (ctx, parent, blueprint_id, definition) that return a
    reason to refuse, or None. They run once per command, with parent=None.
    """

    name = "spawn"

    def run(self, ctx, player_id, args):
        keys = ("ids", "blueprint", "target") if "target" in args else ("ids", "blueprint")
        clean_args(args, *keys)
        ids = as_ids(args["ids"])
        blueprint_id, definition = as_blueprint(args["blueprint"], ctx)
        point = as_point(args["target"], ctx) if "target" in args else None

        reason = refusal(ctx, None, blueprint_id, definition)

        if reason:
            raise Rejected(reason)

        pixels, ignored = select_pixels(ctx, player_id, ids, self.name, self.strict)
        order = {"kind": "spawn", "blueprint": blueprint_id, "tick": ctx.tick, "issuer": player_id}

        if point is not None:
            order["x"], order["y"] = point

        for pixel in pixels:
            issue_order(ctx, pixel, dict(order))

        return Outcome(True, applied=[pixel.id for pixel in pixels], ignored=ignored)