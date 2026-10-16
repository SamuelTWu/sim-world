"""Tech tree data: what can be unlocked, what it costs, and what it provides.

The tree is plain JSON in game/tech/nodes/ (any subfolder works, files starting with _ are ignored; copy
_template.json to start a new node). A file holds nodes, and can set the kind for all of them:

    {
      "kind": "action",
      "nodes": {
        "orders": {
          "name": "Orders",
          "description": "Pixels can obey move commands.",
          "cost": 20,
          "requires": ["wandering"],
          "provides": {"commands": ["move"]}
        }
      }
    }

Node fields (everything but the id is optional, except that a node needs a kind from somewhere):
    kind             body, sense, action or reaction (on the node, or once at the top of the file; "class" also works)
    name             shown in the window (default: the id, tidied up)
    description      shown in the window
    cost             a number (paid in DEFAULT_CURRENCY) or {"currency": 10, "stone": 5}; 0 or missing is free
    requires         ids of nodes that must be unlocked first (this is what draws the tree)
    provides         {"traits": [...], "props": [...], "commands": [...], "triggers": [...], "effects": [...],
                      "resources": [...]}   (see PROVIDES; add a category there)
    starts_unlocked  true if every player owns it from the start (it cannot require anything that is locked)

load_tree() checks all of it and reports every mistake at once, with the file and node, so a typo is easy to find.
Pass `known` (see known.py) to also check that provided commands, triggers and effects really exist.
This file imports nothing from the rest of the game.
"""
import difflib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("body", "sense", "action", "reaction")
PROVIDES = ("traits", "props", "commands", "triggers", "effects", "resources")
DEFAULT_CURRENCY = "currency"
DEFAULT_FOLDER = Path(__file__).resolve().parent / "nodes"

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
NODE_KEYS = ("name", "description", "kind", "class", "cost", "requires", "provides", "starts_unlocked")
FILE_KEYS = ("kind", "class", "nodes")
MAX_LISTED = 15


class TechTreeError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(f"{len(self.errors)} problem(s) in the tech tree:\n" + "\n".join(f"  - {error}" for error in self.errors))


class DuplicateKey(ValueError):
    def __init__(self, key):
        super().__init__(key)
        self.key = key


@dataclass(frozen=True)
class TechNode:
    id: str
    name: str
    kind: str
    description: str = ""
    cost: dict = field(default_factory=dict)
    requires: tuple = ()
    provides: dict = field(default_factory=dict)
    starts_unlocked: bool = False
    source: str = ""


@dataclass
class TechTree:
    nodes: dict
    warnings: list = field(default_factory=list)
    tiers: dict = field(default_factory=dict, repr=False)

    def get(self, node_id):
        return self.nodes[node_id]

    def by_kind(self, kind):
        return [node for node in self.nodes.values() if node.kind == kind]

    def children(self, node_id):
        return [node for node in self.nodes.values() if node_id in node.requires]

    def starting(self):
        return [node for node in self.nodes.values() if node.starts_unlocked]

    def tier(self, node_id):
        """0 for a node with no requirements, otherwise one more than its deepest requirement (for laying out the tree)."""
        if node_id not in self.tiers:
            self.tiers[node_id] = 1 + max((self.tier(required) for required in self.nodes[node_id].requires), default=-1)

        return self.tiers[node_id]

    def provided_by(self, owned, category):
        """Every name in `category` provided by the owned node ids, in tree order."""
        names = []

        for node in self.nodes.values():
            if node.id in owned:
                names.extend(name for name in node.provides.get(category, ()) if name not in names)

        return names


def suggest(word, options):
    matches = difflib.get_close_matches(str(word), list(options), n=1)
    return f" (did you mean '{matches[0]}'?)" if matches else ""


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def reject_duplicates(pairs):
    seen = {}

    for key, value in pairs:
        if key in seen:
            raise DuplicateKey(key)

        seen[key] = value

    return seen


