import msgpack

from ..server.server import protocol as p

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
    (p.welcome(1, 12345, {"width": 200, "height": 200, "tag_modifiers": {"all": {"scale": 1.3}}}, "ab" * 32, 0, 20), p.SERVER_TYPES),
    (p.command(1, "move", {"ids": [1, 2], "target": [320.0, 480.0]}), p.CLIENT_TYPES),
    (p.tick_update(5, enter=[{"id": 1, "x": 1.5}], update=[{"id": 2, "x": 3.0}], leave=[3], events=[{"kind": "fired"}], ack=1), p.SERVER_TYPES),
    (p.tick_update(6), p.SERVER_TYPES),
    (p.world_delta(5, [[10, 10, "stone"], [11, 10, "stone"]]), p.SERVER_TYPES),
    (p.error(p.COMMAND_REJECTED, "not enough currency", seq=1), p.SERVER_TYPES),
]

for message, accept in samples:
    assert roundtrip(message, accept) == message, message["type"]
    checks += 1

assert "enter" not in p.tick_update(6) and "ack" not in p.tick_update(6)

expect_error("set in args", lambda: p.encode(p.command(1, "x", {"tags": {"a"}})))
expect_error("not a dict", lambda: p.encode(["join"]))
expect_error("unknown type", lambda: p.encode({"type": "nope"}))
expect_error("missing field", lambda: p.encode({"type": "join", "name": "sam"}))
expect_error("wrong type", lambda: p.encode({"type": "join", "name": 5, "protocol": 1}))
expect_error("bool as int", lambda: p.encode({"type": "join", "name": "sam", "protocol": True}))
expect_error("extra field", lambda: p.encode({"type": "join", "name": "sam", "protocol": 1, "admin": True}))
expect_error("client sends welcome", lambda: p.decode(p.encode(samples[1][0]), p.CLIENT_TYPES))
expect_error("server sends command", lambda: p.decode(p.encode(samples[2][0]), p.SERVER_TYPES))
expect_error("text frame", lambda: p.decode('{"type": "join"}'))
expect_error("garbage bytes", lambda: p.decode(b"\xc1\xc1\xc1"))
expect_error("truncated", lambda: p.decode(p.encode(samples[1][0])[:10]))
expect_error("trailing bytes", lambda: p.decode(p.encode(samples[0][0]) + b"\x00"))
expect_error("list at top level", lambda: p.decode(msgpack.packb([1, 2, 3])))
expect_error("oversized", lambda: p.decode(b"\x00" * (p.MAX_MESSAGE_BYTES + 1)))

print(f"protocol OK ({checks} checks, msgpack {msgpack.version})")