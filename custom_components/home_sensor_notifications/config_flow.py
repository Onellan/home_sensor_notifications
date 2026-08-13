from __future__ import annotations

from typing import Any, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DELIVERY_MODE,
    CONF_ENABLED,
    CONF_ESCALATION_SECONDS,
    CONF_GLOBAL_OPEN_MESSAGE,
    CONF_GLOBAL_REMINDER_MESSAGE,
    CONF_MONITORED_SENSORS,
    CONF_NOTIFICATION_MODE,
    CONF_NOTIFY_ON_CLOSE,
    CONF_NOTIFY_TARGETS,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_REMINDER_MINUTES,
    CONF_REMINDER_SECONDS,
    CONF_SENSOR_MESSAGES,
    CONF_SENSOR_REMINDER_SECONDS,
    CONF_SOUND_ENABLED,
    CONF_SOUND_NAME,
    CONF_TARGET_SETTINGS,
    DEFAULT_DELIVERY_MODE,
    DEFAULT_ESCALATION_SECONDS,
    DEFAULT_GLOBAL_OPEN_MESSAGE,
    DEFAULT_GLOBAL_REMINDER_MESSAGE,
    DEFAULT_NOTIFICATION_MODE,
    DEFAULT_NOTIFY_ON_CLOSE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_REMINDER_MINUTES,
    DEFAULT_SOUND_ENABLED,
    DEFAULT_SOUND_NAME,
    DEFAULT_TITLE,
    DELIVERY_MODE_BOTH,
    DELIVERY_MODE_CRITICAL,
    DELIVERY_MODE_NORMAL,
    DOMAIN,
    NOTIFY_DOMAIN,
    NOTIFY_SEND_MESSAGE,
)


def _available_notify_targets(hass) -> list[str]:
    """Return modern notify entities and legacy notify service names."""
    services = hass.services.async_services().get(NOTIFY_DOMAIN, {})
    modern_entities = [state.entity_id for state in hass.states.async_all(NOTIFY_DOMAIN)]
    legacy_services = [
        service_name
        for service_name in services
        if service_name != NOTIFY_SEND_MESSAGE and not service_name.startswith("__")
    ]
    return sorted({*modern_entities, *legacy_services})


_NOTIFICATION_MODE_OPTIONS = [
    {"label": "Use the same message for all sensors", "value": "global"},
    {"label": "Use custom messages per sensor", "value": "per_sensor"},
]

_DELIVERY_MODE_OPTIONS = [
    {"label": "In-app notification only", "value": DELIVERY_MODE_NORMAL},
    {"label": "Ring / critical alert only", "value": DELIVERY_MODE_CRITICAL},
    {"label": "Both in-app and ring / critical", "value": DELIVERY_MODE_BOTH},
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
                CONF_REMINDER_SECONDS,
                default=options.get(
                    CONF_REMINDER_SECONDS,
                    int(options.get(CONF_REMINDER_MINUTES, DEFAULT_REMINDER_MINUTES)) * 60,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=86400,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="sec",
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
                    options=cast(Any, _NOTIFICATION_MODE_OPTIONS),
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
            ),
            vol.Required(
                CONF_DELIVERY_MODE,
                default=options.get(CONF_DELIVERY_MODE, DEFAULT_DELIVERY_MODE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=cast(Any, _DELIVERY_MODE_OPTIONS),
                    multiple=False,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
            ),
            vol.Required(
                CONF_SOUND_ENABLED,
                default=options.get(CONF_SOUND_ENABLED, DEFAULT_SOUND_ENABLED),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_SOUND_NAME,
                default=options.get(CONF_SOUND_NAME, DEFAULT_SOUND_NAME),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiline=False,
                    type=selector.TextSelectorType.TEXT,
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
            vol.Optional(
                CONF_TARGET_SETTINGS,
                default=options.get(CONF_TARGET_SETTINGS, {}),
            ): selector.ObjectSelector(),
            vol.Optional(
                CONF_NOTIFY_ON_CLOSE,
                default=options.get(CONF_NOTIFY_ON_CLOSE, DEFAULT_NOTIFY_ON_CLOSE),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_ESCALATION_SECONDS,
                default=options.get(CONF_ESCALATION_SECONDS, DEFAULT_ESCALATION_SECONDS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=86400, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_SENSOR_REMINDER_SECONDS,
                default=options.get(CONF_SENSOR_REMINDER_SECONDS, {}),
            ): selector.ObjectSelector(),
            vol.Optional(
                CONF_QUIET_HOURS_START,
                default=options.get(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_QUIET_HOURS_END,
                default=options.get(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END),
            ): selector.TextSelector(),
        }
    )


class HomeSensorNotificationsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Home Sensor Notifications."""

    VERSION = 3
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=DEFAULT_TITLE, data=user_input)

        return self.async_show_form(step_id="user", data_schema=_build_schema(self.hass))

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_update_and_abort(
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
        return HomeSensorNotificationsOptionsFlow()


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
