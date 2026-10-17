import re
from functools import lru_cache

NAME = re.compile(r"^[a-z_]+(:[A-Za-z0-9_\-]{1,32})?$")

STATS = {
    "health": lambda entity: entity.health / max(entity.max_health, 1e-9),
    "energy": lambda entity: entity.energy / max(entity.max_energy, 1e-9),
    "age": lambda entity: entity.age,
    "carried": lambda entity: entity.carried(),
}

FAMILIES = {
    "need": lambda entity, key: entity.needs[key].get_urgency() if key in entity.needs else 0.0,
    "need_value": lambda entity, key: entity.needs[key].value if key in entity.needs else 0.0,
    "inventory": lambda entity, key: entity.inventory.get(key, 0.0),
    "prop": lambda entity, key: entity.prop(key),
    "tag": lambda entity, key: 1.0 if key in entity.tags else 0.0,
}

DESCRIPTIONS = {
    "health": "Health as a fraction of its maximum (0 to 1)",
    "energy": "Energy as a fraction of its maximum (0 to 1)",
    "age": "Seconds since it was created",
    "carried": "Total amount of resources it holds",
    "need:<name>": "How urgent a need is (0 to 1, after its curve)",
    "need_value:<name>": "The raw value of a need",
    "inventory:<resource>": "How much of a resource it holds",
    "prop:<name>": "A property such as max_speed or temperature",
    "tag:<name>": "1 if it has the tag, otherwise 0",
}


def resolve(name):
    return compile_name(name) if isinstance(name, str) else None


@lru_cache(maxsize=256)
def compile_name(name):
    if not NAME.match(name):
        return None

    known = STATS.get(name)

    if known is not None:
        return known

    family, _, key = name.partition(":")
    reader = FAMILIES.get(family)
    return (lambda entity: reader(entity, key)) if reader is not None and key else None


def valid(name):
    return resolve(name) is not None


def read(entity, name, default=0.0):
    function = resolve(name)
    return function(entity) if function is not None else default


def names():
    return list(DESCRIPTIONS)


def reader(name, low=0.0, high=1.0):
    function = resolve(name)

    if function is None:
        raise ValueError(f"unknown stat {name!r}; valid: {names()}")

    span = high - low

    if span <= 0:
        raise ValueError("high must be greater than low")

    return lambda entity, action=None, context=None: max(0.0, min(1.0, (function(entity) - low) / span))