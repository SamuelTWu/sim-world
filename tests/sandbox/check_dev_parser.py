import random
import sys

from src.simworld.shared import dev_commands as d

failures = []
CONTEXT = {"selected": 7, "cursor": (4.5, 6.0)}
EMPTY = {"selected": None, "cursor": None}


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


expected = ["catalog", "delete", "help", "inspect", "pause", "spawn", "speed", "step", "tile", "wake"]
check("the table has exactly the planned commands", d.names() == expected, str(d.names()))

for what, command in d.DEV_COMMANDS.items():
    check(f"{what}: has help text and an example that starts with /{what}", bool(command.help) and command.example.split()[0] == f"/{what}")
    parsed = d.parse(command.example, CONTEXT)
    check(f"{what}: parses its example", parsed[0] == what and plain(parsed[1]), str(parsed))
    check(f"{what}: the parsed args pass validate unchanged", d.validate(what, parsed[1]) == parsed[1])
    check(f"{what}: usage starts with /{what}", d.usage(what).startswith(f"/{what}"), d.usage(what))

cases = [
    ("/pause", CONTEXT, ("pause", {})),
    ("pause", CONTEXT, ("pause", {})),
    ("/PAUSE", CONTEXT, ("pause", {})),
    ("  /pause  ", CONTEXT, ("pause", {})),
    ("/step", CONTEXT, ("step", {"count": 1})),
    ("/step 5", CONTEXT, ("step", {"count": 5})),
    ("/step 100", CONTEXT, ("step", {"count": 100})),
    ("/speed 0.25", CONTEXT, ("speed", {"factor": 0.25})),
    ("/speed 1", CONTEXT, ("speed", {"factor": 1.0})),
    ("/speed 4", CONTEXT, ("speed", {"factor": 4.0})),
    ("/spawn wolf 10 12", CONTEXT, ("spawn", {"blueprint": "wolf", "x": 10.0, "y": 12.0})),
    ("/spawn wolf 1.5 -2", CONTEXT, ("spawn", {"blueprint": "wolf", "x": 1.5, "y": -2.0})),
    ("/spawn wolf", CONTEXT, ("spawn", {"blueprint": "wolf", "x": 4.5, "y": 6.0})),
    ("/spawn wolf ~", CONTEXT, ("spawn", {"blueprint": "wolf", "x": 4.5, "y": 6.0})),
    ("/delete 3", CONTEXT, ("delete", {"id": 3})),
    ("/delete", CONTEXT, ("delete", {"id": 7})),
    ("/delete @", CONTEXT, ("delete", {"id": 7})),
    ("/wake", CONTEXT, ("wake", {"id": 7})),
    ("/wake @", CONTEXT, ("wake", {"id": 7})),
    ("/inspect 12", CONTEXT, ("inspect", {"id": 12})),
    ("/inspect", CONTEXT, ("inspect", {"id": 7})),
    ("/tile stone 4 4", CONTEXT, ("tile", {"name": "stone", "x": 4.0, "y": 4.0})),
    ("/tile stone", CONTEXT, ("tile", {"name": "stone", "x": 4.5, "y": 6.0})),
    ("/tile stone ~", CONTEXT, ("tile", {"name": "stone", "x": 4.5, "y": 6.0})),
    ("/catalog", CONTEXT, ("catalog", {})),
    ("/help", CONTEXT, ("help", {})),
    ("/help spawn", CONTEXT, ("help", {"command": "spawn"})),
    ("/spawn wolf 3 4", EMPTY, ("spawn", {"blueprint": "wolf", "x": 3.0, "y": 4.0})),
    ("/delete 3", EMPTY, ("delete", {"id": 3})),
    ("/pause", None, ("pause", {})),
    ("/spawn wolf", {"cursor": [2, 3]}, ("spawn", {"blueprint": "wolf", "x": 2.0, "y": 3.0})),
]

for text, context, want in cases:
    got = message(lambda: d.parse(text, context)) or d.parse(text, context)
    check(f"parse {text!r} {'(no context)' if context in (EMPTY, None) else ''}".rstrip(), got == want and all(type(a) is type(b) for a, b in zip(got[1].values(), want[1].values())), f"{got} != {want}")

