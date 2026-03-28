from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import websocket_api
from homeassistant.components.frontend import async_remove_panel
from homeassistant.components.panel_custom import async_register_panel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, ServiceCall, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_MESSAGE,
    ATTR_SENSOR,
    ATTR_TARGETS,
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
    DOMAIN,
    NOTIFY_DOMAIN,
    PANEL_CONFIG_KEY_ENTRY_ID,
    PANEL_ICON,
    PANEL_JS_FILENAME,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PANEL_WEBCOMPONENT,
    PLATFORMS,
    SERVICE_SEND_TEST_NOTIFICATION,
    STATE_CLOSED,
    STATE_OPEN,
    STATIC_PANEL_DIR,
    WS_TYPE_GET_CONFIG,
    WS_TYPE_SAVE_CONFIG,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_SENSOR): str,
        vol.Optional(ATTR_TARGETS): [str],
        vol.Optional(ATTR_MESSAGE): str,
    }
)


@dataclass
class OpenSensorState:
    """Runtime state for an open sensor."""

    reminder_cancel: Any | None = None


class HomeSensorNotificationsManager:
    """Manage monitoring and notifications for a config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.unsub_state_change = None
        self.enabled = True
        self.open_sensors: dict[str, OpenSensorState] = {}
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}.json")

    @property
    def options(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @property
    def monitored_sensors(self) -> list[str]:
        return list(self.options.get(CONF_MONITORED_SENSORS, []))

    @property
    def notify_targets(self) -> list[str]:
        return list(self.options.get(CONF_NOTIFY_TARGETS, []))

    @property
    def reminder_minutes(self) -> int:
        return int(self.options.get(CONF_REMINDER_MINUTES, DEFAULT_REMINDER_MINUTES))

    @property
    def notification_mode(self) -> str:
        return str(self.options.get(CONF_NOTIFICATION_MODE, DEFAULT_NOTIFICATION_MODE))

    @property
    def global_open_message(self) -> str:
        return str(self.options.get(CONF_GLOBAL_OPEN_MESSAGE, DEFAULT_GLOBAL_OPEN_MESSAGE))

    @property
    def global_reminder_message(self) -> str:
        return str(self.options.get(CONF_GLOBAL_REMINDER_MESSAGE, DEFAULT_GLOBAL_REMINDER_MESSAGE))

    @property
    def sensor_messages(self) -> dict[str, dict[str, str]]:
        raw = self.options.get(CONF_SENSOR_MESSAGES, {}) or {}
        if not isinstance(raw, dict):
            return {}
        messages: dict[str, dict[str, str]] = {}
        for entity_id, value in raw.items():
            if isinstance(value, dict):
                messages[entity_id] = {
                    "open_message": str(value.get("open_message", "")),
                    "reminder_message": str(value.get("reminder_message", "")),
                }
        return messages

    async def async_initialize(self) -> None:
        stored = await self.store.async_load() or {}
        self.enabled = stored.get(CONF_ENABLED, self.options.get(CONF_ENABLED, True))
        self._start_listener()

        for entity_id in self.monitored_sensors:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == STATE_OPEN:
                await self._mark_open(entity_id, send_initial=False)

    async def async_shutdown(self) -> None:
        if self.unsub_state_change is not None:
            self.unsub_state_change()
            self.unsub_state_change = None
        for sensor_state in self.open_sensors.values():
            if sensor_state.reminder_cancel is not None:
                sensor_state.reminder_cancel()
        self.open_sensors.clear()

    async def async_handle_entry_update(self) -> None:
        existing = set(self.open_sensors)
        current = set(self.monitored_sensors)

        for entity_id in existing - current:
            self._clear_sensor(entity_id)

        if self.unsub_state_change is not None:
            self.unsub_state_change()
        self._start_listener()

        for entity_id in current:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == STATE_OPEN and entity_id not in self.open_sensors:
                await self._mark_open(entity_id, send_initial=False)

    def _start_listener(self) -> None:
        if not self.monitored_sensors:
            self.unsub_state_change = None
            return
        self.unsub_state_change = async_track_state_change_event(
            self.hass,
            self.monitored_sensors,
            self._async_state_changed,
        )

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        await self.store.async_save({CONF_ENABLED: enabled})

    @callback
    def _clear_sensor(self, entity_id: str) -> None:
        sensor_state = self.open_sensors.pop(entity_id, None)
        if sensor_state and sensor_state.reminder_cancel is not None:
            sensor_state.reminder_cancel()

    async def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None:
            return
        if old_state is not None and old_state.state == new_state.state:
            return

        if new_state.state == STATE_OPEN:
            await self._mark_open(entity_id, send_initial=True)
        elif new_state.state == STATE_CLOSED:
            self._clear_sensor(entity_id)

    async def _mark_open(self, entity_id: str, send_initial: bool) -> None:
        sensor_state = self.open_sensors.get(entity_id)
        if sensor_state is None:
            sensor_state = OpenSensorState()
            self.open_sensors[entity_id] = sensor_state
        elif sensor_state.reminder_cancel is not None:
            sensor_state.reminder_cancel()
            sensor_state.reminder_cancel = None

        if send_initial and self.enabled:
            await self._send_notification(
                self._render_message(entity_id, is_reminder=False),
                self.notify_targets,
            )

        sensor_state.reminder_cancel = async_call_later(
            self.hass,
            timedelta(minutes=self.reminder_minutes),
            lambda _: self.hass.async_create_task(self._async_send_reminder(entity_id)),
        )

    async def _async_send_reminder(self, entity_id: str) -> None:
        sensor_state = self.open_sensors.get(entity_id)
        current_state = self.hass.states.get(entity_id)

        if sensor_state is None or current_state is None or current_state.state != STATE_OPEN:
            self._clear_sensor(entity_id)
            return

        if self.enabled:
            await self._send_notification(
                self._render_message(entity_id, is_reminder=True),
                self.notify_targets,
            )

        sensor_state.reminder_cancel = async_call_later(
            self.hass,
            timedelta(minutes=self.reminder_minutes),
            lambda _: self.hass.async_create_task(self._async_send_reminder(entity_id)),
        )

    def _render_message(self, entity_id: str, is_reminder: bool) -> str:
        sensor_name = self._friendly_name(entity_id)
        template = self.global_reminder_message if is_reminder else self.global_open_message

        if self.notification_mode == "per_sensor":
            per_sensor = self.sensor_messages.get(entity_id, {})
            key = "reminder_message" if is_reminder else "open_message"
            template = per_sensor.get(key) or template

        context = {
            "sensor": sensor_name,
            "entity_id": entity_id,
            "state": STATE_OPEN,
        }
        try:
            return template.format(**context)
        except Exception:
            _LOGGER.exception("Invalid notification template for %s", entity_id)
            fallback = DEFAULT_GLOBAL_REMINDER_MESSAGE if is_reminder else DEFAULT_GLOBAL_OPEN_MESSAGE
            return fallback.format(**context)

    async def _send_notification(self, message: str, targets: list[str]) -> None:
        if not targets:
            _LOGGER.warning("No notify targets configured for %s", self.entry.title)
            return

        for target in targets:
            try:
                await self.hass.services.async_call(
                    NOTIFY_DOMAIN,
                    target,
                    {"message": message, "title": self.entry.title},
                    blocking=True,
                )
            except Exception:
                _LOGGER.exception("Failed to send notification via notify.%s", target)

    def _friendly_name(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        if state is None:
            return entity_id
        return cast(str, state.attributes.get("friendly_name", entity_id))


def _available_notify_targets(hass: HomeAssistant) -> list[str]:
    services = hass.services.async_services().get(NOTIFY_DOMAIN, {})
    return sorted(
        service_name
        for service_name in services
        if service_name != "send_message" and not service_name.startswith("__")
    )


def _available_binary_sensors(hass: HomeAssistant) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    for state in sorted(hass.states.async_all("binary_sensor"), key=lambda item: item.entity_id):
        entity_id = state.entity_id
        device_class = state.attributes.get("device_class")
        label = state.attributes.get("friendly_name", entity_id)
        if device_class in ("door", "window", "opening", None):
            entities.append(
                {
                    "entity_id": entity_id,
                    "name": str(label),
                    "device_class": str(device_class or ""),
                    "state": state.state,
                }
            )
    return entities


async def _async_register_panel(hass: HomeAssistant, entry_id: str) -> None:
    panel_dir = Path(__file__).parent / STATIC_PANEL_DIR
    panel_url = f"/api/{DOMAIN}/static"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(panel_url, str(panel_dir), False)]
    )
    async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_WEBCOMPONENT,
        js_url=f"{panel_url}/{PANEL_JS_FILENAME}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        config={PANEL_CONFIG_KEY_ENTRY_ID: entry_id},
        require_admin=False,
    )


def _register_websocket_commands(hass: HomeAssistant) -> None:
    if hass.data[DOMAIN].get("websocket_registered"):
        return

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_GET_CONFIG})
    @websocket_api.async_response
    async def websocket_get_config(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_configured", "Integration is not configured")
            return

        entry = entries[0]
        manager: HomeSensorNotificationsManager = hass.data[DOMAIN][entry.entry_id]
        connection.send_result(
            msg["id"],
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "config": {
                    CONF_MONITORED_SENSORS: manager.monitored_sensors,
                    CONF_NOTIFY_TARGETS: manager.notify_targets,
                    CONF_REMINDER_MINUTES: manager.reminder_minutes,
                    CONF_ENABLED: manager.enabled,
                    CONF_NOTIFICATION_MODE: manager.notification_mode,
                    CONF_GLOBAL_OPEN_MESSAGE: manager.global_open_message,
                    CONF_GLOBAL_REMINDER_MESSAGE: manager.global_reminder_message,
                    CONF_SENSOR_MESSAGES: manager.sensor_messages,
                },
                "available_sensors": _available_binary_sensors(hass),
                "available_notify_targets": _available_notify_targets(hass),
                "open_sensors": sorted(manager.open_sensors.keys()),
                "updated_at": dt_util.utcnow().isoformat(),
            },
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_TYPE_SAVE_CONFIG,
            vol.Required("config"): dict,
        }
    )
    @websocket_api.async_response
    async def websocket_save_config(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_configured", "Integration is not configured")
            return

        entry = entries[0]
        config = dict(msg["config"])
        cleaned = {
            CONF_MONITORED_SENSORS: list(config.get(CONF_MONITORED_SENSORS, [])),
            CONF_NOTIFY_TARGETS: list(config.get(CONF_NOTIFY_TARGETS, [])),
            CONF_REMINDER_MINUTES: max(1, int(config.get(CONF_REMINDER_MINUTES, DEFAULT_REMINDER_MINUTES))),
            CONF_ENABLED: bool(config.get(CONF_ENABLED, True)),
            CONF_NOTIFICATION_MODE: str(config.get(CONF_NOTIFICATION_MODE, DEFAULT_NOTIFICATION_MODE)),
            CONF_GLOBAL_OPEN_MESSAGE: str(config.get(CONF_GLOBAL_OPEN_MESSAGE, DEFAULT_GLOBAL_OPEN_MESSAGE)),
            CONF_GLOBAL_REMINDER_MESSAGE: str(config.get(CONF_GLOBAL_REMINDER_MESSAGE, DEFAULT_GLOBAL_REMINDER_MESSAGE)),
            CONF_SENSOR_MESSAGES: config.get(CONF_SENSOR_MESSAGES, {}) if isinstance(config.get(CONF_SENSOR_MESSAGES, {}), dict) else {},
        }

        hass.config_entries.async_update_entry(entry, options=cleaned)
        manager: HomeSensorNotificationsManager = hass.data[DOMAIN][entry.entry_id]
        await manager.set_enabled(cleaned[CONF_ENABLED])
        await hass.config_entries.async_reload(entry.entry_id)
        connection.send_result(msg["id"], {"saved": True})

    websocket_api.async_register_command(hass, websocket_get_config)
    websocket_api.async_register_command(hass, websocket_save_config)
    hass.data[DOMAIN]["websocket_registered"] = True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    _register_websocket_commands(hass)

    async def async_send_test_notification(call: ServiceCall) -> None:
        managers: dict[str, HomeSensorNotificationsManager] = hass.data[DOMAIN]
        manager_entries = [value for key, value in managers.items() if key != "websocket_registered"]
        if not manager_entries:
            _LOGGER.warning("No Home Sensor Notifications entry is configured")
            return

        manager = manager_entries[0]
        sensor = call.data.get(ATTR_SENSOR)
        targets = call.data.get(ATTR_TARGETS, manager.notify_targets)
        message = call.data.get(ATTR_MESSAGE)

        if message is None:
            if sensor is None:
                message = f"Test notification from {manager.entry.title}."
            else:
                message = manager._render_message(sensor, is_reminder=False)

        await manager._send_notification(message, list(targets))

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TEST_NOTIFICATION,
        async_send_test_notification,
        schema=SERVICE_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = HomeSensorNotificationsManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = manager
    await manager.async_initialize()
    await _async_register_panel(hass, entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager: HomeSensorNotificationsManager = hass.data[DOMAIN].pop(entry.entry_id)
        await manager.async_shutdown()
        async_remove_panel(hass, PANEL_URL_PATH)
    return unload_ok
