from dataclasses import dataclass


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


class StimulusField:
    def __init__(self):
        self.stimuli = []

    def emit(self, stimulus):
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

        self.stimuli = [s for s in self.stimuli if s.age < s.lifetime]