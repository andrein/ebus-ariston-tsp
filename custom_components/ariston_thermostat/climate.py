from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AristonThermostatConfigEntry
from .const import DOMAIN
from .entity import RoomSensorEntity

KEY = "thermostat"

# Zone mode values the Cube's MODE key selects. The Cube does not offer 1, which heats to the reduced temperature.
_ZONE_MODES = {0: HVACMode.OFF, 2: HVACMode.HEAT, 3: HVACMode.AUTO}
_HVAC_MODES = {hvac_mode: mode for mode, hvac_mode in _ZONE_MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: AristonThermostatConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    if hub.thermostat:
        async_add_entities([RoomThermostat(hub, entry.entry_id, KEY)])
    else:
        registry = er.async_get(hass)
        if entity_id := registry.async_get_entity_id(Platform.CLIMATE, DOMAIN, f"{entry.entry_id}_{KEY}"):
            registry.async_remove(entity_id)


class RoomThermostat(RoomSensorEntity, ClimateEntity):
    _attr_name = None
    _attr_hvac_modes = list(_HVAC_MODES)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5

    @property
    def available(self) -> bool:
        return self.hub.connected and self.hub.sensor.enabled

    @property
    def current_temperature(self) -> float | None:
        return self.hub.sensor.reported_temperature

    @property
    def target_temperature(self) -> float | None:
        return self.hub.sensor.zone.comfort

    @property
    def min_temp(self) -> float:
        minimum = self.hub.sensor.zone.comfort_min
        return super().min_temp if minimum is None else minimum

    @property
    def max_temp(self) -> float:
        maximum = self.hub.sensor.zone.comfort_max
        return super().max_temp if maximum is None else maximum

    @property
    def hvac_mode(self) -> HVACMode | None:
        return _ZONE_MODES.get(self.hub.sensor.zone.mode)

    @property
    def hvac_action(self) -> HVACAction | None:
        zone = self.hub.sensor.zone
        if zone.mode == 0:
            return HVACAction.OFF
        if zone.heat_request is None:
            return None
        return HVACAction.HEATING if zone.heat_request else HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        self.hub.set_comfort(kwargs[ATTR_TEMPERATURE])

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self.hub.set_zone_mode(_HVAC_MODES[hvac_mode])
