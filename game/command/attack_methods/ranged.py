from ...entity.system import transientEvents
from ..attack_method import ATTACKED, AttackMethod, attack_method
from ...entity.system.simContext import TILE_UNITS


@attack_method
class Ranged(AttackMethod):
    """Shoots from a distance. The hit is decided at once; the shot you SEE is a transient event (entity/system/transientEvents.py), not a pixel.

    Params (set in the pixel's "attack" trait: {"method": "ranged", ...}):
      damage          health taken from the target per shot (default 1.0)
      reach           range in world units (default 5 tiles)
      cooldown_ticks  ticks between shots (default 20)
      shot            the transient event type clients draw ("arrow", "bolt", ...; default "arrow")
    """

    name = "ranged"
    defaults = {"damage": 1.0, "reach": TILE_UNITS * 5, "cooldown_ticks": 20, "shot": "arrow"}

    def attack(self, ctx, attacker, target, params):
        amount = float(params["damage"])
        target.health = max(0.0, target.health - amount)
        transientEvents.fired(ctx, attacker, target, str(params.get("shot") or "arrow"))

        if ctx.events is not None:
            ctx.events.emit(ATTACKED, attacker=attacker, target=target, amount=amount, method=self.name)