"""eBUS messages of the Ariston zone room sensor (see docs/room-thermostat.md)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

BROADCAST = 0xFE
BOILER = 0x37
GATEWAY = 0x7F

ROOM_TEMPERATURE_ID = bytes.fromhex("7118")
ZONE_TARGET_ID = bytes.fromhex("6996")
COMFORT_ID = bytes.fromhex("6271")
ZONE_MODE_ID = bytes.fromhex("c679")
FROST_ID = bytes.fromhex("6426")
HEAT_REQUEST_ID = bytes.fromhex("0191")

# Value width by the second byte of an id; the first byte changes with the zone.
_RECORD_WIDTHS = {0x18: 2, 0x26: 2, 0x47: 2, 0x71: 2, 0x79: 1, 0x91: 1, 0x94: 1, 0x96: 2}

_BUS_RESET = (0x20, 0x34)
_SERIAL = (0x20, 0x31)
_QUERY = (0x20, 0x00)
_ANSWER = (0x20, 0x0F)
_CAST = (0x20, 0x10)
_SETTING_QUERY = (0x20, 0x01)
_SETTING_ANSWER = (0x20, 0x0E)
_WRITE = (0x20, 0x20)
_ERROR = (0x20, 0x04)
_ADDRESS_CAST = (0x20, 0x3B)

# Error 411, room sensor missing: index 69, flags 03 = active for zone 1 (01 = cleared).
_ROOM_SENSOR_MISSING = bytes.fromhex("6903")

# Trailing bytes of the Cube's 2031 frame; not decoded, sent as the Cube sends them.
_SERIAL_TRAILER = bytes.fromhex("020009")


@dataclass(frozen=True)
class Frame:
    """A master part of an eBUS message: source, destination, command and data."""

    source: int
    destination: int
    command: tuple[int, int]
    data: bytes

    @classmethod
    def parse(cls, text: str) -> Frame:
        """Parse QQZZPBSBNN[DD]* as ebusd prints it (no CRC)."""
        raw = bytes.fromhex(text)
        if len(raw) < 5 or raw[4] != len(raw) - 5:
            raise ValueError(f"invalid master part {text}")
        return cls(raw[0], raw[1], (raw[2], raw[3]), raw[5:])


@dataclass(frozen=True)
class StreamLine:
    """A line from ebusd's direct stream mode."""

    timestamp: float
    kind: str  # r received, s sent, a answered, e send failed
    frame: Frame
    error: str | None = None

    @classmethod
    def parse(cls, line: str) -> StreamLine | None:
        """Parse "SECONDS.MILLIS KIND HEX[ SLAVE| ERR: ...]", or None for any other line."""
        parts = line.split(" ", 3)
        if len(parts) < 3 or parts[1] not in ("r", "s", "a", "e"):
            return None
        try:
            timestamp = float(parts[0])
            frame = Frame.parse(parts[2])
        except ValueError:
            return None
        error = parts[3] if parts[1] == "e" and len(parts) > 3 else None
        return cls(timestamp, parts[1], frame, error)


# Each nibble of an eBUS master address is one of these.
_MASTER_NIBBLES = (0x0, 0x1, 0x3, 0x7, 0xF)


def master_of(slave: int) -> int:
    """The master address an eBUS device uses with its slave address."""
    return (slave - 5) & 0xFF


def is_slave_with_master(slave: int) -> bool:
    """Whether the address is a slave address whose master address is valid on eBUS."""
    master = master_of(slave)
    return master >> 4 in _MASTER_NIBBLES and master & 0xF in _MASTER_NIBBLES


def encode_temperature(value: float) -> bytes:
    return round(value * 10).to_bytes(2, "little", signed=True)


def decode_temperature(raw: bytes) -> float:
    return int.from_bytes(raw, "little", signed=True) / 10


