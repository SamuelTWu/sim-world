from dataclasses import dataclass
from typing import Any

@dataclass
class Stimulus:
    x: float
    y: float
    channel: str
    strength: float = 1.0
    radius: float = 160.0
    lifetime: float = 3.0
    owner: int | None = None
    age: float = 0.0

    def intensity_at(self, x, y):
        distance = ((x - self.x) ** 2 + (y - self.y) ** 2) ** 0.5

        if distance >= self.radius or self.age >= self.lifetime:
            return 0.0

        return self.strength * (1.0 - distance / self.radius) * (1.0 - self.age / self.lifetime)

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "channel": self.channel, "strength": self.strength, "radius": self.radius, "lifetime": self.lifetime, "owner": self.owner, "age": self.age}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Stimulus":
        return cls(x=float(data["x"]), y=float(data["y"]), channel=str(data["channel"]), strength=float(data.get("strength", 1.0)), radius=float(data.get("radius", 160.0)), lifetime=float(data.get("lifetime", 3.0)), owner=data.get("owner"), age=float(data.get("age", 0.0)))


class StimulusField:
    def __init__(self):
        self.stimuli = []

    def emit(self, stimulus: Stimulus):
        self.stimuli.append(stimulus)

    def strongest(self, x, y, channels):
        best, best_value = None, 0.0

        for stimulus in self.stimuli:
            if stimulus.channel in channels:
                value = stimulus.intensity_at(x, y)

                if value > best_value:
                    best, best_value = stimulus, value

        return best, best_value

    def update(self, delta_time):
        for stimulus in self.stimuli:
            stimulus.age += delta_time

        self.stimuli = [stimulus for stimulus in self.stimuli if stimulus.age < stimulus.lifetime]

    def to_dict(self) -> list[dict[str, Any]]:
        return [stimulus.to_dict() for stimulus in self.stimuli]

    @classmethod
    def from_dict(cls, data: list[dict[str, Any]]) -> "StimulusField":
        field = cls()
        field.stimuli = [Stimulus.from_dict(stimulus) for stimulus in data]
        return field