import math
from dataclasses import dataclass
from typing import Any, Callable

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

def logistic(midpoint=0.5, steepness=10.0):
    return lambda value: 1.0 / (1.0 + math.exp(-steepness * (value - midpoint)))

@dataclass
class Consideration:
    read: Callable[[Any, Any, Any], float]
    curve: Callable[[float], float] = linear
    name: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name}


    def score(entity, action, context, considerations):
        if not considerations:
            return 0.0

        result = 1.0

        for consideration in considerations:
            value = max(0.0, min(1.0, consideration.read(entity, action, context)))
            result *= max(0.0, min(1.0, consideration.curve(value)))

            if result <= 0.0:
                return 0.0

        compensation = 1.0 - 1.0 / len(considerations)

        return result + (1.0 - result) * compensation * result