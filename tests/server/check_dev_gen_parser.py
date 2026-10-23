import random
import sys

from src.simworld.client.ui.dev.console_state import complete, sources
from src.simworld.shared import dev_commands as d

failures = []
CONTEXT = {"selected": 7, "cursor": (4.5, 6.0)}


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


def message(call):
    try:
        call()
    except d.DevSyntaxError as problem:
        return str(problem)
    except Exception as problem:
        return f"WRONG {type(problem).__name__}: {problem}"

    return None


def plain(args):
    return isinstance(args, dict) and all(isinstance(key, str) and type(value) in (int, float, str) for key, value in args.items())


cases = [
    ("/gen list", ("gen", {"action": "list"})),
    ("gen list", ("gen", {"action": "list"})),
    ("/GEN LIST", ("gen", {"action": "list"})),
    ("  /gen   list  ", ("gen", {"action": "list"})),
    ("/gen feature arctic off", ("gen", {"action": "feature", "name": "arctic", "value": "off"})),
    ("/gen feature arctic on", ("gen", {"action": "feature", "name": "arctic", "value": "on"})),
    ("/gen feature arctic OFF", ("gen", {"action": "feature", "name": "arctic", "value": "off"})),
    ("/gen map height off", ("gen", {"action": "map", "name": "height", "value": "off"})),
    ("/gen map height on", ("gen", {"action": "map", "name": "height", "value": "on"})),
    ("/gen seed 0", ("gen", {"action": "seed", "value": 0})),
    ("/gen seed 12345", ("gen", {"action": "seed", "value": 12345})),
    ("/gen seed 4294967295", ("gen", {"action": "seed", "value": 4294967295})),
]

def parsed(text):
    try:
        return d.parse(text, CONTEXT)
    except Exception as problem:
        return f"ERROR {problem}"


for text, wanted in cases:
    check(f"{text!r} gives {wanted}", parsed(text) == wanted, str(parsed(text)))

errors = {
    "/gen": "missing <action>",
    "/gen nope": "unknown action 'nope'",
    "/gen list extra": "too many arguments",
    "/gen feature": "missing <name>",
    "/gen feature arctic": "missing <on|off>",
    "/gen feature arctic maybe": "must be on or off",
    "/gen feature arctic on off": "too many arguments",
    "/gen map": "missing <name>",
    "/gen map height 1": "must be on or off",
    "/gen seed": "missing <n>",
    "/gen seed abc": "not a whole number",
    "/gen seed 1.5": "not a whole number",
    "/gen seed -1": "from 0 to 4294967295",
    "/gen seed 4294967296": "from 0 to 4294967295",
    "/gen seed 1 2": "too many arguments",
    "/gen feature a/b off": "must be a name",
    "/gen feature item:x:y off": "must be a name",
}

for text, wanted in errors.items():
    got = message(lambda: d.parse(text, CONTEXT))
    check(f"{text!r} gives a readable error containing {wanted!r}", got is not None and wanted in got and not got.startswith("WRONG"), repr(got))

check("errors show the usage", "/gen list | feature <name> on|off | map <name> on|off | seed <n>" in message(lambda: d.parse("/gen", CONTEXT)))
check("usage text for gen", d.usage("gen") == "/gen list | feature <name> on|off | map <name> on|off | seed <n>")
check("the table entry has an example that starts with /gen and parses", d.DEV_COMMANDS["gen"].example == "/gen feature arctic off" and d.parse(d.DEV_COMMANDS["gen"].example, CONTEXT)[0] == "gen")
check("the help line for gen is one line", len([line for line in d.help_lines() if line.startswith("/gen ")]) == 1 and all("\n" not in line for line in d.help_lines()))
check("the other usages are unchanged", [d.usage(name) for name in ("pause", "spawn", "tile")] == ["/pause", "/spawn <blueprint> [x y]", "/tile <name> [x y]"])

for args, wanted in (
    ({"action": "list"}, {"action": "list"}),
    ({"action": "feature", "name": "arctic", "value": "off"}, {"action": "feature", "name": "arctic", "value": "off"}),
    ({"action": "map", "name": "height", "value": "on"}, {"action": "map", "name": "height", "value": "on"}),
    ({"action": "seed", "value": 7}, {"action": "seed", "value": 7}),
    ({"action": "seed", "value": 0}, {"action": "seed", "value": 0}),
    ({"action": "seed", "value": 2**32 - 1}, {"action": "seed", "value": 2**32 - 1}),
):
    check(f"validate keeps {args}", d.validate("gen", args) == wanted and plain(d.validate("gen", args)), str(message(lambda: d.validate("gen", args))))

