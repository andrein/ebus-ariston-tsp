from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowHandler, section
from homeassistant.helpers import selector

from . import ebusd, protocol
from .const import (
    CONF_CLIMATE_ENTITIES,
    CONF_SENSOR_ENTITY,
    CONF_SERIAL,
    CONF_SLAVE,
    CONF_SOURCE,
    DEFAULT_PORT,
    DEFAULT_SERIAL,
    DEFAULT_SLAVE,
    DOMAIN,
    SOURCE_NEEDIEST_ROOM,
    SOURCE_THERMOSTAT,
)

_THERMOSTAT_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_SENSOR_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
        ),
    }
)

_ROOMS_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_CLIMATE_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate", multiple=True)
        ),
    }
)


_BUS = "bus"

_CONNECTION_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): str,
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)
        ),
        probatio.Required(_BUS): section(
            probatio.Schema(
                {
                    probatio.Required(CONF_SERIAL, default=DEFAULT_SERIAL): str,
                    probatio.Required(CONF_SLAVE, default=DEFAULT_SLAVE): str,
                }
            ),
            {"collapsed": True},
        ),
    }
)


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    data = {**user_input, **user_input[_BUS]}
    del data[_BUS]
    data[CONF_PORT] = int(data[CONF_PORT])
    return data


def _nest(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        CONF_HOST: data[CONF_HOST],
        CONF_PORT: data[CONF_PORT],
        _BUS: {CONF_SERIAL: data[CONF_SERIAL], CONF_SLAVE: data[CONF_SLAVE]},
    }


async def _validate_connection(data: dict[str, Any]) -> dict[str, str]:
    # The fields are in a section, whose errors the form shows only as a whole.
    if not re.fullmatch(r"[\x20-\x7e]{12}", data[CONF_SERIAL]):
        return {"base": "invalid_serial"}
    if not re.fullmatch(r"[0-9a-fA-F]{2}", data[CONF_SLAVE]) or not protocol.is_slave_with_master(
        int(data[CONF_SLAVE], 16)
    ):
        return {"base": "invalid_slave"}
    try:
        await ebusd.check(data[CONF_HOST], data[CONF_PORT])
    except ebusd.StreamUnsupported:
        return {"base": "stream_unsupported"}
    except ebusd.HexDisabled:
        return {"base": "hex_disabled"}
    except (OSError, TimeoutError, ConnectionError):
        return {"base": "cannot_connect"}
    return {}


class _TemperatureSteps(FlowHandler):
    """Choosing where the reported room temperature comes from, shared by setup and the options."""

    _options: dict[str, Any]

    def _finish(self, options: dict[str, Any]) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_temperature(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="temperature", menu_options=[SOURCE_THERMOSTAT, SOURCE_NEEDIEST_ROOM])

    async def async_step_thermostat(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._finish({CONF_SOURCE: SOURCE_THERMOSTAT, **user_input})
        return self.async_show_form(
            step_id=SOURCE_THERMOSTAT,
            data_schema=self.add_suggested_values_to_schema(_THERMOSTAT_SCHEMA, self._options),
        )

    async def async_step_neediest_room(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._finish({CONF_SOURCE: SOURCE_NEEDIEST_ROOM, **user_input})
        return self.async_show_form(
            step_id=SOURCE_NEEDIEST_ROOM,
            data_schema=self.add_suggested_values_to_schema(_ROOMS_SCHEMA, self._options),
        )


class AristonThermostatConfigFlow(_TemperatureSteps, ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        return OptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _flatten(user_input)
            await self.async_set_unique_id(f"{data[CONF_HOST]}:{data[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            if not (errors := await _validate_connection(data)):
                self._data = data
                return await self.async_step_temperature()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_CONNECTION_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _flatten(user_input)
            unique_id = f"{data[CONF_HOST]}:{data[CONF_PORT]}"
            if any(
                other.unique_id == unique_id and other.entry_id != entry.entry_id
                for other in self._async_current_entries(include_ignore=False)
            ):
                return self.async_abort(reason="already_configured")
            if not (errors := await _validate_connection(data)):
                return self.async_update_reload_and_abort(entry, unique_id=unique_id, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(_CONNECTION_SCHEMA, user_input or _nest(entry.data)),
            errors=errors,
        )

    def _finish(self, options: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title="Zone 1 thermostat", data=self._data, options=options)


class OptionsFlowHandler(_TemperatureSteps, OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._options = dict(self.config_entry.options)
        return await self.async_step_temperature()

    def _finish(self, options: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data=options)
