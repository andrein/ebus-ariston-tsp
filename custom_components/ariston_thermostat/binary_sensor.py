from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AristonThermostatConfigEntry
from .entity import RoomSensorEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AristonThermostatConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    async_add_entities(
        [
            RegisteredSensor(hub, entry.entry_id, "registered"),
            ConnectedSensor(hub, entry.entry_id, "connected"),
        ]
    )


class RegisteredSensor(RoomSensorEntity, BinarySensorEntity):
    """On once the boiler or the gateway asked for the room temperature after the last bus reset."""

    @property
    def is_on(self) -> bool:
        return self.hub.sensor.registered


class ConnectedSensor(RoomSensorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.hub.connected
