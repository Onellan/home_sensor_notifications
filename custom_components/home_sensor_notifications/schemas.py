"""Validation schemas for WebSocket and service input."""

from __future__ import annotations

import voluptuous as vol

from .const import (
    ATTR_DELIVERY_MODE,
    ATTR_MESSAGE,
    ATTR_SENSOR,
    ATTR_SOUND_ENABLED,
    ATTR_SOUND_NAME,
    ATTR_TARGETS,
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
    CONF_REMINDER_SECONDS,
    CONF_SENSOR_MESSAGES,
    CONF_SENSOR_REMINDER_SECONDS,
    CONF_SOUND_ENABLED,
    CONF_SOUND_NAME,
    CONF_TARGET_SETTINGS,
    DEFAULT_DELIVERY_MODE,
    DEFAULT_ESCALATION_SECONDS,
    DEFAULT_NOTIFY_ON_CLOSE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_SOUND_ENABLED,
    DEFAULT_SOUND_NAME,
    VALID_DELIVERY_MODES,
)

MAX_TARGETS = 100
MAX_MESSAGE_LENGTH = 4096
MAX_SOUND_NAME_LENGTH = 128
MAX_ENTITY_ID_LENGTH = 255
BOUNDED_ENTITY_ID = vol.All(str, vol.Length(min=1, max=MAX_ENTITY_ID_LENGTH))
BOUNDED_MESSAGE = vol.All(str, vol.Length(max=MAX_MESSAGE_LENGTH))
BOUNDED_SOUND_NAME = vol.All(str, vol.Length(max=MAX_SOUND_NAME_LENGTH))
TIME_OF_DAY = vol.All(str, vol.Match(r"^$|^(?:[01]\d|2[0-3]):[0-5]\d$"))
MESSAGE_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional("open_message", default=""): BOUNDED_MESSAGE,
        vol.Optional("reminder_message", default=""): BOUNDED_MESSAGE,
    },
    extra=vol.PREVENT_EXTRA,
)
TARGET_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DELIVERY_MODE, default=DEFAULT_DELIVERY_MODE): vol.In(
            VALID_DELIVERY_MODES
        ),
        vol.Optional(CONF_SOUND_ENABLED, default=DEFAULT_SOUND_ENABLED): bool,
        vol.Optional(CONF_SOUND_NAME, default=DEFAULT_SOUND_NAME): BOUNDED_SOUND_NAME,
    },
    extra=vol.PREVENT_EXTRA,
)
PANEL_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MONITORED_SENSORS): vol.All(
            [BOUNDED_ENTITY_ID], vol.Length(max=MAX_TARGETS)
        ),
        vol.Required(CONF_NOTIFY_TARGETS): vol.All(
            [BOUNDED_ENTITY_ID], vol.Length(max=MAX_TARGETS)
        ),
        vol.Required(CONF_REMINDER_SECONDS): vol.All(int, vol.Range(min=1, max=86400)),
        vol.Required(CONF_ENABLED): bool,
        vol.Required(CONF_NOTIFICATION_MODE): vol.In(["global", "per_sensor"]),
        vol.Required(CONF_GLOBAL_OPEN_MESSAGE): BOUNDED_MESSAGE,
        vol.Required(CONF_GLOBAL_REMINDER_MESSAGE): BOUNDED_MESSAGE,
        vol.Required(CONF_SENSOR_MESSAGES): {BOUNDED_ENTITY_ID: MESSAGE_SETTINGS_SCHEMA},
        vol.Required(CONF_DELIVERY_MODE): vol.In(VALID_DELIVERY_MODES),
        vol.Required(CONF_SOUND_ENABLED): bool,
        vol.Required(CONF_SOUND_NAME): BOUNDED_SOUND_NAME,
        vol.Required(CONF_TARGET_SETTINGS): {BOUNDED_ENTITY_ID: TARGET_SETTINGS_SCHEMA},
        vol.Optional(CONF_NOTIFY_ON_CLOSE, default=DEFAULT_NOTIFY_ON_CLOSE): bool,
        vol.Optional(CONF_ESCALATION_SECONDS, default=DEFAULT_ESCALATION_SECONDS): vol.All(
            int, vol.Range(min=0, max=86400)
        ),
        vol.Optional(CONF_SENSOR_REMINDER_SECONDS, default={}): {
            BOUNDED_ENTITY_ID: vol.All(int, vol.Range(min=1, max=86400))
        },
        vol.Optional(CONF_QUIET_HOURS_START, default=DEFAULT_QUIET_HOURS_START): TIME_OF_DAY,
        vol.Optional(CONF_QUIET_HOURS_END, default=DEFAULT_QUIET_HOURS_END): TIME_OF_DAY,
    },
    extra=vol.PREVENT_EXTRA,
)
SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_SENSOR): BOUNDED_ENTITY_ID,
        vol.Optional(ATTR_TARGETS): vol.All(
            [BOUNDED_ENTITY_ID], vol.Length(min=1, max=MAX_TARGETS)
        ),
        vol.Optional(ATTR_MESSAGE): BOUNDED_MESSAGE,
        vol.Optional(ATTR_DELIVERY_MODE): vol.In(VALID_DELIVERY_MODES),
        vol.Optional(ATTR_SOUND_ENABLED): bool,
        vol.Optional(ATTR_SOUND_NAME): BOUNDED_SOUND_NAME,
    },
    extra=vol.PREVENT_EXTRA,
)
