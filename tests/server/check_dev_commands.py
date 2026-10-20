import contextlib
import io
import sys
from types import SimpleNamespace

from src.simworld.server import dev_commands as dev
from src.simworld.server.dev_time import init_time
from src.simworld.shared import dev_commands as table

failures = []
CONTEXT = {"selected": 3, "cursor": (4.0, 5.0)}
SAMPLE_ARGS = {name: table.parse(command.example, CONTEXT)[1] for name, command in table.DEV_COMMANDS.items()}


def check(text, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + text + ("" if condition else f" {detail}"))

    if not condition:
        failures.append(text)


class Counters:
    def __init__(self):
        self.values = {}

    def add(self, name, amount=1):
        self.values[name] = self.values.get(name, 0) + amount


def fake_server(sandbox, paused=False):
    server = SimpleNamespace(sim=SimpleNamespace(sandbox=sandbox, tick=0, systems=SimpleNamespace(counters=Counters())))
    init_time(server)
    server.paused = paused
    return server


def quiet(call):
    with contextlib.redirect_stdout(io.StringIO()):
        return call()


check("every handler has a command in the table", set(dev.DEV_HANDLERS) <= set(table.DEV_COMMANDS), f"{sorted(set(dev.DEV_HANDLERS) - set(table.DEV_COMMANDS))}")
check("help has a handler", "help" in dev.DEV_HANDLERS)

normal, sandbox = fake_server(False), fake_server(True)

for name in sorted(table.DEV_COMMANDS):
    refused = dev.run_dev(normal, None, name, SAMPLE_ARGS[name])
    check(f"{name}: refused on a normal server", refused == dev.DevResult(False, "not available"), str(refused))

for name in sorted(dev.DEV_HANDLERS):
    accepted = dev.run_dev(fake_server(True, paused=True), None, name, SAMPLE_ARGS[name])
    check(f"{name}: accepted on a sandbox server", accepted.ok, str(accepted))

for name in sorted(set(table.DEV_COMMANDS) - set(dev.DEV_HANDLERS)):
    waiting = dev.run_dev(sandbox, None, name, SAMPLE_ARGS[name])
    check(f"{name}: valid but not implemented yet says so", waiting == dev.DevResult(False, "not implemented yet"), str(waiting))

check("each refusal is counted", normal.sim.systems.counters.values.get("dev_refused") == len(table.DEV_COMMANDS) and "dev_refused" not in sandbox.sim.systems.counters.values, str(normal.sim.systems.counters.values))

for flag in (None, 0, 1, "yes", False):
    odd = fake_server(flag)
    check(f"sandbox={flag!r} counts as a normal server", dev.run_dev(odd, None, "help", {}).text == "not available")

check("a normal server refuses even a bad name or bad args", all(dev.run_dev(normal, None, what, args).text == "not available" for what in (None, "nope", 5) for args in (None, 5, {"x": 1})))

whats = [None, 5, 2.5, True, "", "nope", [], {}, ("help",), "help\x00", "x" * 10000, b"help", ["help"], "HELP", " help"]
bad_args = [None, 5, "x", [], [1], True, 3.5, (), {"x": 1}, {1: 2}, {"": 1}, {None: 1}, {"help": 1}, {"a" * 5000: 1}]

for server_name, server in (("normal", normal), ("sandbox", sandbox)):
    raised = []

    for what in whats:
        for args in bad_args + [{}]:
            try:
                result = dev.run_dev(server, None, what, args)
                assert isinstance(result, dev.DevResult) and isinstance(result.ok, bool) and isinstance(result.text, str)

                if server is sandbox:
                    assert result.ok is False, (what, args, result)
            except Exception as problem:
                raised.append((what, args, repr(problem)))

    check(f"bad names and args never raise or succeed ({server_name})", not raised, str(raised[:3]))

for name in table.DEV_COMMANDS:
    for args in (None, 5, "x", [], [1], True):
        result = dev.run_dev(sandbox, None, name, args)
        check(f"{name}: non-dict args {args!r} refused", result.ok is False and result.text == "args must be a map", str(result))

check("an unknown name on a sandbox server is named as such", dev.run_dev(sandbox, None, "nope", {}).text == "unknown dev command")
check("an unexpected argument is refused", "unexpected" in dev.run_dev(sandbox, None, "help", {"x": 1}).text)
check("help lists the commands", dev.run_dev(sandbox, None, "help", {}).data["commands"] == table.names())
check("help <command> shows its usage", dev.run_dev(sandbox, None, "help", {"command": "spawn"}).text.startswith("/spawn <blueprint> [x y]"))
check("help <unknown> says so", dev.run_dev(sandbox, None, "help", {"command": "zzz"}).ok is False)

table.DEV_COMMANDS["zz_test"] = table.Command("test only", (table.Arg("n", "int", low=1, high=5),), "/zz_test 1")
seen = []


def boom(server, client, args):
    seen.append(args)
    raise RuntimeError("kaboom")


dev.DEV_HANDLERS["zz_test"] = boom