check("the default is the tile under the mouse, as numbers", d.parse("/spawn wolf", {"cursor": (3, 4)})[1] == {"blueprint": "wolf", "x": 3.0, "y": 4.0})

needs = {
    "/delete": "select something first",
    "/wake": "select something first",
    "/inspect": "select something first",
    "/wake @": "select something first",
    "/spawn wolf": "point at a tile first",
    "/spawn wolf ~": "point at a tile first",
    "/tile stone": "point at a tile first",
    "/tile stone ~": "point at a tile first",
}

for text, wanted in needs.items():
    for context in (EMPTY, None, {}, {"selected": True, "cursor": "x"}, {"selected": "7", "cursor": (1,)}):
        got = message(lambda: d.parse(text, context))
        check(f"{text!r} with no usable context says {wanted!r}", got == wanted, f"{got!r} for {context!r}")

errors = {
    "": "type a command",
    "/": "type a command",
    "   ": "type a command",
    "/nope": "unknown command 'nope'",
    "/nope 1 2": "unknown command",
    "/step x": "not a whole number",
    "/step 1.5": "not a whole number",
    "/step 0": "at least 1",
    "/step 101": "at most 100",
    "/step 500": "at most 100",
    "/step -3": "at least 1",
    "/step 1 2": "too many arguments",
    "/speed": "missing <factor>",
    "/speed fast": "not a number",
    "/speed nan": "not a number",
    "/speed 2": "must be one of 0.25, 1, 4",
    "/speed 1 2": "too many arguments",
    "/pause now": "too many arguments",
    "/catalog all": "too many arguments",
    "/spawn": "missing <blueprint>",
    "/spawn wolf 3": "a point needs two numbers",
    "/spawn wolf 1 2 3": "too many arguments",
    "/spawn wolf a b": "not a number",
    "/spawn wolf 1 b": "not a number",
    "/spawn wolf nan 2": "not a number",
    "/spawn wolf inf 2": "not a number",
    "/spawn wolf 1e9 1": "at most",
    "/spawn bad/name 1 2": "must be a name",
    "/spawn " + "w" * 65 + " 1 2": "must be a name",
    "/delete -1": "at least 0",
    "/delete x": "not a whole number",
    "/delete 3 4": "too many arguments",
    "/delete 99999999999999999999": "at most",
    "/tile": "missing <name>",
    "/tile stone 1": "a point needs two numbers",
    "/help a b": "too many arguments",
    "/wake ~": "not a whole number",
    "/spawn wolf @": "a point needs two numbers",
    "/step @": "not a whole number",
}

for text, wanted in errors.items():
    got = message(lambda: d.parse(text, CONTEXT))
    check(f"{text[:40]!r} gives a readable error containing {wanted!r}", got is not None and wanted in got and not got.startswith("WRONG"), repr(got))

for value in (None, 5, 2.5, b"/pause", ["/pause"], {"a": 1}):
    check(f"parse of {value!r} gives a syntax error", message(lambda: d.parse(value, CONTEXT)) == "type a command, or /help")

check("missing and bad usage errors show the usage", "/spawn <blueprint> [x y]" in message(lambda: d.parse("/spawn", CONTEXT)) and "/step [count]" in message(lambda: d.parse("/step 1 2", CONTEXT)))
check("usage text", [d.usage(name) for name in ("pause", "step", "speed", "spawn", "delete", "tile", "help")] == ["/pause", "/step [count]", "/speed <0.25|1|4>", "/spawn <blueprint> [x y]", "/delete [id]", "/tile <name> [x y]", "/help [command]"], str([d.usage(name) for name in d.names()]))
check("help lines have one line per command", len(d.help_lines()) == len(d.names()) and all(line.startswith("/") for line in d.help_lines()))

random.seed(4)
alphabet = "/@~ 0123456789.-+eE" + "abcxyz_" + "\t\x00é"
words = list(d.DEV_COMMANDS) + ["wolf", "stone", "nan", "inf", "-0", "1e999", "9" * 5000]
bad = []

