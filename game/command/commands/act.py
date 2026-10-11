"""One click, any command. The player selects pixels (ids, or a dragged box) and clicks a spot on the map; the server decides what
that click means for the chosen action and runs the matching command. Nothing here is new game logic: it only turns a click into the
arguments of `move`, `attack`, `spawn`, `drop` or `transfer`, so every rule, gate and order those commands have still applies.

args: {"ids": [...] or "box": [x0, y0, x1, y1], "point": [x, y], "action": name (optional), ...extras for that action}

    action     what the click at `point` becomes                                      extras
    (none)     attack if a hostile pixel is under the click, otherwise move there
    move       move to the point
    attack     attack the hostile pixel under the click (refused if there is none)
    spawn      create a pixel of `blueprint` at the point                             blueprint
    drop       put `item` ({"resource", "amount"}) on the ground at the point         item
    transfer   a pixel under the click is the other side:                             item, mode, from
                 no item        pick up the pixel under the click (settlement, passenger)
                 resource item  mode "give" (default): give it to that pixel; "take": take from it
                 entity item    put it on the pixel under the click, or set it down at the point if there is none
                                ("from": the carrier to take it off first)

"Under the click" means the nearest living pixel within PICK_RADIUS of the point, never one of the pixels being ordered. Hostile
means visible and not yours; for transfer the pixel must be yours. Add an action with @click_action("name", extras=(...)): a function
(ctx, player_id, ids, point, args) -> (command name, that command's args without ids). Unknown extras for an action are refused.
"""
from ..command import COMMANDS, Command, Rejected, as_ids, as_point, command, pick_entity

CLICK_ACTIONS = {}


def click_action(name, extras=()):
    def register(function):
        CLICK_ACTIONS[name] = (function, frozenset(extras))
        return function

    return register


def hostile_under(ctx, player_id, ids, x, y):
    return pick_entity(ctx, x, y, lambda pixel: pixel.visible and pixel.id not in ids and pixel.owner != player_id)


def own_under(ctx, player_id, ids, x, y):
    return pick_entity(ctx, x, y, lambda pixel: pixel.owner is not None and pixel.owner == player_id and pixel.id not in ids)


@click_action("move")
def click_move(ctx, player_id, ids, point, args):
    return "move", {"target": list(point)}


@click_action("attack")
def click_attack(ctx, player_id, ids, point, args):
    target = hostile_under(ctx, player_id, ids, *point)

    if target is None:
        raise Rejected("nothing to attack there")

    return "attack", {"target": target.id}


@click_action("spawn", extras=("blueprint",))
def click_spawn(ctx, player_id, ids, point, args):
    if "blueprint" not in args:
        raise Rejected("missing argument(s): ['blueprint']")

    return "spawn", {"blueprint": args["blueprint"], "target": list(point)}


@click_action("drop", extras=("item",))
def click_drop(ctx, player_id, ids, point, args):
    if "item" not in args:
        raise Rejected("missing argument(s): ['item']")

    return "drop", {"item": args["item"], "target": list(point)}


@click_action("transfer", extras=("item", "mode", "from"))
def click_transfer(ctx, player_id, ids, point, args):
    other = own_under(ctx, player_id, ids, *point)
    item = args.get("item")
    inner = {}

    if item is None:
        if other is None or "mode" in args or "from" in args:
            raise Rejected("click one of your pixels to pick it up")

        return "transfer", {"item": {"entity": other.id}}

    if isinstance(item, dict) and "resource" in item:
        mode = args.get("mode", "give")

        if mode not in ("give", "take") or "from" in args:
            raise Rejected("mode must be give or take (and from only applies to carrying things)")

        if other is None:
            raise Rejected("click one of your pixels to give to or take from (to put resources on the ground, use drop)")

        return "transfer", {"item": item, "to" if mode == "give" else "from": other.id}

    if "mode" in args:
        raise Rejected("mode only applies to resources")

    inner["item"] = item

    if "from" in args:
        inner["from"] = args["from"]

    inner["to"] = other.id if other is not None else list(point)
    return "transfer", inner


def default_click(ctx, player_id, ids, point, args):
    target = hostile_under(ctx, player_id, ids, *point)
    return ("attack", {"target": target.id}) if target is not None else ("move", {"target": list(point)})


@command
class Act(Command):
    __doc__ = __doc__
    name = "act"

    def selection_name(self, args):
        action = args.get("action") if isinstance(args, dict) else None
        return action if isinstance(action, str) else None

    def run(self, ctx, player_id, args):
        if not isinstance(args, dict):
            raise Rejected("the arguments must be a map")

        action = args.get("action")

        if action is not None and (not isinstance(action, str) or action not in CLICK_ACTIONS):
            raise Rejected("unknown action")

        resolver, extras = CLICK_ACTIONS[action] if action is not None else (default_click, frozenset())
        extra = sorted((key for key in args if key not in {"ids", "action", "point"} | extras), key=str)

        if extra:
            raise Rejected(f"unexpected argument(s): {extra}")

        if "ids" not in args or "point" not in args:
            raise Rejected("missing argument(s): ids (or box) and point")

        ids = as_ids(args["ids"])
        point = as_point(args["point"], ctx)
        name, inner = resolver(ctx, player_id, set(ids), point, args)
        inner["ids"] = ids
        return COMMANDS[name].run(ctx, player_id, inner)