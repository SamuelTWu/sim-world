"""Checks that the rendering code never reaches into the simulation.

Run from the project root:
    python check_renderer_isolation.py                 scans game/rendering
    python check_renderer_isolation.py game/rendering other/folder

The renderer may only use what it is given in a View (server/replica.py): the client's own world, maps,
features and replicated entities. This reports any import of simulation code and any use of the name
Simulation or a `.sim` attribute. Exit code 1 if it finds one.
"""
import ast
import sys
from pathlib import Path

FORBIDDEN = ("game.simulation", "game.entity", "game.game", "server.server", "server.local")
FORBIDDEN_NAMES = {"Simulation"}
FORBIDDEN_ATTRIBUTES = {"sim"}


def forbidden(module):
    return next((prefix for prefix in FORBIDDEN if module == prefix or module.startswith(prefix + ".")), None)


def imported_modules(node, package):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    if node.level:
        base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
        prefix = ".".join(base + (node.module.split(".") if node.module else []))
    else:
        prefix = node.module or ""

    return [prefix] + [f"{prefix}.{alias.name}" if prefix else alias.name for alias in node.names]


def scan(path):
    package = list(path.with_suffix("").parts[:-1])
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module in imported_modules(node, package):
                prefix = forbidden(module)

                if prefix:
                    found.append((node.lineno, f"imports {module} (simulation code)"))
                    break
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.append((node.lineno, f"uses the name {node.id}"))
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            found.append((node.lineno, f"reads a .{node.attr} attribute"))

    return found


def main():
    roots = [Path(arg) for arg in sys.argv[1:]] or [Path("game/rendering")]
    files = []

    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(p for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts)
        else:
            print(f"(skipping {root}: not found)")

    count = 0

    for path in files:
        for line, problem in sorted(set(scan(path))):
            print(f"{path.as_posix()}:{line}  {problem}")
            count += 1

    if count:
        print(f"\n{count} problem(s). Move shared constants to a neutral module, or pass the value in through the View.")
        return 1

    print(f"OK: {len(files)} rendering file(s) do not touch the simulation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())