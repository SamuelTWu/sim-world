"""Wire protocol shared by the server and the client.

Every message is a small dict with a "type" field, packed with msgpack and sent as one
binary WebSocket frame. This file must not import anything from game/.

Rules:
- Use msgpack 1.x. Map keys must be strings (use lists, not int-keyed dicts).
- Tuples arrive as lists, sets cannot be sent (send sorted lists), floats are 64-bit.
- Optional fields are left out when empty, so read them with .get(key, default).
- Bump PROTOCOL_VERSION whenever a message changes shape.

Client -> server: join, command
Server -> client: welcome, tick_update, world_delta, error
"""
import msgpack
from msgpack.exceptions import UnpackException

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1_000_000

JOIN = "join"
WELCOME = "welcome"
COMMAND = "command"
TICK_UPDATE = "tick_update"
WORLD_DELTA = "world_delta"
ERROR = "error"

BAD_MESSAGE = "bad_message"
BAD_PROTOCOL = "bad_protocol"
NOT_JOINED = "not_joined"
SERVER_FULL = "server_full"
COMMAND_REJECTED = "command_rejected"

CLIENT_TYPES = frozenset({JOIN, COMMAND})
SERVER_TYPES = frozenset({WELCOME, TICK_UPDATE, WORLD_DELTA, ERROR})

# type -> (required fields, optional fields), each as {field: python type}
SCHEMAS = {
    JOIN: ({"name": str, "protocol": int}, {}),
    WELCOME: ({"player_id": int, "seed": int, "settings": dict, "checksum": str, "tick": int, "tick_rate": int}, {}),
    COMMAND: ({"seq": int, "name": str, "args": dict}, {}),
    TICK_UPDATE: ({"tick": int}, {"enter": list, "update": list, "leave": list, "events": list, "ack": int}),
    WORLD_DELTA: ({"tick": int, "tiles": list}, {}),
    ERROR: ({"code": str, "message": str}, {"seq": int}),
}


class ProtocolError(Exception):
    """A message is malformed, the wrong type for its sender, or too large."""


def join(name):
    return {"type": JOIN, "name": name, "protocol": PROTOCOL_VERSION}


def welcome(player_id, seed, settings, checksum, tick, tick_rate):
    return {"type": WELCOME, "player_id": player_id, "seed": seed, "settings": settings, "checksum": checksum, "tick": tick, "tick_rate": tick_rate}


def command(seq, name, args=None):
    return {"type": COMMAND, "seq": seq, "name": name, "args": args or {}}


def tick_update(tick, enter=None, update=None, leave=None, events=None, ack=None):
    message = {"type": TICK_UPDATE, "tick": tick}

    for key, value in (("enter", enter), ("update", update), ("leave", leave), ("events", events)):
        if value:
            message[key] = list(value)

    if ack is not None:
        message["ack"] = ack

    return message


def world_delta(tick, tiles):
    return {"type": WORLD_DELTA, "tick": tick, "tiles": list(tiles)}


def error(code, message, seq=None):
    result = {"type": ERROR, "code": code, "message": message}

    if seq is not None:
        result["seq"] = seq

    return result


def check_type(kind, key, value, expected):
    ok = isinstance(value, int) and not isinstance(value, bool) if expected is int else isinstance(value, expected)

    if not ok:
        raise ProtocolError(f"{kind}.{key} must be {expected.__name__}, got {type(value).__name__}")


def validate(message):
    """Check the structure of a message (not what is inside lists and dicts). Returns it unchanged."""
    if not isinstance(message, dict):
        raise ProtocolError("a message must be a map")

    kind = message.get("type")

    if not isinstance(kind, str) or kind not in SCHEMAS:
        raise ProtocolError(f"unknown message type {kind!r}")

    required, optional = SCHEMAS[kind]

    for key, expected in required.items():
        if key not in message:
            raise ProtocolError(f"{kind} is missing '{key}'")

    for key, value in message.items():
        if key == "type":
            continue

        expected = required.get(key) or optional.get(key)

        if expected is None:
            raise ProtocolError(f"{kind} has unexpected field '{key}'")

        check_type(kind, key, value, expected)

    return message


def encode(message):
    """Validate a message and pack it into bytes for one binary frame."""
    validate(message)

    try:
        data = msgpack.packb(message, use_bin_type=True)
    except (TypeError, ValueError, OverflowError) as error_:
        raise ProtocolError(f"cannot encode {message['type']}: {error_}") from error_

    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"{message['type']} is {len(data)} bytes (limit {MAX_MESSAGE_BYTES})")

    return data


def decode(data, accept=None):
    """
    Unpack and validate bytes from the network.

    Pass accept=CLIENT_TYPES on the server and accept=SERVER_TYPES on the client so a peer
    cannot send messages that only the other side is allowed to send.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ProtocolError("messages must be binary frames")

    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"message is {len(data)} bytes (limit {MAX_MESSAGE_BYTES})")

    try:
        message = msgpack.unpackb(data, raw=False, strict_map_key=True)
    except (UnpackException, ValueError, TypeError, RecursionError) as error_:
        raise ProtocolError("could not decode message") from error_

    validate(message)

    if accept is not None and message["type"] not in accept:
        raise ProtocolError(f"unexpected message type '{message['type']}'")

    return message