try:
    check("an argument out of range is refused before the handler runs", dev.run_dev(sandbox, None, "zz_test", {"n": 9}).ok is False and not seen)
    check("a missing argument is refused", "missing" in dev.run_dev(sandbox, None, "zz_test", {}).text and not seen)
    check("a bool is not a whole number", dev.run_dev(sandbox, None, "zz_test", {"n": True}).ok is False and not seen)
    result = quiet(lambda: dev.run_dev(sandbox, None, "zz_test", {"n": 3}))
    check("a handler that raises becomes ok False 'dev command failed'", result == dev.DevResult(False, "dev command failed") and seen == [{"n": 3}], str(result))
    printed = io.StringIO()

    with contextlib.redirect_stdout(printed):
        dev.run_dev(sandbox, None, "zz_test", {"n": 3})

    check("the failure is printed", "kaboom" in printed.getvalue())

    for value in (5, object(), (True, "x"), dev.DevResult("yes"), dev.DevResult(True, 5), dev.DevResult(True, "x", [1])):
        dev.DEV_HANDLERS["zz_test"] = lambda server, client, args, value=value: value
        result = quiet(lambda: dev.run_dev(sandbox, None, "zz_test", {"n": 3}))
        check(f"a handler returning {type(value).__name__} becomes 'dev command failed'", result == dev.DevResult(False, "dev command failed"), str(result))

    dev.DEV_HANDLERS["zz_test"] = lambda server, client, args: "done"
    check("a handler may return text", dev.run_dev(sandbox, None, "zz_test", {"n": 3}) == dev.DevResult(True, "done"))
    dev.DEV_HANDLERS["zz_test"] = lambda server, client, args: None
    check("a handler may return nothing", dev.run_dev(sandbox, None, "zz_test", {"n": 3}) == dev.DevResult(True, ""))
    dev.DEV_HANDLERS["zz_test"] = lambda server, client, args: dev.DevResult(True, "x" * 5000, {})
    result = dev.run_dev(sandbox, None, "zz_test", {"n": 3})
    check("text is capped and empty data is dropped", len(result.text) == dev.MAX_TEXT and result.data is None)
finally:
    del table.DEV_COMMANDS["zz_test"]
    del dev.DEV_HANDLERS["zz_test"]

try:
    dev.dev_command("not_in_the_table")(lambda *a: None)
    check("registering a name missing from the table is refused", False)
except ValueError:
    check("registering a name missing from the table is refused", True)

try:
    dev.dev_command("help")(lambda *a: None)
    check("registering a second handler is refused", False)
except ValueError:
    check("registering a second handler is refused", True)

check("a counter-less sim does not break the refusal", dev.run_dev(SimpleNamespace(sim=SimpleNamespace(sandbox=False)), None, "help", {}).text == "not available")
check("a sim without the sandbox attribute is refused", dev.run_dev(SimpleNamespace(sim=SimpleNamespace()), None, "help", {}).text == "not available")

from src.simworld.server import server as server_module
from src.simworld.server.server import Client, Server
from src.simworld.shared import protocol as proto


def real_server(flag):
    server = Server.__new__(Server)
    server.sim = SimpleNamespace(sandbox=flag, systems=SimpleNamespace(counters=Counters()))
    server.metrics = SimpleNamespace(sent=lambda *args, **kwargs: None)
    return server


def ask(server, message, player_id=1):
    client = Client(websocket=None, player_id=player_id, name="t")
    client.pending = 1
    server.handle(client, message)
    items = [client.outbox.get_nowait() for _ in range(client.outbox.qsize())]
    return client, [proto.decode(item, proto.SERVER_TYPES) for item in items if isinstance(item, bytes)]


original = server_module.commands.execute


def forbidden(*args, **kwargs):
    raise AssertionError("a dev message must not go through commands.execute")


server_module.commands.execute = forbidden

try:
    server = real_server(False)
    _, replies = ask(server, proto.dev(7, "help", {}))
    check("Server.handle answers a dev message with dev_result and the same seq", len(replies) == 1 and replies[0]["type"] == proto.DEV_RESULT and replies[0]["seq"] == 7, str(replies))
    check("a normal server says 'not available'", replies[0]["ok"] is False and replies[0]["text"] == "not available", str(replies))
    check("and counts it", server.sim.systems.counters.values.get("dev_refused") == 1)

    server = real_server(True)
    _, replies = ask(server, proto.dev(8, "help", {}))
    check("a sandbox server accepts it", replies[0]["ok"] is True and "help" in replies[0]["data"]["commands"], str(replies))
    _, replies = ask(server, proto.dev(9, "nope", {}))
    check("an unknown command gets ok False, not a disconnect", replies[0]["ok"] is False and replies[0]["text"] == "unknown dev command" and replies[0]["seq"] == 9, str(replies))
    _, replies = ask(server, proto.dev(10, "help", {"x": 1}))
    check("bad args get ok False", replies[0]["ok"] is False, str(replies))

    client, replies = ask(server, proto.dev(11, "help", {}), player_id=None)
    check("a dev message before join is refused like any other", replies[0]["type"] == proto.ERROR and replies[0]["code"] == proto.NOT_JOINED, str(replies))
finally:
    server_module.commands.execute = original

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)

print("OK")