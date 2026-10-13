"""Wire protocol shared by the server and the client.

Every message is a small dict with a "type" field, packed with msgpack and sent as one
binary WebSocket frame. This file must not import anything from game/.

Rules:
- Use msgpack 1.x. Map keys must be strings (use lists, not int-keyed dicts).
- Tuples arrive as lists, sets cannot be sent (send sorted lists), floats are 64-bit.
- Optional fields are left out when empty, so read them with .get(key, default).
- Pixel positions are small ints (POSITION_SCALE). Bump PROTOCOL_VERSION whenever a message changes shape.

Client -> server: join, command, view
Server -> client: welcome, tick_update, world_delta, entity_info, command_result, order_failed, error
"""
import msgpack
from msgpack.exceptions import UnpackException

PROTOCOL_VERSION = 6
MAX_MESSAGE_BYTES = 1_000_000

# Pixel positions travel as whole numbers of 1/POSITION_SCALE world units ("x": 4400 means 1100.0). A 64-bit float costs 9 bytes
# in msgpack and a number up to 65535 only 3, and it never has a long tail of decimals. 4 means a quarter of a world unit
# (1/128 of a tile), far finer than anything visible, and keeps a 500-tile world (16000 units = 64000) inside 3 bytes.
POSITION_SCALE = 4


def to_wire(value):
    """A position in world units as the small integer that is sent."""
    return round(value * POSITION_SCALE)


def from_wire(value):
    """The world position a received integer stands for."""
    return value / POSITION_SCALE

JOIN = "join"
WELCOME = "welcome"
COMMAND = "command"
VIEW = "view"
TICK_UPDATE = "tick_update"
WORLD_DELTA = "world_delta"
ENTITY_INFO = "entity_info"
COMMAND_RESULT = "command_result"
ORDER_FAILED = "order_failed"
ERROR = "error"

BAD_MESSAGE = "bad_message"
BAD_PROTOCOL = "bad_protocol"
NOT_JOINED = "not_joined"
SERVER_FULL = "server_full"
COMMAND_REJECTED = "command_rejected"

CLIENT_TYPES = frozenset({JOIN, COMMAND, VIEW})
SERVER_TYPES = frozenset({WELCOME, TICK_UPDATE, WORLD_DELTA, ENTITY_INFO, COMMAND_RESULT, ORDER_FAILED, ERROR})

# type -> (required fields, optional fields), each as {field: python type}
SCHEMAS = {
    JOIN: ({"name": str, "protocol": int}, {}),
    WELCOME: ({"player_id": int, "seed": int, "settings": dict, "checksum": str, "tick": int, "tick_rate": int}, {}),
    COMMAND: ({"seq": int, "name": str, "args": dict}, {}),
    VIEW: ({"rect": list}, {}),
    TICK_UPDATE: ({"tick": int}, {"enter": list, "update": list, "leave": list, "events": list, "ack": int}),
    WORLD_DELTA: ({"tick": int, "tiles": list}, {}),
    ENTITY_INFO: ({"id": int, "info": dict}, {"seq": int}),
    COMMAND_RESULT: ({"seq": int}, {"applied": list, "ignored": list}),
    ORDER_FAILED: ({"id": int, "kind": str, "reason": str}, {}),
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


def transient_event(kind, type, start, end):
    """One event for tick_update's `events`: something that was SEEN but is not a pixel (a shot, an impact), drawn by the client on its own.

    `start` and `end` are (x, y) in world units, sent as small ints like pixel positions. Pixel ids are never in it, so it cannot leak a hidden pixel.
    """
    return {"kind": kind, "type": type, "from": [to_wire(start[0]), to_wire(start[1])], "to": [to_wire(end[0]), to_wire(end[1])]}


def view(rect):
    """The part of the world the player's camera shows, [x0, y0, x1, y1] in world units. The server also sends pixels in it (interest.py)."""
    return {"type": VIEW, "rect": list(rect)}


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


def entity_info(entity_id, info, seq=None):
    """One pixel's attributes, sent to its owner in answer to `inspect` or `edit_property` (seq is that command's)."""
    result = {"type": ENTITY_INFO, "id": entity_id, "info": info}

    if seq is not None:
        result["seq"] = seq

    return result


def command_result(seq, applied=None, ignored=None):
    """The command with this seq was accepted. `applied` lists what it acted on (pixel ids, or a new blueprint id);
    `ignored` is [[pixel id, reason], ...] for pixels it skipped. A refused command gets an `error` with the same seq instead."""
    message = {"type": COMMAND_RESULT, "seq": seq}

    if applied:
        message["applied"] = list(applied)

    if ignored:
        message["ignored"] = [list(pair) for pair in ignored]

    return message


def order_failed(entity_id, kind, reason):
    """A pixel the player ordered gave up (or the order could not start) after the command was accepted."""
    return {"type": ORDER_FAILED, "id": entity_id, "kind": kind, "reason": reason}


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