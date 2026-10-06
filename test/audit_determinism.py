"""Static determinism audit for world generation.

Run from the project root (the folder that contains game/):
    python audit_determinism.py                    scans game/world game/map game/feature game/tile
    python audit_determinism.py game/map           scans specific files or folders
    python audit_determinism.py --min medium       hides LOW findings

Put `# determinism: ok` on a line you have reviewed to silence it.
This reads the code without running it, so it finds suspects, not proof.
"""
import argparse
import ast
import sys
from pathlib import Path

DEFAULT_PATHS = ["game/world", "game/map", "game/feature", "game/tile"]
LEVELS = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
SUPPRESS = "determinism: ok"

SET_FUNCS = {"set", "frozenset"}
SET_METHODS = {"union", "intersection", "difference", "symmetric_difference"}
SET_OPS = (ast.BitOr, ast.BitAnd, ast.Sub, ast.BitXor)
SET_ANNOTATIONS = {"set", "frozenset", "Set", "FrozenSet", "AbstractSet", "MutableSet"}
SAFE_CONSUMERS = {"sorted", "len", "any", "all", "set", "frozenset"}
ORDER_CONSUMERS = {"list", "tuple", "enumerate", "zip", "map", "filter", "sum", "min", "max", "next", "iter", "reversed", "dict"}
EXTERNAL_LOADERS = {"json.load", "json.loads", "tomllib.load", "tomllib.loads", "yaml.load", "yaml.safe_load", "msgpack.unpackb", "msgpack.unpack", "pickle.load", "pickle.loads"}
FS_ORDER_CALLS = {"os.listdir", "os.scandir", "os.walk", "glob.glob", "glob.iglob", "pkgutil.iter_modules", "pkgutil.walk_packages"}
FS_ORDER_METHODS = {"iterdir", "glob", "rglob"}
TIME_CALLS = {"time.time", "time.time_ns", "time.monotonic", "time.monotonic_ns", "time.perf_counter", "time.perf_counter_ns", "time.process_time"}
DATETIME_CALLS = {"datetime.datetime.now", "datetime.datetime.utcnow", "datetime.datetime.today", "datetime.date.today"}
LIBM = {"sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sinh", "cosh", "tanh", "asinh", "acosh", "atanh", "exp", "exp2", "expm1", "log", "log2", "log10", "log1p", "pow", "erf", "erfc", "gamma", "lgamma", "cbrt"}
SORT_FIX = "wrap it in sorted(...), or use a list / dict so the order is fixed"


def identifier(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def annotation_is_set(annotation):
    if annotation is None:
        return False
    node = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    return identifier(node) in SET_ANNOTATIONS


def lookup(registry, node, path, scope):
    if isinstance(node, ast.Name):
        return registry.get((path, scope, node.id)) or registry.get(node.id)

    if isinstance(node, ast.Attribute):
        return registry.get(node.attr)

    return None


def set_kind(node, registry, path, scope):
    """Returns (level, detail) if the expression is (or may be) a set, else None."""
    if isinstance(node, (ast.Set, ast.SetComp)):
        return "HIGH", "set literal"

    if isinstance(node, ast.Call):
        func = node.func

        if isinstance(func, ast.Name) and func.id in SET_FUNCS:
            return "HIGH", f"{func.id}(...)"

        if isinstance(func, ast.Attribute) and func.attr in SET_METHODS and set_kind(func.value, registry, path, scope):
            return "HIGH", f"result of .{func.attr}()"

        return None

    if isinstance(node, ast.BinOp) and isinstance(node.op, SET_OPS) and (set_kind(node.left, registry, path, scope) or set_kind(node.right, registry, path, scope)):
        return "HIGH", "result of a set operation"

    origin = lookup(registry, node, path, scope)

    if origin:
        return "MEDIUM", f"'{identifier(node)}' is assigned a set at {origin}"

    return None


class SetCollector(ast.NodeVisitor):
    """Pass 1: remember every name or attribute that is assigned or annotated as a set."""

    def __init__(self, path, registry):
        self.path = path
        self.registry = registry
        self.added = False
        self.scope = []

    def key(self, target):
        name = identifier(target)

        if name is None:
            return None

        if isinstance(target, ast.Name) and self.scope:
            return (self.path, ".".join(self.scope), name)

        return name

    def register(self, key, node):
        if key and key not in self.registry:
            self.registry[key] = f"{self.path}:{node.lineno}"
            self.added = True

    def kind(self, node):
        return set_kind(node, self.registry, self.path, ".".join(self.scope))

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple) and len(target.elts) == len(node.value.elts):
                for part, value in zip(target.elts, node.value.elts):
                    if self.kind(value):
                        self.register(self.key(part), node)
            elif self.kind(node.value):
                self.register(self.key(target), node)

        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if annotation_is_set(node.annotation) or (node.value is not None and self.kind(node.value)):
            self.register(self.key(node.target), node)

        self.generic_visit(node)

    def visit_arg(self, node):
        if annotation_is_set(node.annotation):
            self.register((self.path, ".".join(self.scope), node.arg) if self.scope else node.arg, node)

        self.generic_visit(node)


