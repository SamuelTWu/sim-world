from ..attack_method import ATTACKED, AttackMethod, attack_method
from ...entity.system.simContext import TILE_UNITS


@attack_method
class Collision(AttackMethod):
    """Melee: the attacker touches the target and hurts it. The default for every pixel.

    Params (set in the pixel's "attack" trait to override):
      damage          health taken from the target per hit (default 1.0)
      reach           how close counts as touching, in world units (default half a tile)
      cooldown_ticks  ticks to wait between hits (default 10)

    Health is lowered here but death is not decided here: whatever already handles health reaching 0 does that.
    """

    name = "collision"
    defaults = {"damage": 1.0, "reach": TILE_UNITS * 0.5, "cooldown_ticks": 10}

    def attack(self, ctx, attacker, target, params):
        amount = float(params["damage"])
        target.health = max(0.0, target.health - amount)
        events = ctx.events

        if events is not None:
            events.emit(ATTACKED, attacker=attacker, target=target, amount=amount, method=self.name)