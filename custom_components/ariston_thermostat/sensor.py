from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, Platform, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AristonThermostatConfigEntry
from .const import DOMAIN
from .entity import RoomSensorEntity
from .hub import Hub


@dataclass(frozen=True, kw_only=True)
class RoomSensorDescription(SensorEntityDescription):
    value: Callable[[Hub], float | int | None]
    # Only in room thermostat mode (True) or only in per-room mode (False); both when None.
    thermostat: bool | None = None


SENSORS = (
    RoomSensorDescription(
        key="reported_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda hub: hub.sensor.reported_temperature,
        thermostat=True,
    ),
    RoomSensorDescription(
        key="room_offset",
        # A temperature difference: the temperature device class would convert it like a temperature.
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value=lambda hub: hub.room_offset,
        thermostat=False,
    ),
    RoomSensorDescription(
        key="answer_latency",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda hub: hub.sensor.statistics.answer_latency_ms,
    ),
    RoomSensorDescription(
        key="serial_latency",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda hub: hub.sensor.statistics.serial_latency_ms,
    ),
    RoomSensorDescription(
        key="queries_answered",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda hub: hub.sensor.statistics.queries_answered,
    ),
    RoomSensorDescription(
        key="send_failures",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda hub: hub.sensor.statistics.send_failures,
    ),
    RoomSensorDescription(
        key="bus_resets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda hub: hub.sensor.statistics.bus_resets,
    ),
    RoomSensorDescription(
        key="registrations",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda hub: hub.sensor.statistics.registrations,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AristonThermostatConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    registry = er.async_get(hass)
    for description in SENSORS:
        if description.thermostat in (None, hub.thermostat):
            continue
        unique_id = f"{entry.entry_id}_{description.key}"
        if entity_id := registry.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id):
            registry.async_remove(entity_id)
    async_add_entities(
        RoomSensorValue(hub, entry.entry_id, description)
        for description in SENSORS
        if description.thermostat in (None, hub.thermostat)
    )


class RoomSensorValue(RoomSensorEntity, SensorEntity):
    entity_description: RoomSensorDescription

    def __init__(self, hub, entry_id: str, description: RoomSensorDescription) -> None:
        super().__init__(hub, entry_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        return self.entity_description.value(self.hub)
