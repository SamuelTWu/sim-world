import msgpack

from src.simworld.shared import protocol as p

checks = 0


def roundtrip(message, accept=None):
    return p.decode(p.encode(message), accept)


def expect_error(label, call):
    global checks
    try:
        call()
    except p.ProtocolError:
        checks += 1
        return
    raise AssertionError(f"{label}: expected ProtocolError")


samples = [
    (p.join("sam"), p.CLIENT_TYPES),
    (p.view([0.0, 0.0, 1280, 720.5]), p.CLIENT_TYPES),
    (p.welcome(1, 12345, {"width": 200, "height": 200, "tag_modifiers": {"all": {"scale": 1.3}}}, "ab" * 32, 0, 20, "cd" * 16), p.SERVER_TYPES),
    (p.welcome(1, 12345, {"width": 200}, "ab" * 32, 40, 20, "cd" * 16, resumed=True), p.SERVER_TYPES),
    (p.join("sam", 3, "cd" * 16), p.CLIENT_TYPES),
    (p.command(1, "move", {"ids": [1, 2], "target": [320.0, 480.0]}), p.CLIENT_TYPES),
    (p.tick_update(5, enter=[{"id": 1, "x": 1.5}], update=[{"id": 2, "x": 3.0}], leave=[3], events=[{"kind": "fired"}], ack=1), p.SERVER_TYPES),
    (p.tick_update(6), p.SERVER_TYPES),
    (p.tick_update(6, events=[p.transient_event("fired", "arrow", (100.0, 200.0), (400.5, 200.0))]), p.SERVER_TYPES),
    (p.world_delta(5, [[10, 10, "stone"], [11, 10, "stone"]]), p.SERVER_TYPES),
    (p.entity_info(7, {"id": 7, "stats": {"health": 1.0}}, seq=3), p.SERVER_TYPES),
    (p.command_result(4, [1, 2], [[3, "unavailable"]]), p.SERVER_TYPES),
    (p.command_result(5), p.SERVER_TYPES),
    (p.order_failed(1, "move", "it could not get there"), p.SERVER_TYPES),
    (p.error(p.COMMAND_REJECTED, "not enough currency", seq=1), p.SERVER_TYPES),
    (p.dev(1, "help"), p.CLIENT_TYPES),
    (p.dev(2, "pause", {"on": True}), p.CLIENT_TYPES),
    (p.dev_result(1, True, "ok"), p.SERVER_TYPES),
    (p.dev_result(2, True, "listed", {"commands": ["help"]}), p.SERVER_TYPES),
    (p.dev_result(3, False, "not available"), p.SERVER_TYPES),
]

for message, accept in samples:
    assert roundtrip(message, accept) == message, message["type"]
    checks += 1

assert "player_id" not in p.join("sam") and "token" not in p.join("sam") and "resumed" not in p.welcome(1, 1, {}, "x", 0, 20, "t")
assert p.join("sam", 3)["token"] == ""
assert "enter" not in p.tick_update(6) and "ack" not in p.tick_update(6)
assert "data" not in p.dev_result(1, True, "x") and p.dev(1, "help")["args"] == {}

expect_error("set in args", lambda: p.encode(p.command(1, "x", {"tags": {"a"}})))
expect_error("not a dict", lambda: p.encode(["join"]))
expect_error("unknown type", lambda: p.encode({"type": "nope"}))
expect_error("missing field", lambda: p.encode({"type": "join", "name": "sam"}))
expect_error("wrong type", lambda: p.encode({"type": "join", "name": 5, "protocol": 1}))
expect_error("bool as int", lambda: p.encode({"type": "join", "name": "sam", "protocol": True}))
expect_error("extra field", lambda: p.encode({"type": "join", "name": "sam", "protocol": 1, "admin": True}))
expect_error("token must be text", lambda: p.encode({"type": "join", "name": "sam", "protocol": 7, "player_id": 1, "token": 5}))
expect_error("welcome without token", lambda: p.encode({"type": "welcome", "player_id": 1, "seed": 1, "settings": {}, "checksum": "x", "tick": 0, "tick_rate": 20}))
expect_error("client sends welcome", lambda: p.decode(p.encode(samples[2][0]), p.CLIENT_TYPES))
expect_error("server sends command", lambda: p.decode(p.encode(p.command(1, "x")), p.SERVER_TYPES))
expect_error("text frame", lambda: p.decode('{"type": "join"}'))
expect_error("garbage bytes", lambda: p.decode(b"\xc1\xc1\xc1"))
expect_error("truncated", lambda: p.decode(p.encode(samples[2][0])[:10]))
expect_error("trailing bytes", lambda: p.decode(p.encode(samples[0][0]) + b"\x00"))
expect_error("list at top level", lambda: p.decode(msgpack.packb([1, 2, 3])))
expect_error("oversized", lambda: p.decode(b"\x00" * (p.MAX_MESSAGE_BYTES + 1)))
expect_error("dev args not a map", lambda: p.encode({"type": "dev", "seq": 1, "what": "help", "args": [1]}))
expect_error("dev extra field", lambda: p.encode({"type": "dev", "seq": 1, "what": "help", "args": {}, "admin": True}))
expect_error("dev_result ok must be bool", lambda: p.encode({"type": "dev_result", "seq": 1, "ok": 1, "text": "x"}))
expect_error("client sends dev_result", lambda: p.decode(p.encode(p.dev_result(1, True, "x")), p.CLIENT_TYPES))
expect_error("server sends dev", lambda: p.decode(p.encode(p.dev(1, "help")), p.SERVER_TYPES))

print(f"protocol OK ({checks} checks, msgpack {msgpack.version})")