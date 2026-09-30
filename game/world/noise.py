import math
import random

_GRADIENTS = ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (0.70710678118, 0.70710678118), (-0.70710678118, 0.70710678118), (0.70710678118, -0.70710678118), (-0.70710678118, -0.70710678118))
_PERMUTATION_CACHE = {}


def _get_permutation(seed):
    if seed not in _PERMUTATION_CACHE:
        values = list(range(256))
        random.Random(seed).shuffle(values)
        _PERMUTATION_CACHE[seed] = tuple(values + values)
    return _PERMUTATION_CACHE[seed]


def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _lerp(a, b, t):
    return a + t * (b - a)


def _gradient(permutation, ix, iy, x, y):
    gx, gy = _GRADIENTS[permutation[permutation[ix & 255] + (iy & 255)] & 7]
    return gx * (x - ix) + gy * (y - iy)


def _perlin2(x, y, permutation):
    x0, y0 = math.floor(x), math.floor(y)
    x1, y1 = x0 + 1, y0 + 1
    sx, sy = _fade(x - x0), _fade(y - y0)
    n00 = _gradient(permutation, x0, y0, x, y)
    n10 = _gradient(permutation, x1, y0, x, y)
    n01 = _gradient(permutation, x0, y1, x, y)
    n11 = _gradient(permutation, x1, y1, x, y)
    return _lerp(_lerp(n00, n10, sx), _lerp(n01, n11, sx), sy)


def pnoise2(x, y, *, octaves=1, persistence=0.5, lacunarity=2.0, repeatx=None, repeaty=None, base=0):
    if octaves <= 0:
        return 0.0
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("x and y must be finite")
    if not math.isfinite(persistence):
        raise ValueError("persistence must be finite")
    if not math.isfinite(lacunarity) or lacunarity <= 0:
        raise ValueError("lacunarity must be positive and finite")

    total, amplitude, frequency, amplitude_sum = 0.0, 1.0, 1.0, 0.0
    seed = int(base)

    for octave in range(octaves):
        sx, sy = x * frequency, y * frequency
        if repeatx is not None and repeatx > 0:
            sx %= repeatx
        if repeaty is not None and repeaty > 0:
            sy %= repeaty
        total += _perlin2(sx, sy, _get_permutation(seed + octave * 1013)) * amplitude
        amplitude_sum += amplitude
        amplitude *= persistence
        frequency *= lacunarity

    return total / amplitude_sum if amplitude_sum else 0.0