class Auditor(ast.NodeVisitor):
    """Pass 2: report anything that can make generation differ between runs or machines."""

    def __init__(self, path, source, tree, registry, findings):
        self.path = path
        self.lines = source.splitlines()
        self.registry = registry
        self.findings = findings
        self.aliases = {}
        self.ext_names = {}
        self.safe = 0
        self.scope = []
        self.numpy_noted = False
        self.collect_imports(tree)
        self.collect_external(tree)

    def collect_imports(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    root = item.name.split(".")[0]
                    self.aliases[item.asname or root] = item.name if item.asname else root
                    self.note_numpy(root, node)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for item in node.names:
                    self.aliases[item.asname or item.name] = f"{node.module}.{item.name}"
                self.note_numpy(node.module.split(".")[0], node)

    def collect_external(self, tree):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue

            value = node.value

            while isinstance(value, ast.Subscript):
                value = value.value

            if isinstance(value, ast.Call):
                qualified = self.qualname(value.func)

                if qualified in EXTERNAL_LOADERS:
                    for target in node.targets:
                        name = identifier(target)

                        if name:
                            self.ext_names[name] = f"{qualified}() on line {node.lineno}"

    def note_numpy(self, root, node):
        if root == "numpy" and not self.numpy_noted:
            self.numpy_noted = True
            self.add(node, "LOW", "numpy", "numpy imported: float results and RNG streams can differ between numpy versions and CPUs",
                     "keep world generation in plain Python, or confirm with the cross-machine checksum")

    def qualname(self, node):
        parts = []

        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value

        if isinstance(node, ast.Name) and node.id in self.aliases:
            return ".".join([self.aliases[node.id]] + parts[::-1])

        return None

    def add(self, node, level, rule, message, fix=""):
        line = self.lines[node.lineno - 1] if 0 < node.lineno <= len(self.lines) else ""

        if SUPPRESS in line.lower():
            return

        self.findings.append((self.path, node.lineno, level, rule, message, fix, line.strip()))

    def kind(self, node):
        return set_kind(node, self.registry, self.path, ".".join(self.scope))

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def unordered(self, node):
        kind = self.kind(node)

        if kind:
            return kind[0], "set-order", f"a set in arbitrary order ({kind[1]})", SORT_FIX

        target = node

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("items", "keys", "values"):
            target = node.func.value

        name = identifier(target)

        if name in self.ext_names:
            return "MEDIUM", "dict-order", f"a dict in the key order of its external data ('{name}' comes from {self.ext_names[name]}; ignore if it is a list)", "iterate sorted(data) / sorted(data.items()), or use an explicit key list"

        return None

    def check_order(self, expr, anchor, how):
        if self.safe:
            return

        found = self.unordered(expr)

        if found:
            level, rule, description, fix = found
            self.add(anchor, level, rule, f"{how} reads {description}", fix)

    def visit_For(self, node):
        self.check_order(node.iter, node, "this for loop")
        self.generic_visit(node)

    def visit_ListComp(self, node):
        for generator in node.generators:
            self.check_order(generator.iter, node, "this comprehension")

        self.generic_visit(node)

    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_SetComp(self, node):
        self.safe += 1
        self.generic_visit(node)
        self.safe -= 1

    def visit_Set(self, node):
        self.safe += 1
        self.generic_visit(node)
        self.safe -= 1

    def visit_Starred(self, node):
        self.check_order(node.value, node, "* unpacking")
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Pow) and isinstance(node.right, ast.Constant) and isinstance(node.right.value, float) and not node.right.value.is_integer():
            if node.right.value == 0.5:
                self.add(node, "MEDIUM", "libm", "** 0.5 goes through the C pow() function and can differ between platforms", "use math.sqrt(x), which is exactly rounded")
            else:
                self.add(node, "MEDIUM", "libm", f"** {node.right.value} goes through the C pow() function and can differ between platforms", "avoid it in generation, or confirm with the cross-machine checksum")

        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        qualified = self.qualname(func)

        if isinstance(func, ast.Name) and func.id not in self.aliases:
            if func.id == "hash":
                self.add(node, "HIGH", "hash", "hash() changes between runs for str/bytes (and tuples containing them)", "use hashlib (e.g. sha256 of the text), a fixed table, or only hash ints")
            elif func.id == "id":
                self.add(node, "MEDIUM", "id", "id() is a memory address and differs between runs", "never use it for ordering, seeding, or keys that affect the world")

        if qualified:
            self.check_qualified(node, qualified)

        if isinstance(func, ast.Name) and func.id in ORDER_CONSUMERS and func.id not in self.aliases and node.args:
            self.check_order(node.args[0], node, f"{func.id}()")

        if isinstance(func, ast.Attribute):
            if func.attr == "join" and node.args:
                self.check_order(node.args[0], node, ".join()")
            elif func.attr in ("extend", "fromkeys") and node.args:
                self.check_order(node.args[0], node, f".{func.attr}()")
            elif func.attr == "pop" and not node.args:
                kind = self.kind(func.value)

                if kind:
                    self.add(node, kind[0], "set-order", f"set.pop() takes an arbitrary element ({kind[1]})", "keep a sorted list and pop from that")
            elif func.attr == "__subclasses__":
                self.add(node, "MEDIUM", "subclasses", "__subclasses__() order follows import order", "sort by class name")

            if func.attr in FS_ORDER_METHODS and qualified not in FS_ORDER_CALLS and not self.safe:
                self.add(node, "MEDIUM", "fs-order", f".{func.attr}() returns files in directory order, which differs between machines", "wrap it in sorted(...)")

        if isinstance(func, ast.Name) and func.id in SAFE_CONSUMERS and func.id not in self.aliases:
            self.safe += 1
            self.generic_visit(node)
            self.safe -= 1
        else:
            self.generic_visit(node)

    def check_qualified(self, node, q):
        unseeded = not node.args and not node.keywords
        none_seed = bool(node.args) and isinstance(node.args[0], ast.Constant) and node.args[0].value is None

        if q == "random.Random":
            if unseeded or none_seed:
                self.add(node, "HIGH", "unseeded-rng", "random.Random() without a seed is different every run", "seed it from settings.seed, e.g. random.Random(f\"world:{seed}\")")
        elif q == "random.SystemRandom" or q in ("os.urandom", "uuid.uuid1", "uuid.uuid4") or q.startswith("secrets."):
            self.add(node, "HIGH", "entropy", f"{q}() is true randomness and cannot be reproduced", "derive the value from the seed instead")
        elif q == "random.seed":
            self.add(node, "MEDIUM", "global-random", "random.seed() reseeds the shared global generator", "use your own random.Random(seed) instance")
        elif q.startswith("random."):
            self.add(node, "HIGH", "global-random", f"{q}() uses the shared global generator", "use generator.random / context.random instead")
        elif q.startswith("numpy.random."):
            leaf = q.rsplit(".", 1)[1]

            if leaf in ("default_rng", "RandomState"):
                if unseeded or none_seed:
                    self.add(node, "HIGH", "unseeded-rng", f"numpy {leaf}() without a seed is different every run", "pass a seed from settings.seed")
                else:
                    self.add(node, "MEDIUM", "numpy", f"numpy {leaf} streams are not guaranteed to match across numpy versions", "prefer a pure-Python generator for anything that shapes the world")
            else:
                self.add(node, "HIGH", "global-random", f"{q}() uses numpy's shared global generator", "use a seeded generator instance")
        elif q in TIME_CALLS:
            self.add(node, "LOW", "time", f"{q}() is fine for timing/logging but must never influence generation", "mark it `# determinism: ok` if it only feeds a print")
        elif q in DATETIME_CALLS:
            self.add(node, "MEDIUM", "time", f"{q}() depends on the wall clock", "never let it influence generation")
        elif q in FS_ORDER_CALLS and not self.safe:
            self.add(node, "MEDIUM", "fs-order", f"{q}() returns entries in directory order, which differs between machines", "wrap it in sorted(...)")
        elif q.startswith("math.") and q.split(".", 1)[1] in LIBM:
            self.add(node, "MEDIUM", "libm", f"{q}() uses the platform's C math library and can differ in the last bits between machines", "avoid it in generation, or confirm with the cross-machine checksum")


