from game.command.attack_method import load_attack_methods, method_name, resolve
from ..command import Command, Outcome, Rejected, as_ids, clean_args, command, is_int, issue_order, select_pixels

ATTACK_GATES = []


def gate_not_own(ctx, player_id, target):
    return "you cannot attack your own pixels" if target.owner is not None and target.owner == player_id else None


def gate_targetable(ctx, player_id, target):
    """Dead and invisible pixels look the same as ones that do not exist, so ids cannot be probed."""
    return None if target.alive and target.visible else "invalid target"


ATTACK_GATES.extend([gate_targetable, gate_not_own])


@command
class Attack(Command):
    """Order pixels to attack another pixel. args: {"ids": [pixel ids], "target": a pixel id}.

    A command for pixels, like `move` and `spawn`: only pixels you own, that are alive and that carry the "command"
    trait for "attack" obey (the others are skipped; the command is refused if none can). A pixel never attacks
    itself. Like `move`, a valid command only stores an order on each obeying pixel:
    {"kind": "attack", "target": pixel id, "tick", "issuer"} and emits "order_issued".

    The order does not say HOW to attack. Each pixel attacks in its own way (collision by default, or whatever its
    "attack" trait names: see attack_method.py), looked up when the order is carried out. A pixel whose attack
    trait names a method that does not exist is skipped. Nothing carries orders out yet: that behavior should call
    attack_method.attack_step(ctx, pixel, target) every tick, which applies the pixel's own attack when it is in reach,
    and says when to move closer or when the target is gone.

    ATTACK_GATES are checks on the target: functions (ctx, player_id, target) that return a reason to refuse, or None.
    They run once per command. Add range and "can this player see the target" rules there (Phase 7.5): right now
    any pixel that is alive and visible can be named, whoever owns it and wherever it is.
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