def read_json(path, name, errors):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as problem:
        errors.append(f"{name}: could not read the file ({problem})")
        return None

    try:
        return json.loads(text, object_pairs_hook=reject_duplicates)
    except DuplicateKey as problem:
        lines = [str(number) for number, line in enumerate(text.splitlines(), 1) if re.search(rf'"{re.escape(problem.key)}"\s*:', line)]
        errors.append(f"{name}: the key '{problem.key}' appears more than once in the same object (lines {', '.join(lines)})")
    except json.JSONDecodeError as problem:
        errors.append(f"{name}: invalid JSON at line {problem.lineno}, column {problem.colno}: {problem.msg}")

    return None


def pick_kind(where, data, fallback, errors):
    if "kind" in data and "class" in data:
        errors.append(f"{where}: use either 'kind' or 'class', not both")
        return None

    kind = data["kind"] if "kind" in data else data["class"] if "class" in data else fallback

    if kind is not None and kind not in KINDS:
        errors.append(f"{where}: kind {kind!r} is not one of {', '.join(KINDS)}{suggest(kind, KINDS)}")
        return None

    return kind


def parse_cost(value, where, errors):
    amounts = {DEFAULT_CURRENCY: value} if is_number(value) else value

    if not isinstance(amounts, dict):
        errors.append(f"{where}: cost must be a number or a map like {{\"{DEFAULT_CURRENCY}\": 10, \"stone\": 5}}")
        return {}

    cost = {}

    for currency, amount in amounts.items():
        if not currency:
            errors.append(f"{where}: a cost needs a currency name")
        elif not is_number(amount) or not math.isfinite(amount) or amount < 0:
            errors.append(f"{where}: the cost of '{currency}' must be a number that is 0 or more, not {amount!r}")
        elif amount > 0:
            cost[currency] = amount

    return cost


def parse_provides(value, where, known, errors):
    if not isinstance(value, dict):
        errors.append(f"{where}: provides must be a map like {{\"traits\": [\"roam\"]}}")
        return {}

    provides = {}

    for category, names in value.items():
        if category not in PROVIDES:
            errors.append(f"{where}: unknown provides category '{category}'{suggest(category, PROVIDES)}; valid: {', '.join(PROVIDES)}")
        elif not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
            errors.append(f"{where}: provides.{category} must be a list of names")
        else:
            names = list(dict.fromkeys(names))
            valid = known.get(category)

            for name in names:
                if valid is not None and name not in valid:
                    listed = sorted(valid)
                    more = " ..." if len(listed) > MAX_LISTED else ""
                    errors.append(f"{where}: provides.{category} has '{name}', which the game does not define{suggest(name, valid)}; known: {', '.join(listed[:MAX_LISTED])}{more}")

            provides[category] = tuple(names)

    return provides


def build_node(source, node_id, raw, file_kind, known, errors):
    where = f"{source} › {node_id}"
    start = len(errors)

    if not ID_PATTERN.match(node_id):
        errors.append(f"{source}: the node id '{node_id}' must be lowercase letters, digits and underscores, starting with a letter")

    if not isinstance(raw, dict):
        errors.append(f"{where}: a node must be an object")
        return None

    for key in raw:
        if key not in NODE_KEYS:
            errors.append(f"{where}: unknown field '{key}'{suggest(key, NODE_KEYS)}; valid: {', '.join(NODE_KEYS)}")

    kind = pick_kind(where, raw, file_kind, errors)

    if kind is None and "kind" not in raw and "class" not in raw:
        errors.append(f"{where}: no kind. Set \"kind\" on the node or at the top of the file ({', '.join(KINDS)})")

    name = raw.get("name", node_id.replace("_", " ").title())
    description = raw.get("description", "")

    if not isinstance(name, str) or not name:
        errors.append(f"{where}: name must be text")

    if not isinstance(description, str):
        errors.append(f"{where}: description must be text")

    cost = parse_cost(raw.get("cost", 0), where, errors)
    requires = raw.get("requires", [])

    if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
        errors.append(f"{where}: requires must be a list of node ids")
        requires = []

    provides = parse_provides(raw.get("provides", {}), where, known, errors)
    starts_unlocked = raw.get("starts_unlocked", False)

    if not isinstance(starts_unlocked, bool):
        errors.append(f"{where}: starts_unlocked must be true or false")

    if len(errors) > start:
        return None

    return TechNode(node_id, name, kind, description, cost, tuple(dict.fromkeys(requires)), provides, starts_unlocked, source)


