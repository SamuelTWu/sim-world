from ..attack_method import load_attack_methods, method_name, resolve
from ..visibility import can_see
from ..command import Command, Outcome, Rejected, as_ids, clean_args, command, is_int, issue_order, select_pixels

ATTACK_GATES = []


def gate_not_own(ctx, player_id, target):
    return "you cannot attack your own pixels" if target.owner is not None and target.owner == player_id else None


def gate_targetable(ctx, player_id, target):
    """Dead pixels, and pixels hidden from this player (invisible, or spies: visibility.py), look the same as ones that do not exist, so ids cannot be probed."""
    return None if can_see(player_id, target) else "invalid target"


ATTACK_GATES.extend([gate_targetable, gate_not_own])


@command
class Attack(Command):
    """Order pixels to attack another pixel. args: {"ids": [pixel ids], "target": a pixel id}.

    A command for pixels, like `move` and `spawn`: only pixels you own, that are alive, that carry the "command"
    permission for "attack" and have the `attack` behavior obey (the others are skipped; the command is refused if none can). A pixel never attacks
    itself. Like `move`, a valid command only stores an order on each obeying pixel:
    {"kind": "attack", "target": pixel id, "tick", "issuer"} and emits "order_issued".

    The order does not say HOW to attack. The pixel's `attack` behavior does it in the pixel's own way (collision by
    default, or the method its attack trait names: see attack_method.py), chasing the target until it is gone. A pixel
    whose attack method does not exist is skipped.

    ATTACK_GATES are checks on the target: functions (ctx, player_id, target) that return a reason to refuse, or None.
    They run once per command. "Can this player see the target" is enforced there (visibility.py: invisible pixels and
    spies are hidden from enemies); range is not checked yet, so any pixel the player may see can be named, wherever it is.
    """

    name = "attack"

    def run(self, ctx, player_id, args):
        clean_args(args, "ids", "target")
        ids = as_ids(args["ids"])
        target_id = args["target"]

        if not is_int(target_id):
            raise Rejected("the target must be a pixel id")

        target = ctx.get_entity(target_id)

        if target is None:
            raise Rejected("invalid target")

        for gate in ATTACK_GATES:
            reason = gate(ctx, player_id, target)

            if reason:
                raise Rejected(reason)

        load_attack_methods()
        attackers = [entity_id for entity_id in ids if entity_id != target_id]
        pixels, ignored = select_pixels(ctx, player_id, attackers, self.name, self.strict) if attackers else ([], {})

        for pixel in list(pixels):
            if resolve(pixel) is None:
                pixels.remove(pixel)
                ignored[pixel.id] = f"unknown attack method '{method_name(pixel)}'"

        if target_id in ids:
            ignored[target_id] = "cannot attack itself"

        if not pixels:
            raise Rejected("no pixels can attack" if not ignored else "no commandable pixels: " + ", ".join(sorted(set(ignored.values()))))

        for pixel in pixels:
            issue_order(ctx, pixel, {"kind": "attack", "target": target_id, "tick": ctx.tick, "issuer": player_id})

        return Outcome(True, applied=[pixel.id for pixel in pixels], ignored=ignored)