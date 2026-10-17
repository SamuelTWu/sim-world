import math
from dataclasses import dataclass
from typing import Any, Callable

MAX_STEEPNESS = 100.0


def linear(value):
    return value


def quadratic(value):
    return value * value


def inverse(value):
    return 1.0 - value


def ramp(low, high):
    return lambda value: low + (high - low) * value


def step(threshold):
    return lambda value: 1.0 if value >= threshold else 0.0


def sigmoid(value, midpoint, steepness):
    return 1.0 / (1.0 + math.exp(max(-60.0, min(60.0, -steepness * (value - midpoint)))))


def logistic(midpoint=0.5, steepness=10.0):
    steepness = max(0.0, min(MAX_STEEPNESS, steepness))

    if steepness == 0.0:
        return linear

    low, high = sigmoid(0.0, midpoint, steepness), sigmoid(1.0, midpoint, steepness)
    return lambda value: (sigmoid(value, midpoint, steepness) - low) / (high - low)


CURVES = {"linear": lambda: linear, "quadratic": lambda: quadratic, "inverse": lambda: inverse, "ramp": ramp, "step": step, "logistic": logistic}


def curve_from(name, args=None):
    factory = CURVES.get(name)

    if factory is None:
        raise ValueError(f"unknown curve {name!r}; valid: {sorted(CURVES)}")

    try:
        return factory(**(args or {}))
    except TypeError as problem:
        raise ValueError(f"bad arguments for curve {name!r}: {problem}") from None


@dataclass
class Consideration:
    read: Callable[[Any, Any, Any], float]
    curve: Callable[[float], float] = linear
    name: str = ""