import json
import sys
from dataclasses import asdict
from pathlib import Path

from src.simworld.world.generator import GenerationSettings, WorldGenerator

BASELINE = Path(__file__).with_name("world_mode_baseline.json")
CASES = [(100, 100, 12345), (64, 64, 7), (150, 90, 99)]
failures = 0


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


def checksum(settings):
    world = WorldGenerator(settings).generate()
    world.finish_generation()
    return world.generation_checksum


def plain(width, height, seed):
    return GenerationSettings(width=width, height=height, seed=seed)


if "--record" in sys.argv:
    BASELINE.write_text(json.dumps({f"{w}x{h}:{s}": checksum(plain(w, h, s)) for w, h, s in CASES}, indent=2))
    print(f"recorded {len(CASES)} checksums in {BASELINE.name}: run this BEFORE the mode change, then run the check without --record")
    sys.exit(0)

check("default mode is normal", GenerationSettings().mode == "normal")
check("mode is in the settings sent to clients", asdict(GenerationSettings()).get("mode") == "normal")
check("sandbox is accepted", GenerationSettings(mode="sandbox").mode == "sandbox")

for bad in ("bogus", "", "Normal", "SANDBOX", None, 5, ["sandbox"]):
    try:
        GenerationSettings(mode=bad)
        check(f"mode {bad!r} refused", False, "no error")
    except ValueError as problem:
        check(f"mode {bad!r} refused", "mode" in str(problem), str(problem))

settings = GenerationSettings(width=64, height=64, seed=1)
settings.mode = "bogus"

try:
    WorldGenerator(settings).generate()
    check("a mode changed after creation is refused by generate()", False, "no error")
except ValueError as problem:
    check("a mode changed after creation is refused by generate()", "mode" in str(problem), str(problem))

welcome = {**asdict(plain(100, 100, 12345))}
welcome.pop("mode")
check("a welcome message without a mode still builds a normal world", GenerationSettings(**welcome).mode == "normal")
check("settings survive the welcome round trip", GenerationSettings(**asdict(GenerationSettings(width=70, height=80, seed=3, mode="sandbox"))) == GenerationSettings(width=70, height=80, seed=3, mode="sandbox"))

for width, height, seed in CASES:
    explicit = GenerationSettings(width=width, height=height, seed=seed, mode="normal")
    check(f"explicit normal equals default {width}x{height} seed {seed}", checksum(explicit) == checksum(plain(width, height, seed)))

if BASELINE.exists():
    baseline = json.loads(BASELINE.read_text())

    for width, height, seed in CASES:
        key = f"{width}x{height}:{seed}"
        check(f"normal world {key} is unchanged since the baseline", checksum(plain(width, height, seed)) == baseline.get(key), "the world generates differently now")
else:
    check("baseline file exists (run with --record before the change)", False)

sandbox = WorldGenerator(GenerationSettings(width=100, height=100, seed=1, mode="sandbox")).generate()
check("sandbox mode generates a world", sandbox.width >= 64 and sandbox.height >= 64)
check("sandbox mode is deterministic", checksum(GenerationSettings(seed=1, mode="sandbox")) == checksum(GenerationSettings(seed=1, mode="sandbox")))

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)