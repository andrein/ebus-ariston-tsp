"""Zone thermostat for Ariston boilers on eBUS, through ebusd's direct stream mode."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .hub import Hub

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]

type AristonThermostatConfigEntry = ConfigEntry[Hub]


async def async_setup_entry(hass: HomeAssistant, entry: AristonThermostatConfigEntry) -> bool:
    hub = Hub(hass, entry)
    entry.runtime_data = hub
    await hub.async_start()
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await hub.async_stop()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AristonThermostatConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded
