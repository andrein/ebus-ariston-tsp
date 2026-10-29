"""Connects the room sensor logic to ebusd and to the Home Assistant entities it reads and updates."""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
from datetime import timedelta
import logging
import math
import time

from homeassistant.components.climate import ATTR_CURRENT_TEMPERATURE, ATTR_TEMPERATURE, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, CONF_HOST, CONF_PORT, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    CONF_CLIMATE_ENTITIES,
    CONF_SENSOR_ENTITY,
    CONF_SERIAL,
    CONF_SLAVE,
    CONF_SOURCE,
    DISCONNECTED_ISSUE_DELAY,
    DOMAIN,
    SOURCE_THERMOSTAT,
)
from .ebusd import EbusdStream
from .protocol import StreamLine, master_of
from .room_sensor import RoomSensor
from .rooms import Room, reported_temperature

_LOGGER = logging.getLogger(__name__)

TICK_INTERVAL = timedelta(seconds=5)


class Hub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._config = {**entry.data, **entry.options}
        self.thermostat = self._config[CONF_SOURCE] == SOURCE_THERMOSTAT
        self.sensor = RoomSensor(
            send=self._send,
            temperature=self._room_temperature,
            serial=self._config[CONF_SERIAL],
            slave=int(self._config[CONF_SLAVE], 16),
            thermostat=self.thermostat,
        )
        # Answers from ebusd's own address 31 were asked for again three times; the Cube sent from 70 (slave 75).
        self._source = f"-s {master_of(int(self._config[CONF_SLAVE], 16)):02x} "
        self._stream = EbusdStream(
            self._config[CONF_HOST],
            self._config[CONF_PORT],
            on_line=self._on_line,
            on_rejected=self._on_rejected,
            on_gap=self._on_gap,
            on_connection=self._on_connection,
        )
        self._listeners: list[Callable[[], None]] = []
        self._unsub_tick: Callable[[], None] | None = None
        self._unsub_issue: Callable[[], None] | None = None
        self._issue_id = f"disconnected_{entry.entry_id}"
        self._failed_issue_id = f"registration_failed_{entry.entry_id}"
        self._storm_issue_id = f"reset_storm_{entry.entry_id}"
        self._no_room_data_issue_id = f"no_room_data_{entry.entry_id}"
        self._stopping = False
        self._was_connected = False

    @property
    def connected(self) -> bool:
        return self._stream.connected

    @property
    def room_offset(self) -> float | None:
        """In per-room mode, the neediest room's distance from its own target, as sent to the boiler."""
        zone = self.sensor.zone
        target = self._target()
        if self.thermostat or self.sensor.reported_temperature is None or target is None:
            return None
        if zone.frost is not None and target <= zone.frost:
            return None
        return round(self.sensor.reported_temperature - target, 1)

    async def async_start(self) -> None:
        self.sensor.start(time.monotonic())
        self._stream.start()
        self._unsub_tick = async_track_time_interval(self.hass, self._tick, TICK_INTERVAL)
        self._schedule_issue()

    async def async_stop(self) -> None:
        self._stopping = True
        if self._unsub_tick:
            self._unsub_tick()
            self._unsub_tick = None
        await self._stream.stop()
        if self._unsub_issue:
            self._unsub_issue()
            self._unsub_issue = None
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        ir.async_delete_issue(self.hass, DOMAIN, self._failed_issue_id)
        ir.async_delete_issue(self.hass, DOMAIN, self._storm_issue_id)
        ir.async_delete_issue(self.hass, DOMAIN, self._no_room_data_issue_id)

    def set_comfort(self, value: float) -> None:
        self.sensor.set_comfort(value)

    def set_zone_mode(self, mode: int) -> None:
        self.sensor.set_zone_mode(mode)

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self) -> None:
        for issue_id, active in (
            (self._failed_issue_id, self.sensor.registration_failed),
            (self._storm_issue_id, self.sensor.storm_stopped),
            (self._no_room_data_issue_id, self.sensor.silent),
        ):
            if active:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key=issue_id.removesuffix(f"_{self._entry.entry_id}"),
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        for listener in list(self._listeners):
            listener()

    def _send(self, message: str, delay: float) -> None:
        if delay > 0:
            self.hass.loop.call_later(delay, self._send_delayed, message)
        elif not self._stream.send(self._source + message):
            self.sensor.statistics.send_failures += 1

    @callback
    def _send_delayed(self, message: str) -> None:
        if self.sensor.enabled and not self._stopping:
            self._send(message, 0)

    def _state(self) -> tuple:
        return (
            self.sensor.enabled,
            self.sensor.registered,
            self.sensor.registration_failed,
            self.sensor.storm_stopped,
            self.sensor.silent,
            self.sensor.reported_temperature,
            self.room_offset,
            dataclasses.astuple(self.sensor.statistics),
            dataclasses.astuple(self.sensor.zone),
        )

    @callback
    def _on_line(self, line: StreamLine) -> None:
        before = self._state()
        self.sensor.on_line(line, time.monotonic())
        if line.kind == "e":
            _LOGGER.warning("send failed: %s %s", line.frame, line.error)
        if self._state() != before:
            self._notify()

    @callback
    def _on_gap(self) -> None:
        self.sensor.lost_track()
        self._notify()

    @callback
    def _on_rejected(self, text: str) -> None:
        _LOGGER.warning("ebusd rejected: %s", text)
        self.sensor.statistics.send_failures += 1
        self._notify()

    @callback
    def _on_connection(self, connected: bool) -> None:
        if self._stopping:
            return
        _LOGGER.info("ebusd direct stream %s", "connected" if connected else "disconnected")
        if connected:
            if self._was_connected:
                # A bus reset may have passed while we were away.
                self.sensor.lost_track()
            self._was_connected = True
            if self._unsub_issue:
                self._unsub_issue()
                self._unsub_issue = None
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        else:
            self._schedule_issue()
        self._notify()

    def _schedule_issue(self) -> None:
        if self._unsub_issue is None:
            self._unsub_issue = async_call_later(self.hass, DISCONNECTED_ISSUE_DELAY, self._raise_issue)

    @callback
    def _raise_issue(self, _now) -> None:
        self._unsub_issue = None
        if self.connected or not self.sensor.enabled:
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="disconnected",
            translation_placeholders={"host": self._config[CONF_HOST], "port": str(self._config[CONF_PORT])},
        )

    @callback
    def _tick(self, _now) -> None:
        if self._stream.connected:
            before = self._state()
            self.sensor.tick(time.monotonic())
            if self._state() != before:
                self._notify()

    def _target(self) -> float | None:
        # The boiler switches the zone heat request by comparing the room temperature with this target.
        if (target := self.sensor.zone.target) is not None:
            return target
        # After registering, the boiler casts the target only once our first answer is in: until then the comfort
        # temperature, which is the target in manual mode.
        return self.sensor.zone.comfort

    def _room_temperature(self) -> float | None:
        if self.thermostat:
            return self._sensor_temperature(self._config.get(CONF_SENSOR_ENTITY))
        unit = self.hass.config.units.temperature_unit
        rooms = [
            Room(
                current=_celsius(state.attributes.get(ATTR_CURRENT_TEMPERATURE), unit),
                target=_celsius(state.attributes.get(ATTR_TEMPERATURE), unit),
                heating=state.state == HVACMode.HEAT,
            )
            for entity_id in self._config.get(CONF_CLIMATE_ENTITIES, [])
            if (state := self.hass.states.get(entity_id)) is not None
        ]
        return reported_temperature(rooms, self._target(), self.sensor.zone.frost)

    def _sensor_temperature(self, entity_id: str | None) -> float | None:
        if not entity_id or (state := self.hass.states.get(entity_id)) is None:
            return None
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature.CELSIUS)
        return _celsius(state.state, unit)


def _celsius(value, unit: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or unit not in TemperatureConverter.VALID_UNITS:
        return None
    return TemperatureConverter.convert(number, unit, UnitOfTemperature.CELSIUS)
