"""Behaviour of the zone room sensor on the bus, independent of Home Assistant."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from . import protocol
from .protocol import StreamLine

CAST_INTERVAL = 60
# The Cube, the boiler and the gateway each cast their slave address every ~5 min. Without it the gateway reset the
# bus 30 min after every registration. For an unknown slave it starts an enumeration, so only while registered.
ADDRESS_CAST_INTERVAL = 300
# The boiler asks for the room temperature within ~30 s of the first bus reset when registration works.
REGISTRATION_TIMEOUT = 90
# Every attempt makes the boiler enumerate the bus, which stalls other traffic for ~30 s.
REGISTRATION_RETRY = 600
REGISTRATION_ATTEMPTS = 3
# For an unknown slave the boiler starts a bus enumeration after its address cast; a known one triggers nothing.
PROBE_WINDOW = 10
# The Cube sent its serial ~0.3 s after each bus reset. Sent after 0.14 s from ebusd's address 31, which wins
# arbitration against the boiler, the boiler repeated the reset step over and over.
SERIAL_DELAY = 0.3
# More bus resets than this within the window means the boiler is stuck on our answers: stop instead of feeding it.
# A normal re-enumeration has up to ~7 resets in 20 s; a storm seen here had 4 a second.
STORM_RESETS = 15
STORM_WINDOW = 60

# Below the lowest zone frost temperature (2 °C): the boiler started heating for a room cast at 2.0.
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 35.0
# Without a room temperature for this long the sensor goes silent, as an unplugged Cube does: the gateway then resets
# the bus and, with the room sensor in the thermoregulation, the boiler raises 411 and falls back on the outdoor
# curve. Answering with an old value would hold the flow temperature where it was for as long as the data is missing.
STALE_AFTER = 600

# The boiler also answers ebusd's and the gateway's queries every few minutes and casts all settings every ~28 min.
SETTINGS_INTERVAL = 300
# Asking again after a write shows whether the boiler took it.
WRITE_CHECK_DELAY = 1.0


@dataclass
class Zone:
    """Zone 1 as the boiler reports it."""

    target: float | None = None
    comfort: float | None = None
    comfort_min: float | None = None
    comfort_max: float | None = None
    mode: int | None = None
    heat_request: bool | None = None
    frost: float | None = None

    def update(self, values: dict[bytes, tuple[bytes, ...]]) -> None:
        if target := values.get(protocol.ZONE_TARGET_ID):
            self.target = protocol.decode_temperature(target[0])
        if comfort := values.get(protocol.COMFORT_ID):
            self.comfort = protocol.decode_temperature(comfort[0])
            if len(comfort) == 3:
                self.comfort_min = protocol.decode_temperature(comfort[1])
                self.comfort_max = protocol.decode_temperature(comfort[2])
        if mode := values.get(protocol.ZONE_MODE_ID):
            self.mode = mode[0][0]
        if heat_request := values.get(protocol.HEAT_REQUEST_ID):
            self.heat_request = heat_request[0][0] == 1
        if frost := values.get(protocol.FROST_ID):
            self.frost = protocol.decode_temperature(frost[0])


@dataclass
class Statistics:
    queries_answered: int = 0
    send_failures: int = 0
    bus_resets: int = 0
    registrations: int = 0
    answer_latency_ms: float | None = None
    serial_latency_ms: float | None = None


class RoomSensor:
    """Registers with the boiler, answers its room temperature queries and casts the room temperature."""

    def __init__(
        self,
        send: Callable[[str, float], None],
        temperature: Callable[[], float | None],
        serial: str,
        slave: int,
        thermostat: bool = False,
    ) -> None:
        self._send = send
        self._temperature = temperature
        self._serial = protocol.serial(serial, slave)
        self._address_cast = protocol.address_cast(slave)
        self.enabled = False
        self.registered = False
        self.registration_failed = False
        self.storm_stopped = False
        # No room temperature for STALE_AFTER: nothing is sent until one is back.
        self.silent = False
        self.statistics = Statistics()
        self.reported_temperature: float | None = None
        self._temperature_at = 0.0
        self.zone = Zone()
        self._thermostat = thermostat
        self._last_settings_query = 0.0
        self._attempts = 0
        self._registering_since: float | None = None
        self._retry_at: float | None = None
        self._probe_at: float | None = None
        self._probe_until: float | None = None
        self._last_cast = 0.0
        self._last_address_cast = 0.0
        self._query_timestamp: float | None = None
        self._answer_resent = False
        self._reset_timestamp: float | None = None
        self._recent_resets: deque[float] = deque()

    def start(self, now: float) -> None:
        """Answer and cast at once, and check with an address cast whether the boiler knows the sensor."""
        self.enabled = True
        self._temperature_at = now
        self._last_cast = now - CAST_INTERVAL
        self._last_settings_query = now - SETTINGS_INTERVAL
        self._probe_at = now

    def lost_track(self) -> None:
        """Messages were missed, maybe a bus reset: check again whether the boiler knows the sensor."""
        self.registered = False
        if self._registering_since is None and self._retry_at is None:
            self._probe_at = 0.0

    def on_line(self, line: StreamLine, now: float) -> None:
        frame = line.frame
        if line.kind == "e":
            self.statistics.send_failures += 1
            if protocol.is_room_temperature_answer(frame):
                self._query_timestamp = None
                # Right after registering, the boiler holds back its status casts until it has an answer.
                if not self._answer_resent and (temperature := self._current_temperature(now)) is not None:
                    self._answer_resent = True
                    self._send(protocol.room_temperature_answer(temperature), 0)
            elif protocol.is_address_cast(frame) and self._probe_until is not None:
                # Silence after a cast that never reached the bus says nothing.
                self._probe_until = None
                self._probe_at = now
            return
        if line.kind != "r":
            self._measure_latency(line)
            return
        self.zone.update(protocol.boiler_values(frame))
        if not self.enabled or self.silent:
            return
        if protocol.is_bus_reset(frame):
            self.statistics.bus_resets += 1
            self.registered = False
            self._recent_resets.append(now)
            while self._recent_resets[0] < now - STORM_WINDOW:
                self._recent_resets.popleft()
            if len(self._recent_resets) > STORM_RESETS:
                self.enabled = False
                self.registered = False
                self._registering_since = None
                self._retry_at = None
                self.storm_stopped = True
                return
            # This enumeration carries our serial, so a pending attempt of our own would only stall the bus again.
            self._retry_at = None
            if self._probe_until is not None:
                # The boiler did not know the sensor and enumerates: a registration attempt that did not cost one.
                self._probe_until = None
                self._registering_since = now
            self._reset_timestamp = line.timestamp
            self._send(self._serial, SERIAL_DELAY)
        elif protocol.is_room_temperature_query(frame):
            # Unanswered until the temperature is known: the gateway resets the bus only after ~27 min of silence.
            if (temperature := self._current_temperature(now)) is not None:
                self._query_timestamp = line.timestamp
                self._answer_resent = False
                self._send(protocol.room_temperature_answer(temperature), 0)
                self.statistics.queries_answered += 1
            if not self.registered:
                self.registered = True
                self.registration_failed = False
                self.statistics.registrations += 1
                self._attempts = 0
                self._registering_since = None
                self._retry_at = None
                self._probe_at = None
                self._probe_until = None
                self._last_address_cast = now
        elif protocol.is_room_sensor_missing(frame) and self._registering_since is None and self._retry_at is None:
            self.registered = False
            self._register(now)

    def tick(self, now: float) -> None:
        if not self.enabled:
            return
        # Any device may ask; ebusd and the gateway do too.
        wanted = self._thermostat or self.zone.target is None or self.zone.frost is None
        if wanted and now - self._last_settings_query >= SETTINGS_INTERVAL:
            self._last_settings_query = now
            self._query_settings()
        temperature = self._current_temperature(now)
        if temperature is None:
            if not self.silent and now - self._temperature_at >= STALE_AFTER:
                self.silent = True
                self.registered = False
                self._registering_since = None
                self._retry_at = None
                self._probe_at = None
                self._probe_until = None
            return
        if self.silent:
            self.silent = False
            self.lost_track()
        # Also while unregistered: a cast from an unregistered source triggers nothing.
        if now - self._last_cast >= CAST_INTERVAL:
            self._last_cast = now
            self._send(protocol.room_temperature_cast(temperature), 0)
        if self._probe_at is not None and now >= self._probe_at:
            self._probe_at = None
            self._probe_until = now + PROBE_WINDOW
            self._send(self._address_cast, 0)
        if self._probe_until is not None and now >= self._probe_until:
            self._probe_until = None
            self.registered = True
            self._last_address_cast = now
        if self.registered:
            if now - self._last_address_cast >= ADDRESS_CAST_INTERVAL:
                self._last_address_cast = now
                self._send(self._address_cast, 0)
            return
        if self._registering_since is not None and now - self._registering_since >= REGISTRATION_TIMEOUT:
            self._registering_since = None
            if self._attempts >= REGISTRATION_ATTEMPTS:
                self.registration_failed = True
            else:
                self._retry_at = now + REGISTRATION_RETRY
        if self._retry_at is not None and now >= self._retry_at:
            self._register(now)

    def set_comfort(self, value: float) -> None:
        """Set the zone comfort temperature, as turning the Cube's dial does."""
        self._send(protocol.write(protocol.COMFORT_ID, protocol.encode_temperature(value)), 0)
        self._send(protocol.setting_query(protocol.COMFORT_ID), WRITE_CHECK_DELAY)

    def set_zone_mode(self, mode: int) -> None:
        self._send(protocol.write(protocol.ZONE_MODE_ID, bytes((mode,))), 0)
        self._send(protocol.setting_query(protocol.ZONE_MODE_ID), WRITE_CHECK_DELAY)

    def _query_settings(self) -> None:
        self._send(protocol.setting_query(protocol.COMFORT_ID), 0)
        self._send(protocol.setting_query(protocol.ZONE_MODE_ID), 0)
        self._send(protocol.setting_query(protocol.FROST_ID), 0)
        if self._thermostat:
            self._send(protocol.value_query(protocol.HEAT_REQUEST_ID), 0)

    def _register(self, now: float) -> None:
        if self._attempts >= REGISTRATION_ATTEMPTS:
            self.registration_failed = True
            return
        self._attempts += 1
        self._registering_since = now
        self._retry_at = None
        self._send(protocol.bus_reset_request(), 0)

    def _measure_latency(self, line: StreamLine) -> None:
        if self._query_timestamp is not None and protocol.is_room_temperature_answer(line.frame):
            self.statistics.answer_latency_ms = (line.timestamp - self._query_timestamp) * 1000
            self._query_timestamp = None
        elif self._reset_timestamp is not None and protocol.is_serial(line.frame):
            self.statistics.serial_latency_ms = (line.timestamp - self._reset_timestamp) * 1000
            self._reset_timestamp = None

    def _current_temperature(self, now: float) -> float | None:
        """The room temperature to send, or the last one sent while the room temperature is missing but not stale."""
        if (temperature := self._temperature()) is not None:
            self._temperature_at = now
            self.reported_temperature = round(min(max(temperature, MIN_TEMPERATURE), MAX_TEMPERATURE), 1)
        elif self.reported_temperature is not None and now - self._temperature_at >= STALE_AFTER:
            self.reported_temperature = None
        return self.reported_temperature
