"""Who may know a pixel exists (README 7.5). The one place that decides it, used by the server's replication and by
anything that names pixels on someone's behalf (attack, click targets, a pixel picking a target), so what a player is
not shown, they also cannot discover or act on by guessing ids. Imports nothing, so everything can use it.

A pixel is HIDDEN from a viewer when it is not one of the viewer's own (or an ally's) and either
  - it is invisible (`entity.visible` is False, from the blueprint's "visible": false), or
  - it is a spy (it carries the tag "spy").
Everyone who is not an ally is an enemy for this purpose, neutral pixels included. The owner always sees their own
pixels. A dead pixel is seen by nobody (the client is told it left).

Two hooks for later, both empty or trivial now:
  is_ally(viewer, owner): diplomacy / teams. For now only the same player is an ally of itself.
  REVEALS: functions (viewer, entity) -> True that show a hidden pixel anyway (a detector, a scout nearby, a reveal
           spell...). Append to it; any True reveals.
"""
SPY_TAG = "spy"

REVEALS = []


def is_ally(viewer, owner):
    return viewer is not None and viewer == owner


def is_hidden(viewer, entity):
    """True if `viewer` (a player id, or None for a neutral pixel's own sight) must not be told about `entity`."""
    if is_ally(viewer, entity.owner):
        return False

    if entity.visible and SPY_TAG not in entity.tags:
        return False

    return not any(reveal(viewer, entity) for reveal in REVEALS)


def can_see(viewer, entity):
    """True if `viewer` may be told about this living pixel."""
    return entity is not None and entity.alive and not is_hidden(viewer, entity)