bad = {
    "missing action": ({}, "missing argument 'action'"),
    "unknown action": ({"action": "regen"}, "must be one of"),
    "action not text": ({"action": 5}, "must be one of"),
    "action none": ({"action": None}, "must be one of"),
    "action list": ({"action": ["list"]}, "must be one of"),
    "list with a name": ({"action": "list", "name": "x"}, "unexpected argument 'name'"),
    "list with a value": ({"action": "list", "value": "on"}, "unexpected argument 'value'"),
    "extra key": ({"action": "list", "x": 1}, "unexpected argument"),
    "non-text key": ({"action": "list", 5: 1}, "unexpected argument"),
    "feature without name": ({"action": "feature", "value": "on"}, "missing argument 'name'"),
    "feature without value": ({"action": "feature", "name": "a"}, "missing argument 'value'"),
    "feature value maybe": ({"action": "feature", "name": "a", "value": "maybe"}, "must be on or off"),
    "feature value true": ({"action": "feature", "name": "a", "value": True}, "must be on or off"),
    "feature value number": ({"action": "feature", "name": "a", "value": 1}, "must be on or off"),
    "feature value list": ({"action": "feature", "name": "a", "value": ["on"]}, "must be on or off"),
    "feature value uppercase": ({"action": "feature", "name": "a", "value": "ON"}, "must be on or off"),
    "feature name with space": ({"action": "feature", "name": "a b", "value": "on"}, "must be a name"),
    "feature name number": ({"action": "feature", "name": 5, "value": "on"}, "must be a name"),
    "feature name empty": ({"action": "feature", "name": "", "value": "on"}, "must be a name"),
    "feature name long": ({"action": "feature", "name": "x" * 100, "value": "on"}, "must be a name"),
    "map without name": ({"action": "map", "value": "on"}, "missing argument 'name'"),
    "seed with name": ({"action": "seed", "name": "x", "value": 1}, "unexpected argument 'name'"),
    "seed without value": ({"action": "seed"}, "missing argument 'value'"),
    "seed float": ({"action": "seed", "value": 1.5}, "whole number"),
    "seed text": ({"action": "seed", "value": "7"}, "whole number"),
    "seed bool": ({"action": "seed", "value": True}, "whole number"),
    "seed none": ({"action": "seed", "value": None}, "whole number"),
    "seed negative": ({"action": "seed", "value": -1}, "from 0 to 4294967295"),
    "seed too big": ({"action": "seed", "value": 2**32}, "from 0 to 4294967295"),
    "seed huge": ({"action": "seed", "value": 10**400}, "from 0 to 4294967295"),
}

for label, (args, wanted) in bad.items():
    got = message(lambda: d.validate("gen", args))
    check(f"validate refuses {label}", got is not None and wanted in got and not got.startswith("WRONG"), repr(got))

check("validate of non-dict args for gen says args must be a map", all(message(lambda a=a: d.validate("gen", a)) == "args must be a map" for a in (None, 5, "x", [], [1], True)))

check("the Tab source for gen is the four actions", sources("gen", None) == ["list", "feature", "map", "seed"] and sources("gen", {"tiles": ["a"]}) == ["list", "feature", "map", "seed"])
check("/gen Tab lists the actions", complete("/gen ", None).options == ["feature", "list", "map", "seed"], str(complete("/gen ", None)))
check("/gen f completes to feature and asks for more words", complete("/gen f", None).text == "/gen feature ", str(complete("/gen f", None)))
check("/gen l completes to list", complete("/gen l", None).text == "/gen list ", str(complete("/gen l", None)))
check("/gen feature <tab> has nothing to complete", complete("/gen feature ", None).text == "/gen feature " and complete("/gen feature ", None).options == [])
check("/ lists gen among the commands", "gen" in complete("/", None).options and complete("/g", None).text == "/gen ", str(complete("/g", None)))

random.seed(11)
words = ["gen", "list", "feature", "map", "seed", "on", "off", "arctic", "height", "0", "7", "-1", "4294967296", "1.5", "x" * 70, "nan", "~", "@", "ON"]
odd = []

for _ in range(4000):
    text = "/" + " ".join(random.choice(words) for _ in range(random.randint(1, 6)))

    try:
        what, args = d.parse(text, CONTEXT)
        assert what in d.DEV_COMMANDS and plain(args) and d.validate(what, args) == args, (text, what, args)
    except d.DevSyntaxError:
        pass
    except Exception as problem:
        odd.append((text, repr(problem)))

check("random gen text only ever parses cleanly or gives a DevSyntaxError", not odd, str(odd[:3]))

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")