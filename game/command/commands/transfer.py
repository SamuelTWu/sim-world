from ..command import Command, Outcome, Rejected, as_ids, as_point, clean_args, command, is_int, issue_order, select_pixels

TRANSFER_GATES = []


def gate_owned(ctx, player_id, things):
    """Everything named must exist, be alive and be yours. One message for all of it, so ids cannot be probed."""
    for entity in things:
        if entity is None or not entity.alive or entity.owner != player_id:
            return "invalid transfer"

    return None


TRANSFER_GATES.append(gate_owned)


def entity_arg(ctx, value, what):
    if not is_int(value):
        raise Rejected(f"{what} must be a pixel id")

    return ctx.get_entity(value)


@command
class Transfer(Command):
    """Order pixels to move something that already exists. args:
        {"ids": [pixel ids], "item": {"resource": name, "amount": n} or {"entity": id}, "from": id (optional), "to": id or [x, y] (optional)}

    A command for pixels, like `move`, `attack` and `spawn`: only pixels you own, that are alive and that carry the
    "command" trait for "transfer" obey. Nothing is created or destroyed (that is `spawn` and `drop`): the thing
    only changes where it is held. See transfer_step.py for what each form does.

    Resources: exactly one of "from" / "to" is given (a pixel id); the other side is the acting pixel itself.
    A point is not allowed here, that would be `drop`. Entities: the acting pixels pick it up together (neither given),
    put it on a carrier ("to": id), hand it over ("from": carrier), or set it down ("to": [x, y]).

    Everything named (item entity, from, to) must be alive and owned by the player, otherwise the one message
    "invalid transfer" is returned. TRANSFER_GATES are the place to loosen that later (trading, allies):
    functions (ctx, player_id, things) returning a reason to refuse, or None.

    A valid command only stores {"kind": "transfer", "item", "from", "to", "tick", "issuer"} on each obeying pixel and
    emits "order_issued". Nothing carries it out yet: that behavior should call transfer_step(ctx, actors, order).
    """

    name = "transfer"

    def run(self, ctx, player_id, args):
        if not isinstance(args, dict):
            raise Rejected("the arguments must be a map")

        extra = sorted((key for key in args if key not in ("ids", "item", "from", "to")), key=str)

        if extra:
            raise Rejected(f"unexpected argument(s): {extra}")

        if "ids" not in args or "item" not in args:
            raise Rejected("missing argument(s): ids and item are required")

        ids = as_ids(args["ids"])
        item, from_id, to = args["item"], args.get("from"), args.get("to")
        item_entity, clean_item = self.read_item(ctx, item, from_id, to)
        named = [item_entity] if item_entity is not None else []

        if from_id is not None:
            named.append(entity_arg(ctx, from_id, "from"))

        if isinstance(to, (list, tuple)):
            to = list(as_point(to, ctx))
        elif to is not None:
            named.append(entity_arg(ctx, to, "to"))

        for gate in TRANSFER_GATES:
            reason = gate(ctx, player_id, named)

            if reason:
                raise Rejected(reason)

        if from_id is not None and from_id == to:
            raise Rejected("invalid transfer")

        involved = {entity.id for entity in named}
        ignored = {entity_id: "cannot transfer with itself" for entity_id in ids if entity_id in involved}
        actors = [entity_id for entity_id in ids if entity_id not in involved]
        pixels, rest = select_pixels(ctx, player_id, actors, self.name, self.strict) if actors else ([], {})
        ignored.update(rest)

        if not pixels:
            raise Rejected("no commandable pixels: " + ", ".join(sorted(set(ignored.values()))) if ignored else "no pixels can transfer")

        for pixel in pixels:
            issue_order(ctx, pixel, {"kind": "transfer", "item": clean_item, "from": from_id, "to": to, "tick": ctx.tick, "issuer": player_id})

        return Outcome(True, applied=[pixel.id for pixel in pixels], ignored=ignored)

    @staticmethod
    def read_item(ctx, item, from_id, to):
        """Returns (the entity being moved or None, the item as stored in the order)."""
        if not isinstance(item, dict):
            raise Rejected("the item must be a resource or an entity")

        if "resource" in item:
            if set(item) != {"resource", "amount"}:
                raise Rejected("the item must be {resource, amount} or {entity}")

            name, amount = item["resource"], item["amount"]

            if not isinstance(name, str) or not name or len(name) > 64:
                raise Rejected("invalid resource")

            if not is_int(amount) or amount <= 0:
                raise Rejected("the amount must be a positive whole number")

            if isinstance(to, (list, tuple)):
                raise Rejected("a resource cannot be set down at a point")

            if (from_id is None) == (to is None):
                raise Rejected("give exactly one of from and to")

            return None, {"resource": name, "amount": amount}

        if set(item) != {"entity"}:
            raise Rejected("the item must be {resource, amount} or {entity}")

        return entity_arg(ctx, item["entity"], "the item"), {"entity": item["entity"]}