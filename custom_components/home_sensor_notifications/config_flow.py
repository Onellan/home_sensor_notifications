from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLED,
    CONF_GLOBAL_OPEN_MESSAGE,
    CONF_GLOBAL_REMINDER_MESSAGE,
    CONF_MONITORED_SENSORS,
    CONF_NOTIFICATION_MODE,
    CONF_NOTIFY_TARGETS,
    CONF_REMINDER_MINUTES,
    CONF_SENSOR_MESSAGES,
    DEFAULT_GLOBAL_OPEN_MESSAGE,
    DEFAULT_GLOBAL_REMINDER_MESSAGE,
    DEFAULT_NOTIFICATION_MODE,
    DEFAULT_REMINDER_MINUTES,
    DEFAULT_TITLE,
    DOMAIN,
    NOTIFY_DOMAIN,
    NOTIFY_SEND_MESSAGE,
)


def _available_notify_targets(hass) -> list[str]:
    """Return available notify targets (service names)."""
    services = hass.services.async_services().get(NOTIFY_DOMAIN, {})
    return sorted(
        service_name
        for service_name in services
        if service_name != NOTIFY_SEND_MESSAGE and not service_name.startswith("__")
    )


_NOTIFICATION_MODE_OPTIONS = [
    {"label": "Use the same message for all sensors", "value": "global"},
    {"label": "Use custom messages per sensor", "value": "per_sensor"},
]


def _build_schema(hass, options: dict[str, Any] | None = None) -> vol.Schema:
    """Build the config/options form schema."""
    options = options or {}
    notify_targets = _available_notify_targets(hass)

    return vol.Schema(
        {
            vol.Required(
                CONF_MONITORED_SENSORS,
                default=options.get(CONF_MONITORED_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor",
                    multiple=True,
                )
            ),
            vol.Required(
                CONF_NOTIFY_TARGETS,
                default=options.get(CONF_NOTIFY_TARGETS, []),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_targets,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
            ),
            vol.Required(
                CONF_REMINDER_MINUTES,
                default=options.get(CONF_REMINDER_MINUTES, DEFAULT_REMINDER_MINUTES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=1440,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Required(
                CONF_ENABLED,
                default=options.get(CONF_ENABLED, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_NOTIFICATION_MODE,
                default=options.get(CONF_NOTIFICATION_MODE, DEFAULT_NOTIFICATION_MODE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_NOTIFICATION_MODE_OPTIONS,
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
            ),
            vol.Required(
                CONF_GLOBAL_OPEN_MESSAGE,
                default=options.get(CONF_GLOBAL_OPEN_MESSAGE, DEFAULT_GLOBAL_OPEN_MESSAGE),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiline=True,
                    type=selector.TextSelectorType.TEXT,
                )
            ),
            vol.Required(
                CONF_GLOBAL_REMINDER_MESSAGE,
                default=options.get(CONF_GLOBAL_REMINDER_MESSAGE, DEFAULT_GLOBAL_REMINDER_MESSAGE),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiline=True,
                    type=selector.TextSelectorType.TEXT,
                )
            ),
            vol.Optional(
                CONF_SENSOR_MESSAGES,
                default=options.get(CONF_SENSOR_MESSAGES, {}),
            ): selector.ObjectSelector(),
        }
    )


class HomeSensorNotificationsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Home Sensor Notifications."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=DEFAULT_TITLE, data=user_input)

        return self.async_show_form(step_id="user", data_schema=_build_schema(self.hass))

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates=user_input,
            )

        entry = self._get_reconfigure_entry()
        merged = {**entry.data, **entry.options}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_schema(self.hass, merged),
        )

    async def async_step_import(self, user_input: dict[str, Any]):
        return self.async_create_entry(title=DEFAULT_TITLE, data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return HomeSensorNotificationsOptionsFlow(config_entry)


class HomeSensorNotificationsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        merged = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(self.hass, merged),
        )