def read_file(name, data, known, nodes, sources, requirements, errors):
    if not isinstance(data, dict):
        errors.append(f"{name}: the file must hold an object like {{\"kind\": \"action\", \"nodes\": {{...}}}}")
        return

    for key in data:
        if key not in FILE_KEYS:
            errors.append(f"{name}: unknown key '{key}'{suggest(key, FILE_KEYS)}; valid: {', '.join(FILE_KEYS)}")

    file_kind = pick_kind(name, data, None, errors)
    items = data.get("nodes")

    if not isinstance(items, dict):
        errors.append(f"{name}: the file needs a \"nodes\" object")
        return

    for node_id, raw in items.items():
        if node_id in sources:
            errors.append(f"{name} › {node_id}: already defined in {sources[node_id]}")
            continue

        sources[node_id] = name
        wanted = raw.get("requires") if isinstance(raw, dict) else None

        if isinstance(wanted, list) and all(isinstance(item, str) for item in wanted):
            requirements[node_id] = (name, tuple(dict.fromkeys(wanted)))

        node = build_node(name, node_id, raw, file_kind, known, errors)

        if node is not None:
            nodes[node_id] = node


def link(nodes, sources, requirements, errors, warnings):
    for node_id, (source, requires) in requirements.items():
        where = f"{source} › {node_id}"

        for required in requires:
            if required == node_id:
                errors.append(f"{where}: requires itself")
            elif required not in sources:
                errors.append(f"{where}: requires '{required}', which does not exist{suggest(required, sources)}")
            elif node_id in nodes and nodes[node_id].starts_unlocked and required in nodes and not nodes[required].starts_unlocked:
                errors.append(f"{where}: starts unlocked but requires '{required}', which does not start unlocked")

    for node in nodes.values():
        where = f"{node.source} › {node.id}"

        if not any(node.provides.values()):
            warnings.append(f"{where}: provides nothing")

        if node.starts_unlocked and node.cost:
            warnings.append(f"{where}: starts unlocked, so its cost is never paid")

    state = {}
    path = []

    def visit(node_id):
        state[node_id] = 1
        path.append(node_id)

        for required in nodes[node_id].requires:
            if required not in nodes or required == node_id:
                continue

            if state.get(required) == 1:
                loop = path[path.index(required):] + [required]
                errors.append(f"{nodes[required].source} › {required}: the requirements form a loop: {' -> '.join(loop)}")
            elif required not in state:
                visit(required)

        path.pop()
        state[node_id] = 2

    for node_id in nodes:
        if node_id not in state:
            visit(node_id)


def load_tree(folder=None, known=None):
    """Read and check every node file. Raises TechTreeError listing all problems; otherwise returns a TechTree."""
    folder = Path(folder) if folder is not None else DEFAULT_FOLDER

    if not folder.is_dir():
        raise TechTreeError([f"tech tree folder not found: {folder}"])

    errors, warnings, nodes, sources, requirements = [], [], {}, {}, {}
    files = [path for path in sorted(folder.rglob("*.json")) if not any(part.startswith("_") for part in path.relative_to(folder).parts)]

    if not files:
        warnings.append(f"no node files found in {folder}")

    for path in files:
        name = path.relative_to(folder).as_posix()
        data = read_json(path, name, errors)

        if data is not None:
            read_file(name, data, known or {}, nodes, sources, requirements, errors)

    link(nodes, sources, requirements, errors, warnings)

    if errors:
        raise TechTreeError(errors)

    return TechTree(nodes, warnings)