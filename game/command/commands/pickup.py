from ..command import Command, Outcome, Rejected, as_ids, clean_args, command, is_int, issue_order, select_pixels

PICKUP_GATES = []


def gate_owned(ctx, player_id, target):
    """The target must exist, be alive and be yours. One message for all of it, so ids cannot be probed."""
    return None if target is not None and target.alive and target.owner == player_id else "invalid target"


PICKUP_GATES.append(gate_owned)


@command
class Pickup(Command):
    """Order pixels to pick up another pixel. args: {"ids": [pixel ids], "target": a pixel id}.

    A command for pixels, like `move`, `attack` and `spawn`: only pixels you own, that are alive, that carry the "command"
    permission for "pickup" and have the `pickup` behavior obey. The picked-up pixel goes into their inventory (see
    entity/inventory.py) until `drop` puts it down. There is no separate "transfer": handing something over is one pixel
    dropping it and another picking it up. A pixel cannot pick up itself.

    The target must be alive and yours, otherwise "invalid target". PICKUP_GATES are the place to loosen that later (allies,
    neutral things): functions (ctx, player_id, target) returning a reason to refuse, or None.

    A valid command only stores {"kind": "pickup", "target", "with", "tick", "issuer"} on each obeying pixel and emits
    "order_issued". "with" is the ids of all the pixels given the order, because a big thing is lifted by several pixels
    together (a size-20 settlement by 4 pixels with 5 free slots each). The `pickup` behavior carries it out.
    """

    name = "pickup"

    def run(self, ctx, player_id, args):
        clean_args(args, "ids", "target")
        ids = as_ids(args["ids"])
        target_id = args["target"]

        if not is_int(target_id):
            raise Rejected("the target must be a pixel id")

        target = ctx.get_entity(target_id)

        for gate in PICKUP_GATES:
            reason = gate(ctx, player_id, target)

            if reason:
                raise Rejected(reason)

        actors = [entity_id for entity_id in ids if entity_id != target_id]
        ignored = {target_id: "cannot pick itself up"} if target_id in ids else {}
        pixels, rest = select_pixels(ctx, player_id, actors, self.name, self.strict) if actors else ([], {})
        ignored.update(rest)

        if not pixels:
            raise Rejected("no commandable pixels: " + ", ".join(sorted(set(ignored.values()))) if ignored else "no pixels can pick that up")

        group = [pixel.id for pixel in pixels]

        for pixel in pixels:
            issue_order(ctx, pixel, {"kind": "pickup", "target": target_id, "with": group, "tick": ctx.tick, "issuer": player_id})

        return Outcome(True, applied=group, ignored=ignored)