import hashlib
import sys

from game.world.noise import pnoise2

EXPECTED = "ed45e0cbc496863e"

h = hashlib.sha256()
for y in range(64):
    for x in range(64):
        value = pnoise2(x * 0.05 + 123.4, y * 0.05 - 56.7, octaves=2, persistence=0.5, lacunarity=2.0, repeatx=100000, repeaty=100000, base=12345)
        h.update(value.hex().encode())

actual = h.hexdigest()[:16]
print(sys.version.split()[0], actual, "OK" if actual == EXPECTED else f"MISMATCH (expected {EXPECTED})")