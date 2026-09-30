class BlendedSelection:
    def __init__(self, seed=0):
        self.seed = seed

    def choose(self, candidates, context, x, y):
        ranked = sorted(candidates, key=lambda c: (c[1], c[0].priority), reverse=True)
        top, top_influence = ranked[0]

        if len(ranked) == 1:
            return top

        other, other_influence = ranked[1]
        width = min(top.border_width(other), other.border_width(top))
        margin = top_influence - other_influence

        if width <= 0 or margin >= width:
            return top

        chance = 0.5 + 0.5 * margin / width
        return top if self._noise(x, y) < chance else other

    def _noise(self, x, y):
        h = (x * 374761393 + y * 668265263 + self.seed * 2147483647) & 0xFFFFFFFF
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
        return ((h ^ (h >> 16)) & 0xFFFF) / 65536