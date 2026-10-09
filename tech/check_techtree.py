"""Loads the tech tree, reports every mistake in the JSON files, and prints the tree as text.

Run from the project root:
    python check_techtree.py                     checks game/tech/nodes
    python check_techtree.py some/other/folder
"""
import sys
from pathlib import Path

from tech.tech import DEFAULT_FOLDER, KINDS, TechTreeError, load_tree


def cost_text(cost):
    return ", ".join(f"{amount:g} {currency}" for currency, amount in cost.items()) or "free"


def provides_text(provides):
    return " | ".join(f"{category}: {', '.join(names)}" for category, names in provides.items() if names) or "nothing"


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FOLDER

    try:
        from tech.known import known_names

        known = known_names()
        note = "provides checked against the game's " + ", ".join(sorted(known))
    except Exception as problem:
        known = None
        note = f"provides were NOT cross-checked against the game ({problem!r})"

    try:
        tree = load_tree(folder, known)
    except TechTreeError as problem:
        print(problem)
        return 1

    counts = ", ".join(f"{kind} {len(tree.by_kind(kind))}" for kind in KINDS)
    print(f"Tech tree: {len(tree.nodes)} nodes ({counts}), {len(tree.starting())} unlocked from the start")
    print(note)
    order = {node_id: index for index, node_id in enumerate(tree.nodes)}

    for kind in KINDS:
        nodes = sorted(tree.by_kind(kind), key=lambda node: (tree.tier(node.id), order[node.id]))

        if not nodes:
            continue

        id_width = max(len(node.id) for node in nodes)
        name_width = max(len(node.name) for node in nodes)
        cost_width = max(len(cost_text(node.cost)) for node in nodes)
        print(f"\n{kind.upper()}")

        for node in nodes:
            after = "start" if node.starts_unlocked else ("after " + ", ".join(node.requires) if node.requires else "open")
            print(f"  tier {tree.tier(node.id)}  {node.id:<{id_width}}  {node.name:<{name_width}}  {cost_text(node.cost):<{cost_width}}  {after:<28}  {provides_text(node.provides)}")

    if tree.warnings:
        print("\nWarnings:")

        for warning in tree.warnings:
            print(f"  - {warning}")

    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())