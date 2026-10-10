"""Player orders, pinned over the decision system.

An order is a plain dict on a pixel: pixel.components["order"] = {"kind": "attack", "target": 7, "tick": 120, "issuer": 1}.
`kind` names a behavior's action, and everything except the bookkeeping keys is that action's data. So an order is
exactly the Action the decision system could have picked ("attack", {"target": 7}), only guaranteed: it is started
with an infinite score, so no scored action can interrupt it. When its task ends (done or failed) the order is removed
and the pixel goes back to deciding for itself. A newer order replaces the running one.

SystemRunner calls follow_orders() at the top of think() and order_finished() when a task ends.
"""
from .decisionSystem import Action, Decision

ORDER_KEY = "order"
ORDER_SCORE = float("inf")
BOOKKEEPING = ("kind", "tick", "issuer", "started")
ORDER_FINISHED = "order_finished"
ORDER_DROPPED = "order_dropped"


def action_of(order):
    return Action(order["kind"], {key: value for key, value in order.items() if key not in BOOKKEEPING})


def follow_orders(runner, entity):
    """True if an order is in charge of this pixel (so it should not think for itself right now)."""
    order = entity.components.get(ORDER_KEY)

    if order is None:
        return False

    if order.get("started") and entity.task is not None and entity.task_score == ORDER_SCORE:
        return True

    if not isinstance(order.get("kind"), str) or order["kind"] not in runner.task_factories:
        drop(runner, entity, order, "no such action")
        return False

    before = entity.task
    runner.start_task(entity, Decision(action_of(order), ORDER_SCORE))

    if entity.task is before:
        drop(runner, entity, order, "could not start")
        return False

    order["started"] = True
    return True


def drop(runner, entity, order, reason):
    entity.components.pop(ORDER_KEY, None)
    runner.events.emit(ORDER_DROPPED, entity=entity, order=order, reason=reason)


def order_finished(runner, entity, task, status):
    """Call when a task ends, before the pixel's task score is reset. Removes the order that task was carrying out."""
    order = entity.components.get(ORDER_KEY)

    if order is not None and order.get("started") and entity.task_score == ORDER_SCORE:
        entity.components.pop(ORDER_KEY, None)
        runner.events.emit(ORDER_FINISHED, entity=entity, order=order, status=status)