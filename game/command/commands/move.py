from ..command import Command, Outcome, as_ids, as_point, clean_args, command, issue_order, select_pixels


@command
class Move(Command):
    """Order pixels to go to a point. args: {"ids": [pixel ids], "target": [x, y] in world units}.

    Pixels that are unknown, not yours, dead, or not able to obey are skipped (so a stale id in a group does not
    ruin the order). Set `strict = True` to refuse the whole command instead. The order is stored as
    {"kind": "move", "x", "y", "tick", "issuer"}.
    """

    name = "move"

    def run(self, ctx, player_id, args):
        clean_args(args, "ids", "target")
        ids = as_ids(args["ids"])
        x, y = as_point(args["target"], ctx)
        pixels, ignored = select_pixels(ctx, player_id, ids, self.name, self.strict)

        for pixel in pixels:
            issue_order(ctx, pixel, {"kind": "move", "x": x, "y": y, "tick": ctx.tick, "issuer": player_id})

        return Outcome(True, applied=[pixel.id for pixel in pixels], ignored=ignored)