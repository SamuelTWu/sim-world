from ...entity.behavior.behaviors.drop import DROP_GATES, refusal
from ..command import Command, Outcome, Rejected, as_ids, as_point, clean_args, command, is_int, issue_order, select_pixels


@command
class Drop(Command):
    """Order pixels to put resources from their inventory on the ground. args: {"ids": [pixel ids], "item": {"resource": name, "amount": n} or {"all": true}, "target": [x, y] (optional)}.

    A command for pixels, like `move` and `transfer`: only pixels you own, that are alive, that carry the "command"
    permission for "drop" and have the `drop` behavior obey (the others are skipped). Only resources can be dropped; to put a
    pixel or structure down use `transfer` with "to": [x, y]. Each pixel drops up to `amount` of its OWN resource as a pile pixel
    (see entity/behavior/behaviors/drop.py); a pixel without it fails and loses nothing.

    A valid command only stores {"kind": "drop", "item", "x", "y", "tick", "issuer"} ("x"/"y" left out when no target was
    given, meaning "next to the pixel") and emits "order_issued"; the drop behavior carries it out. DROP_GATES (in the behavior)
    are the checks on what may be dropped.
    """

    name = "drop"

    def run(self, ctx, player_id, args):
        keys = ("ids", "item", "target") if "target" in args else ("ids", "item")
        clean_args(args, *keys)
        ids = as_ids(args["ids"])
        item = args["item"]

        if isinstance(item, dict) and set(item) == {"all"} and item["all"] is True:
            name, clean_item = None, {"all": True}
        else:
            if not isinstance(item, dict) or set(item) != {"resource", "amount"}:
                raise Rejected("the item must be {resource, amount} or {all: true} (to put a pixel down, use transfer)")

            name, amount = item["resource"], item["amount"]

            if not isinstance(name, str) or not name or len(name) > 64:
                raise Rejected("invalid resource")

            if not is_int(amount) or amount <= 0:
                raise Rejected("the amount must be a positive whole number")

            clean_item = {"resource": name, "amount": amount}

        point = as_point(args["target"], ctx) if "target" in args else None
        pixels, ignored = select_pixels(ctx, player_id, ids, self.name, self.strict)

        for pixel in list(pixels):
            reason = refusal(ctx, pixel, name) if name is not None else None

            if reason:
                pixels.remove(pixel)
                ignored[pixel.id] = reason

        if not pixels:
            raise Rejected("no pixels can drop that: " + ", ".join(sorted(set(ignored.values()))))

        order = {"kind": "drop", "item": clean_item, "tick": ctx.tick, "issuer": player_id}

        if point is not None:
            order["x"], order["y"] = point

        for pixel in pixels:
            issue_order(ctx, pixel, dict(order))

        return Outcome(True, applied=[pixel.id for pixel in pixels], ignored=ignored)