def _records(data: bytes, count: int, flag: bool) -> Iterator[tuple[bytes, tuple[bytes, ...]]]:
    """Each record's id and its values, of the id's width, optionally followed by a flag byte.

    Stops at an id of unknown width, since the records after it cannot be found.
    """
    pos = 0
    while pos + 2 <= len(data) and (width := _RECORD_WIDTHS.get(data[pos + 1])) is not None:
        start = pos + 2
        end = start + count * width
        if end + flag > len(data):
            return
        yield data[pos:start], tuple(data[i : i + width] for i in range(start, end, width))
        pos = end + flag


def boiler_values(frame: Frame) -> dict[bytes, tuple[bytes, ...]]:
    """By id, the values the boiler casts or answers to anyone: (value,) or, for a 2001 query, (value, min, max)."""
    if frame.source != BOILER or frame.destination != BROADCAST:
        return {}
    if frame.command == _ANSWER:
        values = dict(_records(frame.data, 1, True))
        # Seconds after a bus enumeration it answered 0.0 for the zone target, then the real value: casts only.
        values.pop(ZONE_TARGET_ID, None)
        return values
    if frame.command == _CAST:
        return dict(_records(frame.data, 1, True))
    if frame.command == _WRITE:
        return dict(_records(frame.data, 1, False))
    if frame.command == _SETTING_ANSWER:
        return dict(_records(frame.data, 3, False))
    return {}


def _broadcast(command: tuple[int, int], data: bytes) -> str:
    """Hex for ebusd to send from its own address: ZZPBSBNN[DD]*."""
    return bytes((BROADCAST, *command, len(data))).hex() + data.hex()


def bus_reset_request() -> str:
    return _broadcast(_BUS_RESET, b"")


def serial(serial_number: str, slave: int) -> str:
    raw = serial_number.encode("ascii")
    if len(raw) != 12:
        raise ValueError("the serial number has 12 characters")
    return _broadcast(_SERIAL, raw + bytes((slave,)) + _SERIAL_TRAILER)


def address_cast(slave: int) -> str:
    return _broadcast(_ADDRESS_CAST, bytes((slave,)))


def value_query(value_id: bytes) -> str:
    return _broadcast(_QUERY, value_id)


def setting_query(setting_id: bytes) -> str:
    """Asks the boiler for a setting with its limits, as the Cube does."""
    return _broadcast(_SETTING_QUERY, setting_id)


def write(setting_id: bytes, value: bytes) -> str:
    return _broadcast(_WRITE, setting_id + value)


def room_temperature_answer(value: float) -> str:
    return _broadcast(_ANSWER, ROOM_TEMPERATURE_ID + encode_temperature(value) + b"\x00")


def room_temperature_cast(value: float) -> str:
    return _broadcast(_CAST, ROOM_TEMPERATURE_ID + encode_temperature(value) + b"\x00")


def is_bus_reset(frame: Frame) -> bool:
    """A bus reset from the boiler or the gateway, after which every device sends its serial again."""
    return frame.destination == BROADCAST and frame.command == _BUS_RESET and frame.source in (BOILER, GATEWAY)


def is_room_temperature_query(frame: Frame) -> bool:
    """The boiler or the gateway asking for the zone 1 room temperature."""
    return (
        frame.destination == BROADCAST
        and frame.command == _QUERY
        and frame.source in (BOILER, GATEWAY)
        and len(frame.data) % 2 == 0
        # The gateway also asks for several zones at once (7118 7218 7318); each sensor answers its own.
        and ROOM_TEMPERATURE_ID in (frame.data[i : i + 2] for i in range(0, len(frame.data), 2))
    )


def is_room_temperature_answer(frame: Frame) -> bool:
    return frame.destination == BROADCAST and frame.command == _ANSWER and frame.data[:2] == ROOM_TEMPERATURE_ID


def is_serial(frame: Frame) -> bool:
    return frame.destination == BROADCAST and frame.command == _SERIAL


def is_address_cast(frame: Frame) -> bool:
    return frame.destination == BROADCAST and frame.command == _ADDRESS_CAST


def is_room_sensor_missing(frame: Frame) -> bool:
    """The boiler's error 411 becoming active for zone 1."""
    return (
        frame.source == BOILER
        and frame.destination == BROADCAST
        and frame.command == _ERROR
        and frame.data[:2] == _ROOM_SENSOR_MISSING
    )
