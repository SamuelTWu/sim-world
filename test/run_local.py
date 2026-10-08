"""Runs a server and two clients on this machine and checks that all of them see identical terrain.

    python run_local.py
    python run_local.py --size 500 --seed 7
    python run_local.py --test-mismatch
"""

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PIXELS_PER_TILE = 4


def write_png(path, width, height, rows):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def write_terrain(path, world):
    scale = PIXELS_PER_TILE
    rows = []

    for y in range(world.height):
        row = b"".join(bytes(tile.color) * scale for tile in world.tiles[y])
        rows.extend([row] * scale)

    write_png(path, world.width * scale, world.height * scale, rows)


def tampered_builder(welcome):
    from game.tile.tile_types import TILE_TYPES
    from server.worldsync import generate_world

    generator, world = generate_world(welcome)
    first = world.tiles[0][0]
    world.tiles[0][0] = next(tile for tile in TILE_TYPES.values() if tile.name != first.name)
    world.generation_checksum = world.checksum()
    return generator, world


def join(url, name, builder):
    from server.client import Client

    deadline = time.monotonic() + 120

    while True:
        client = Client(url, name, timeout=10, world_builder=builder)
        client.start()
        client.wait()

        if not (client.error or "").startswith("could not connect") or time.monotonic() > deadline:
            return client

        time.sleep(0.25)


def run_client(args):
    from server.client import READY

    client = join(args.url, args.client, tampered_builder if args.tamper else None)
    ready = client.state == READY
    result = {"name": args.client, "state": client.state, "error": client.error, "player_id": client.player_id, "hashseed": os.environ.get("PYTHONHASHSEED")}

    if ready:
        world = client.world
        png = f"terrain_{args.client}.png"
        write_terrain(ROOT / png, world)
        result.update(checksum=world.generation_checksum, width=world.width, height=world.height, seed=client.welcome["seed"], png=png)

    print("RESULT " + json.dumps(result), flush=True)
    client.close()
    return 0 if ready else 1

def child_env(hashseed):
    return {**os.environ, "PYTHONHASHSEED": str(hashseed), "PYTHONUNBUFFERED": "1"}


def start_client(name, hashseed, url, tamper=False):
    command = [sys.executable, "-m", "test.run_local", "--client", name, "--url", url]

    if tamper:
        command.append("--tamper")

    return subprocess.Popen(command, cwd=ROOT, env=child_env(hashseed), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def result_of(process, name, timeout):
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()
        return {"name": name, "state": "crashed", "error": f"timed out after {timeout} seconds\n{output.strip()[-800:]}"}

    for line in output.splitlines():
        if line.startswith("RESULT "):
            result = json.loads(line[len("RESULT "):])
            result.setdefault("name", name)
            return result

    return {"name": name, "state": "crashed", "error": output.strip()[-800:] or f"process exited with code {process.returncode}"}


def file_hash(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def orchestrate(args):
    url = f"ws://127.0.0.1:{args.port}"
    server = subprocess.Popen([sys.executable, "-m", "game.server.server", "--port", str(args.port), "--seed", str(args.seed), "--size", str(args.size)], cwd=ROOT, env=child_env(1))
    processes = []
    failures = []

    try:
        time.sleep(1.0)

        if server.poll() is not None:
            print(f"The server exited immediately with code {server.returncode}. See the error above.")
            return 1

        print(f"Server started (seed {args.seed}, {args.size}x{args.size}). Starting two clients; every process generates the world, so this takes a moment...")
        client_specs = [("alice", 2), ("bob", 3)]
        processes = [start_client(name, hashseed, url) for name, hashseed in client_specs]
        results = [result_of(process, name, args.timeout) for process, (name, _) in zip(processes, client_specs)]
        ready = [r for r in results if r["state"] == "ready"]

        for r in results:
            if r["state"] == "ready":
                print(f"  {r['name']:<6} player {r['player_id']} | {r['width']}x{r['height']} | checksum {r['checksum'][:16]} | {r['png']} | PYTHONHASHSEED={r['hashseed']}")
            else:
                failures.append(f"{r['name']} did not become ready: {r['error']}")

        if len(ready) == 2:
            a, b = ready

            if a["checksum"] != b["checksum"]:
                failures.append("the two clients generated different terrain (checksums differ)")

            if file_hash(a["png"]) != file_hash(b["png"]):
                failures.append(f"{a['png']} and {b['png']} are not identical")

            if a["player_id"] == b["player_id"]:
                failures.append("both clients got the same player id")

            if (a["seed"], a["width"], a["height"]) != (args.seed, args.size, args.size):
                failures.append(f"clients got seed/size {(a['seed'], a['width'], a['height'])}, expected {(args.seed, args.size, args.size)}")

            if not failures:
                print("OK: both clients verified the server's checksum and their terrain is identical.")

        if args.test_mismatch:
            print("Starting a client with a tampered world; the server should be refused...")
            process = start_client("mallory", 4, url, tamper=True)
            processes.append(process)
            r = result_of(process, "mallory", args.timeout)

            if r["state"] == "failed" and "world mismatch" in (r["error"] or ""):
                print(f"OK: the tampered client refused to continue:\n  {r['error']}")
            else:
                failures.append(f"the tampered client should have refused to continue, but got: {r}")
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()

        server.terminate()

        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    for failure in failures:
        print(f"FAILED: {failure}")

    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="Run a server and two clients locally and compare their terrain.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--size", type=int, default=200, help="world width and height in tiles")
    parser.add_argument("--port", type=int, default=8797)
    parser.add_argument("--timeout", type=float, default=600, help="seconds to wait for each client")
    parser.add_argument("--test-mismatch", action="store_true", help="also check that a tampered client is refused")
    parser.add_argument("--client", help=argparse.SUPPRESS)
    parser.add_argument("--url", help=argparse.SUPPRESS)
    parser.add_argument("--tamper", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    sys.exit(run_client(args) if args.client else orchestrate(args))


if __name__ == "__main__":
    main()
