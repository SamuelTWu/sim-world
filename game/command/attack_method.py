"""How a pixel actually hurts another pixel. The `attack` command only says WHO to attack; this says HOW.

Different pixels attack differently: most just run into their target (collision, the default), some explode, some
shoot projectile entities. Each way is an attack method: one file in game/command/attack_methods/ that subclasses
AttackMethod, sets `name`, and is decorated with @attack_method. load_attack_methods() imports that whole folder, so
a new method is just a new file.

A pixel picks its method with an "attack" trait (in its blueprint, or set at runtime):

    "traits": {"attack": {"method": "collision", "damage": 2.0}}

Everything in the trait except "method" overrides that method's `defaults`. A pixel with no attack trait uses
DEFAULT_METHOD (collision) with its defaults. Being ORDERED to attack is a different thing (the "command" trait,
see command.py): that decides whether the player may give the order, this decides what the pixel does with it.

An attack order ({"kind": "attack", "target": id}) does not name a method on purpose: the method is looked up when
the order is carried out, so a pixel that gains or changes its attack later just works.

Whatever carries orders out (a behavior, which does not exist yet) should call `attack_step()` once per tick for a
pixel with an attack order. It returns what happened so the behavior knows what to do next:
    "gone"      the target is dead, invisible or missing: drop the order
    "approach"  not in reach yet: move toward the target (or stand still, for a ranged pixel that wants line of sight)
    "waiting"   in reach, but the pixel is still recovering from its last attack
    "hit"       the attack happened
"""
import importlib
import math

from ..entity.system.simContext import TILE_UNITS

DEFAULT_METHOD = "collision"
TRAIT = "attack"
READY_KEY = "attack_ready_tick"
ATTACKED = "attacked"

ATTACK_METHODS = {}
loaded = False


class AttackMethod:
    """One way of attacking. Override can_attack() and attack(); the rest has sensible defaults.

    Examples of what other methods would do:
      explode     reach = blast radius; attack() hurts everything inside it, then kills the attacker
      projectile  reach = range; attack() creates a projectile pixel with ctx.spawn(...) that flies at the target
    """

    name = ""
    defaults = {"cooldown_ticks": 10}

    def reach(self, ctx, attacker, params):
        """How close the attacker has to be (world units). Used by whatever moves it into position."""
        return float(params.get("reach", TILE_UNITS * 0.5))

    def can_attack(self, ctx, attacker, target, params):
        """True if the attack can happen right now (in reach; ranged methods can also check line of sight)."""
        return distance(attacker, target) <= self.reach(ctx, attacker, params)

    def attack(self, ctx, attacker, target, params):
        """Carry out the attack. Called only when can_attack() is true and the cooldown is over."""
        raise NotImplementedError


def attack_method(cls):
    ATTACK_METHODS[cls.name] = cls()
    return cls


def load_attack_methods():
    """Import every module in game/command/attack_methods/ so the methods in them register. Safe to call repeatedly."""
    global loaded

    if not loaded:
        importlib.import_module(".attack_methods", __package__)
        loaded = True


def distance(first, second):
    return math.hypot(first.position.x - second.position.x, first.position.y - second.position.y)


def method_name(pixel):
    trait = pixel.traits.get(TRAIT)
    name = trait.get("method", DEFAULT_METHOD) if isinstance(trait, dict) else DEFAULT_METHOD
    return name if isinstance(name, str) else DEFAULT_METHOD


def resolve(pixel):
    """(method, params) for a pixel, or None if its attack trait names a method that does not exist."""
    load_attack_methods()
    method = ATTACK_METHODS.get(method_name(pixel))

    if method is None:
        return None

    trait = pixel.traits.get(TRAIT)
    params = dict(method.defaults)

    if isinstance(trait, dict):
        params.update({key: value for key, value in trait.items() if key != "method"})

    return method, params


def attack_step(ctx, attacker, target):
    """One tick of an attack order. Returns "gone", "approach", "waiting" or "hit" (see the top of this file)."""
    resolved = resolve(attacker)

    if target is None or not target.alive or not target.visible or resolved is None:
        return "gone"

    method, params = resolved

    if not method.can_attack(ctx, attacker, target, params):
        return "approach"

    if ctx.tick < attacker.components.get(READY_KEY, 0):
        return "waiting"

    method.attack(ctx, attacker, target, params)
    attacker.components[READY_KEY] = ctx.tick + int(params.get("cooldown_ticks", 0))
    return "hit"