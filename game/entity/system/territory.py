from typing import Any

class Territory:
    MAX_STRENGTH = 5.0

    def __init__(self, decay=0.01, threshold=0.05):
        self.claims = {}
        self.decay = decay
        self.threshold = threshold

    def owner_at(self, x, y):
        claim = self.claims.get((x, y))

        return claim[0] if claim else None

    def strength_at(self, x, y):
        claim = self.claims.get((x, y))

        return claim[1] if claim else 0.0

    def claim(self, x, y, owner, amount=1.0):
        current = self.claims.get((x, y))

        if current is None or current[0] == owner:
            self.claims[(x, y)] = (owner, min(self.MAX_STRENGTH, (current[1] if current else 0.0) + amount))
            return True

        remaining = current[1] - amount

        if remaining <= 0.0:
            self.claims[(x, y)] = (owner, max(-remaining, 0.1))
            return True

        self.claims[(x, y)] = (current[0], remaining)

        return False

    def owned_by(self, owner):
        return [position for position, (claimant, _) in self.claims.items() if claimant == owner]

    def update(self, delta_time):
        loss = self.decay * delta_time
        self.claims = {position: (owner, strength - loss) for position, (owner, strength) in self.claims.items() if strength - loss > self.threshold}

    def to_dict(self) -> dict[str, Any]:
        return {
            "decay": self.decay,
            "threshold": self.threshold,
            "claims": [
                {"x": position[0], "y": position[1], "owner": owner, "strength": strength}
                for position, (owner, strength) in self.claims.items()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Territory":
        territory = cls(decay=float(data.get("decay", 0.01)), threshold=float(data.get("threshold", 0.05)))

        for claim in data.get("claims", []):
            territory.claims[(int(claim["x"]), int(claim["y"]))] = (int(claim["owner"]), float(claim["strength"]))

        return territory