def gather(paths):
    files = []

    for raw in paths:
        path = Path(raw)

        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in sorted(path.rglob("*.py")) if "__pycache__" not in p.parts)
        else:
            print(f"(skipping {raw}: not found)")

    return files


def main():
    parser = argparse.ArgumentParser(description="Static determinism audit for world generation.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS)
    parser.add_argument("--min", choices=["low", "medium", "high"], default="low", help="lowest severity to show")
    args = parser.parse_args()

    parsed = []

    for path in gather(args.paths):
        try:
            source = path.read_text(encoding="utf-8")
            parsed.append((path, source, ast.parse(source, filename=str(path))))
        except (SyntaxError, UnicodeDecodeError, OSError) as error:
            print(f"(could not read {path}: {error})")

    registry = {}

    for _ in range(4):
        added = False

        for path, _source, tree in parsed:
            collector = SetCollector(path.as_posix(), registry)
            collector.visit(tree)
            added = added or collector.added

        if not added:
            break

    findings = []

    for path, source, tree in parsed:
        Auditor(path.as_posix(), source, tree, registry, findings).visit(tree)

    threshold = LEVELS[args.min.upper()]
    shown = sorted({f for f in findings if LEVELS[f[2]] >= threshold}, key=lambda f: (f[0], f[1], -LEVELS[f[2]], f[3]))

    current = None

    for path, line, level, rule, message, fix, code in shown:
        if path != current:
            print(f"\n{path}")
            current = path

        print(f"  line {line:<5} {level:<7} [{rule}] {message}")
        print(f"             {code}")

        if fix:
            print(f"             fix: {fix}")

    print(f"\nScanned {len(parsed)} file(s).")
    counts = {level: sum(1 for f in shown if f[2] == level) for level in ("HIGH", "MEDIUM", "LOW")}
    print("Findings: " + ", ".join(f"{counts[level]} {level}" for level in ("HIGH", "MEDIUM", "LOW")))
    print("HIGH = will break determinism. MEDIUM = check it. LOW = usually fine, listed for completeness.")
    print("Set/dict findings match names across files, so a MEDIUM 'possibly a set' can be a name clash.")
    print("A clean run is not proof: also run check_noise.py, check_sim_determinism.py, and compare world checksums on two machines.")

    return 1 if counts["HIGH"] else 0


if __name__ == "__main__":
    sys.exit(main())