for _ in range(4000):
    text = random.choice(["/", ""]) + " ".join(random.choice(words) if random.random() < 0.5 else "".join(random.choice(alphabet) for _ in range(random.randint(0, 6))) for _ in range(random.randint(0, 6)))
    context = random.choice([CONTEXT, EMPTY, None, {"selected": 2**70, "cursor": (float("nan"), 1)}, {"cursor": ("a", "b")}])

    try:
        what, args = d.parse(text, context)
        assert what in d.DEV_COMMANDS and plain(args) and d.validate(what, args) == args, (text, what, args)
    except d.DevSyntaxError:
        pass
    except Exception as problem:
        bad.append((text, repr(problem)))

check("random text only ever parses cleanly or gives a DevSyntaxError", not bad, str(bad[:3]))

check("validate: step count 0, 101, -1 are rejected", all(message(lambda c=c: d.validate("step", {"count": c})) for c in (0, 101, -1, 10**6)))
check("validate: step count 1 and 100 are accepted", d.validate("step", {"count": 1}) == {"count": 1} and d.validate("step", {"count": 100}) == {"count": 100})
check("validate: step with no count gets 1", d.validate("step", {}) == {"count": 1})
check("validate: step count must be a whole number", all("whole number" in (message(lambda c=c: d.validate("step", {"count": c})) or "") for c in (2.5, "3", True, None, [1])))
check("validate: speed not in choices is rejected", all("must be one of" in (message(lambda s=s: d.validate("speed", {"factor": s})) or "") for s in (2, 0.5, 0, 100.0, -1)))
check("validate: speed in choices is accepted, as a float", [d.validate("speed", {"factor": s}) for s in (0.25, 1, 4.0)] == [{"factor": 0.25}, {"factor": 1.0}, {"factor": 4.0}] and type(d.validate("speed", {"factor": 1})["factor"]) is float)
check("validate: speed must be a number", all("number" in (message(lambda s=s: d.validate("speed", {"factor": s})) or "") for s in ("1", True, None, float("nan"), float("inf"), 10**400)))
check("validate: speed is required", "missing argument 'factor'" == message(lambda: d.validate("speed", {})))
check("validate: unknown command", message(lambda: d.validate("nope", {})) == "unknown dev command" and message(lambda: d.validate(None, {})) == "unknown dev command" and message(lambda: d.validate(["step"], {})) == "unknown dev command")
check("validate: args must be a map", all(message(lambda a=a: d.validate("step", a)) == "args must be a map" for a in (None, 5, "x", [], [1], ())))
check("validate: unexpected arguments are rejected", all("unexpected argument" in (message(lambda a=a: d.validate("pause", a)) or "") for a in ({"x": 1}, {1: 2}, {None: 1}, {"a" * 500: 1})))
check("validate: an id must be given and must be a whole number in range", message(lambda: d.validate("delete", {})) == "missing argument 'id'" and all(message(lambda i=i: d.validate("delete", {"id": i})) for i in (-1, 1.5, "3", True, 10**10)))
check("validate: a point needs both x and y", message(lambda: d.validate("spawn", {"blueprint": "wolf"})) == "missing argument 'at'" and message(lambda: d.validate("spawn", {"blueprint": "wolf", "x": 1.0})) == "missing argument 'y'")
check("validate: a point's numbers are range checked and made floats", d.validate("spawn", {"blueprint": "wolf", "x": 1, "y": 2}) == {"blueprint": "wolf", "x": 1.0, "y": 2.0} and message(lambda: d.validate("spawn", {"blueprint": "wolf", "x": 1e12, "y": 2})) and message(lambda: d.validate("spawn", {"blueprint": "wolf", "x": float("nan"), "y": 2})))
check("validate: names are checked", all(message(lambda n=n: d.validate("spawn", {"blueprint": n, "x": 1, "y": 1})) for n in ("", "a b", "a/b", "x" * 65, 5, None, "é", "a\n")))
check("validate: help takes an optional name", d.validate("help", {}) == {} and d.validate("help", {"command": "spawn"}) == {"command": "spawn"})

original = {"count": 3}
d.validate("step", original)
check("validate does not change what it is given", original == {"count": 3})

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")