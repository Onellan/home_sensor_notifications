from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import time as datetime_time
from datetime import timedelta
from typing import Any, cast

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from . import panel as panel_helpers
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
    DEFAULT_REMINDER_SECONDS,
    DEFAULT_SOUND_ENABLED,
    DEFAULT_SOUND_NAME,
    DELIVERY_MODE_BOTH,
    DELIVERY_MODE_CRITICAL,
    DELIVERY_MODE_NORMAL,
    DOMAIN,
    NOTIFY_DOMAIN,
    NOTIFY_SEND_MESSAGE,
    PLATFORMS,
    SERVICE_SEND_TEST_NOTIFICATION,
    STATE_OPEN,
    VALID_DELIVERY_MODES,
    WS_TYPE_GET_CONFIG,
    WS_TYPE_SAVE_CONFIG,
)
from .runtime import get_manager
from .schemas import PANEL_CONFIG_SCHEMA, SERVICE_SCHEMA

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CONFIG_ENTRY_VERSION = 3
CONFIG_ENTRY_MINOR_VERSION = 1
DATA_WEBSOCKET_REGISTERED = "websocket_registered"
DATA_SERVICE_REGISTERED = "service_registered"


@dataclass
class OpenSensorState:
    """Runtime state for an open sensor."""

    reminder_cancel: Any | None = None
    reminder_task: asyncio.Task[None] | None = None
    opened_at: Any | None = None
    escalated: bool = False


class HomeSensorNotificationsManager:
    """Manage monitoring and notifications for a config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.unsub_state_change: Callable[[], None] | None = None
        self.open_sensors: dict[str, OpenSensorState] = {}
        self._shutting_down = False
        self._notification_semaphore = asyncio.Semaphore(4)

    @property
    def options(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @property
    def enabled(self) -> bool:
        """Enablement is persisted solely in config-entry options/data."""
        return bool(self.options.get(CONF_ENABLED, True))

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
    def reminder_seconds(self) -> int:
        if CONF_REMINDER_SECONDS in self.options:
            return max(1, int(self.options.get(CONF_REMINDER_SECONDS, DEFAULT_REMINDER_SECONDS)))
        return max(1, self.reminder_minutes * 60)

    def reminder_seconds_for(self, entity_id: str) -> int:
        """Return a bounded per-sensor override or the configured default."""
        value = self.options.get(CONF_SENSOR_REMINDER_SECONDS, {}).get(entity_id)
        try:
            return min(86400, max(1, int(value))) if value is not None else self.reminder_seconds
        except (TypeError, ValueError):
            return self.reminder_seconds

    @property
    def notify_on_close(self) -> bool:
        return bool(self.options.get(CONF_NOTIFY_ON_CLOSE, DEFAULT_NOTIFY_ON_CLOSE))

    @property
    def escalation_seconds(self) -> int:
        try:
            return min(
                86400,
                max(0, int(self.options.get(CONF_ESCALATION_SECONDS, DEFAULT_ESCALATION_SECONDS))),
            )
        except (TypeError, ValueError):
            return DEFAULT_ESCALATION_SECONDS

    def _in_quiet_hours(self) -> bool:
        start = self.options.get(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START)
        end = self.options.get(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END)
        if not start or not end:
            return False
        try:
            start_time = datetime_time.fromisoformat(start)
            end_time = datetime_time.fromisoformat(end)
        except ValueError:
            return False
        now = dt_util.now().time()
        return (
            start_time <= now < end_time
            if start_time < end_time
            else now >= start_time or now < end_time
        )

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
    def delivery_mode(self) -> str:
        mode = str(self.options.get(CONF_DELIVERY_MODE, DEFAULT_DELIVERY_MODE))
        return mode if mode in VALID_DELIVERY_MODES else DEFAULT_DELIVERY_MODE

    @property
    def sound_enabled(self) -> bool:
        return bool(self.options.get(CONF_SOUND_ENABLED, DEFAULT_SOUND_ENABLED))

    @property
    def sound_name(self) -> str:
        return str(self.options.get(CONF_SOUND_NAME, DEFAULT_SOUND_NAME))

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

    @property
    def target_settings(self) -> dict[str, dict[str, Any]]:
        raw = self.options.get(CONF_TARGET_SETTINGS, {}) or {}
        if not isinstance(raw, dict):
            return {}
        settings: dict[str, dict[str, Any]] = {}
        for target, value in raw.items():
            if isinstance(value, dict):
                mode = str(value.get(CONF_DELIVERY_MODE, self.delivery_mode))
                if mode not in VALID_DELIVERY_MODES:
                    mode = self.delivery_mode
                settings[target] = {
                    CONF_DELIVERY_MODE: mode,
                    CONF_SOUND_ENABLED: bool(value.get(CONF_SOUND_ENABLED, self.sound_enabled)),
                    CONF_SOUND_NAME: str(value.get(CONF_SOUND_NAME, self.sound_name)),
                }
        return settings

    async def async_initialize(self) -> None:
        _LOGGER.debug("Initializing Home Sensor Notifications entry %s", self.entry.entry_id)
        self._start_listener()

        for entity_id in self.monitored_sensors:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == STATE_OPEN:
                await self._mark_open(entity_id, send_initial=False)

    async def async_shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        if self.unsub_state_change is not None:
            self.unsub_state_change()
            self.unsub_state_change = None
        for sensor_state in self.open_sensors.values():
            if sensor_state.reminder_cancel is not None:
                sensor_state.reminder_cancel()
            if sensor_state.reminder_task is not None:
                sensor_state.reminder_task.cancel()
        await asyncio.gather(
            *(state.reminder_task for state in self.open_sensors.values() if state.reminder_task),
            return_exceptions=True,
        )
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
            if (
                state is not None
                and state.state == STATE_OPEN
                and entity_id not in self.open_sensors
            ):
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

    async def async_set_enabled(self, enabled: bool) -> None:
        """Persist a switch change using the same options as every other edit."""
        if enabled == self.enabled:
            return
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, CONF_ENABLED: enabled},
        )

    @callback
    def _clear_sensor(self, entity_id: str) -> None:
        sensor_state = self.open_sensors.pop(entity_id, None)
        if sensor_state and sensor_state.reminder_cancel is not None:
            sensor_state.reminder_cancel()
        if sensor_state and sensor_state.reminder_task is not None:
            sensor_state.reminder_task.cancel()

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
        else:
            if (
                old_state is not None
                and old_state.state == STATE_OPEN
                and self.notify_on_close
                and self.enabled
            ):
                await self._send_notification(
                    f"{self._friendly_name(entity_id)} closed.",
                    self.notify_targets,
                    entity_id=entity_id,
                )
            self._clear_sensor(entity_id)

    async def _mark_open(self, entity_id: str, send_initial: bool) -> None:
        sensor_state = self.open_sensors.get(entity_id)
        if sensor_state is None:
            sensor_state = OpenSensorState(opened_at=dt_util.utcnow())
            self.open_sensors[entity_id] = sensor_state
        elif sensor_state.reminder_cancel is not None:
            sensor_state.reminder_cancel()
            sensor_state.reminder_cancel = None

        if send_initial and self.enabled and not self._in_quiet_hours():
            await self._send_notification(
                self._render_message(entity_id, is_reminder=False),
                self.notify_targets,
                entity_id=entity_id,
            )

        self._schedule_reminder(entity_id)

    def _schedule_reminder(self, entity_id: str) -> None:
        """Schedule exactly one later callback for an open sensor."""
        if self._shutting_down or entity_id not in self.open_sensors:
            return
        seconds = self.reminder_seconds_for(entity_id)
        _LOGGER.debug("Scheduling reminder for %s in %s seconds", entity_id, seconds)
        self.open_sensors[entity_id].reminder_cancel = async_call_later(
            self.hass,
            timedelta(seconds=seconds),
            lambda _: self._start_reminder_task(entity_id),
        )

    @callback
    def _start_reminder_task(self, entity_id: str) -> None:
        sensor_state = self.open_sensors.get(entity_id)
        if self._shutting_down or sensor_state is None:
            return
        if sensor_state.reminder_task is not None and not sensor_state.reminder_task.done():
            _LOGGER.debug("Skipping overlapping reminder for %s", entity_id)
            return
        sensor_state.reminder_task = self.hass.async_create_task(
            self._async_send_reminder(entity_id),
            f"{DOMAIN}_reminder_{entity_id}",
        )

    async def _async_send_reminder(self, entity_id: str) -> None:
        sensor_state = self.open_sensors.get(entity_id)
        current_state = self.hass.states.get(entity_id)

        if (
            self._shutting_down
            or sensor_state is None
            or current_state is None
            or current_state.state != STATE_OPEN
        ):
            self._clear_sensor(entity_id)
            return
        try:
            if self.enabled and not self._in_quiet_hours():
                critical = (
                    not sensor_state.escalated
                    and self.escalation_seconds > 0
                    and sensor_state.opened_at is not None
                    and (dt_util.utcnow() - sensor_state.opened_at).total_seconds()
                    >= self.escalation_seconds
                )
                await self._send_notification(
                    self._render_message(entity_id, is_reminder=True),
                    self.notify_targets,
                    entity_id=entity_id,
                    delivery_mode_override=DELIVERY_MODE_CRITICAL if critical else None,
                )
                sensor_state.escalated = sensor_state.escalated or critical
        finally:
            sensor_state = self.open_sensors.get(entity_id)
            if sensor_state is not None:
                sensor_state.reminder_task = None
            self._schedule_reminder(entity_id)

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
            fallback = (
                DEFAULT_GLOBAL_REMINDER_MESSAGE if is_reminder else DEFAULT_GLOBAL_OPEN_MESSAGE
            )
            return fallback.format(**context)

    async def _send_notification(
        self,
        message: str,
        targets: list[str],
        *,
        entity_id: str | None = None,
        delivery_mode_override: str | None = None,
    ) -> None:
        if not targets:
            _LOGGER.warning("No notify targets configured for %s", self.entry.title)
            return

        async def send_one(target: str) -> None:
            try:
                async with self._notification_semaphore:
                    await self._send_notification_to_target(
                        target,
                        message,
                        entity_id=entity_id,
                        delivery_mode_override=delivery_mode_override,
                    )
            except HomeAssistantError:
                _LOGGER.exception("Failed to send notification via notify.%s", target)

        await asyncio.gather(*(send_one(target) for target in targets))

    async def _send_notification_to_target(
        self,
        target: str,
        message: str,
        *,
        entity_id: str | None = None,
        delivery_mode_override: str | None = None,
        sound_enabled_override: bool | None = None,
        sound_name_override: str | None = None,
    ) -> None:
        target_config = self.target_settings.get(target, {})
        delivery_mode = self._effective_delivery_mode(
            target,
            str(target_config.get(CONF_DELIVERY_MODE, self.delivery_mode)),
            override=delivery_mode_override,
        )
        sound_enabled = (
            bool(sound_enabled_override)
            if sound_enabled_override is not None
            else bool(target_config.get(CONF_SOUND_ENABLED, self.sound_enabled))
        )
        sound_name = (
            str(sound_name_override)
            if sound_name_override is not None
            else str(target_config.get(CONF_SOUND_NAME, self.sound_name))
        )

        # "Both" is intentionally a single critical notification. Sending two
        # messages with the same mobile-app tag replaces the first visible item.
        critical = delivery_mode in (DELIVERY_MODE_CRITICAL, DELIVERY_MODE_BOTH)
        await self._async_call_notify_service(
            target,
            message,
            self._build_notify_payload(
                target,
                message,
                entity_id=entity_id,
                critical=critical,
                sound_enabled=sound_enabled,
                sound_name=sound_name,
            ),
        )

    async def _async_call_notify_service(
        self, target: str, message: str, payload: dict[str, Any]
    ) -> None:
        if target.startswith("notify."):
            await self.hass.services.async_call(
                NOTIFY_DOMAIN,
                NOTIFY_SEND_MESSAGE,
                payload,
                target={"entity_id": target},
                blocking=True,
            )
            return
        await self.hass.services.async_call(
            NOTIFY_DOMAIN,
            target,
            payload,
            blocking=True,
        )

    def _build_notify_payload(
        self,
        target: str,
        message: str,
        *,
        entity_id: str | None,
        critical: bool,
        sound_enabled: bool,
        sound_name: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "title": self.entry.title,
        }

        if not self._is_mobile_app_target(target):
            return payload

        data: dict[str, Any] = {
            "tag": self._notification_tag(target, entity_id),
        }

        if critical:
            data.update(
                {
                    "ttl": 0,
                    "priority": "high",
                    "channel": "alarm_stream",
                    "media_stream": "alarm_stream",
                }
            )
            ios_sound: dict[str, Any] = {
                "critical": 1,
                "volume": 1.0,
                "name": sound_name if sound_enabled and sound_name else "default",
            }
            data["push"] = {"sound": ios_sound}
        else:
            if sound_enabled:
                data["push"] = {"sound": sound_name or "default"}

        payload["data"] = data
        return payload

    def _effective_delivery_mode(
        self,
        target: str,
        configured_mode: str,
        *,
        override: str | None = None,
    ) -> str:
        delivery_mode = override if override is not None else configured_mode
        if delivery_mode not in VALID_DELIVERY_MODES:
            delivery_mode = self.delivery_mode
        if not self._supports_critical_notifications(target):
            return DELIVERY_MODE_NORMAL
        return delivery_mode

    def _notification_tag(self, target: str, entity_id: str | None) -> str:
        if entity_id is None:
            return f"{DOMAIN}_{target}"
        normalized_entity_id = entity_id.replace(".", "_")
        return f"{DOMAIN}_{target}_{normalized_entity_id}"

    def _supports_critical_notifications(self, target: str) -> bool:
        # The legacy mobile_app notify service is the documented path for the
        # platform-specific critical payload. Generic notify entities receive a
        # standards-compatible notify.send_message call instead.
        return target.startswith("mobile_app_")

    def _is_mobile_app_target(self, target: str) -> bool:
        return target.startswith("mobile_app_")

    def _friendly_name(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        if state is None:
            return entity_id
        return cast(str, state.attributes.get("friendly_name", entity_id))


def _available_notify_targets(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return modern notify entities as well as supported legacy services."""
    services = hass.services.async_services().get(NOTIFY_DOMAIN, {})
    targets: list[dict[str, str]] = []
    for state in sorted(hass.states.async_all(NOTIFY_DOMAIN), key=lambda item: item.entity_id):
        entity_id = state.entity_id
        targets.append(
            {
                "entity_id": entity_id,
                "name": str(state.attributes.get("friendly_name", entity_id)),
                "supports_mobile_app": "false",
            }
        )
    for service_name in sorted(
        service_name
        for service_name in services
        if service_name != "send_message" and not service_name.startswith("__")
    ):
        targets.append(
            {
                "entity_id": service_name,
                "name": service_name,
                "supports_mobile_app": str(service_name.startswith("mobile_app_")).lower(),
            }
        )
    return targets


def _available_binary_sensor_ids(hass: HomeAssistant) -> set[str]:
    return {item["entity_id"] for item in _available_binary_sensors(hass)}


def _available_notify_target_ids(hass: HomeAssistant) -> set[str]:
    return {item["entity_id"] for item in _available_notify_targets(hass)}


def _configuration_issues(
    hass: HomeAssistant, manager: HomeSensorNotificationsManager
) -> list[str]:
    """Return concise, user-safe configuration problems for the panel."""
    issues: list[str] = []
    missing_sensors = set(manager.monitored_sensors) - _available_binary_sensor_ids(hass)
    missing_targets = set(manager.notify_targets) - _available_notify_target_ids(hass)
    if missing_sensors:
        issues.append(f"{len(missing_sensors)} configured sensor(s) are unavailable.")
    if missing_targets:
        issues.append(f"{len(missing_targets)} configured notification target(s) are unavailable.")
    if not manager.monitored_sensors:
        issues.append("Choose at least one monitored sensor.")
    if not manager.notify_targets:
        issues.append("Choose at least one notification target.")
    return issues


def _clean_panel_config(
    hass: HomeAssistant,
    manager: HomeSensorNotificationsManager,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Validate untrusted panel data, then allow only known/current config IDs."""
    cleaned = PANEL_CONFIG_SCHEMA(config)
    known_sensors = _available_binary_sensor_ids(hass) | set(manager.monitored_sensors)
    known_targets = _available_notify_target_ids(hass) | set(manager.notify_targets)
    invalid_sensors = set(cleaned[CONF_MONITORED_SENSORS]) - known_sensors
    invalid_targets = set(cleaned[CONF_NOTIFY_TARGETS]) - known_targets
    if invalid_sensors:
        raise vol.Invalid(f"Unknown monitored sensor: {sorted(invalid_sensors)[0]}")
    if invalid_targets:
        raise vol.Invalid(f"Unknown notification target: {sorted(invalid_targets)[0]}")
    if len(set(cleaned[CONF_MONITORED_SENSORS])) != len(cleaned[CONF_MONITORED_SENSORS]):
        raise vol.Invalid("Monitored sensors must not contain duplicates")
    if len(set(cleaned[CONF_NOTIFY_TARGETS])) != len(cleaned[CONF_NOTIFY_TARGETS]):
        raise vol.Invalid("Notification targets must not contain duplicates")
    if set(cleaned[CONF_SENSOR_MESSAGES]) - set(cleaned[CONF_MONITORED_SENSORS]):
        raise vol.Invalid("Per-sensor messages must refer to monitored sensors")
    if set(cleaned[CONF_TARGET_SETTINGS]) - set(cleaned[CONF_NOTIFY_TARGETS]):
        raise vol.Invalid("Target settings must refer to selected notification targets")
    return cleaned


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


def _has_loaded_entries(hass: HomeAssistant) -> bool:
    return any(
        get_manager(entry) is not None for entry in hass.config_entries.async_entries(DOMAIN)
    )


def _register_websocket_commands(hass: HomeAssistant) -> None:
    if hass.data[DOMAIN].get(DATA_WEBSOCKET_REGISTERED):
        return

    @websocket_api.require_admin
    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_GET_CONFIG})
    @websocket_api.async_response
    async def websocket_get_config(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_configured", "Integration is not configured")
            return

        entry = entries[0]
        manager = get_manager(entry)
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Integration is not loaded")
            return
        connection.send_result(
            msg["id"],
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "config": {
                    CONF_MONITORED_SENSORS: manager.monitored_sensors,
                    CONF_NOTIFY_TARGETS: manager.notify_targets,
                    CONF_REMINDER_SECONDS: manager.reminder_seconds,
                    CONF_ENABLED: manager.enabled,
                    CONF_NOTIFICATION_MODE: manager.notification_mode,
                    CONF_GLOBAL_OPEN_MESSAGE: manager.global_open_message,
                    CONF_GLOBAL_REMINDER_MESSAGE: manager.global_reminder_message,
                    CONF_SENSOR_MESSAGES: manager.sensor_messages,
                    CONF_DELIVERY_MODE: manager.delivery_mode,
                    CONF_SOUND_ENABLED: manager.sound_enabled,
                    CONF_SOUND_NAME: manager.sound_name,
                    CONF_TARGET_SETTINGS: manager.target_settings,
                },
                "available_sensors": _available_binary_sensors(hass),
                "available_notify_targets": _available_notify_targets(hass),
                "open_sensors": sorted(manager.open_sensors.keys()),
                "issues": _configuration_issues(hass, manager),
                "updated_at": dt_util.utcnow().isoformat(),
            },
        )

    @websocket_api.require_admin
    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_TYPE_SAVE_CONFIG,
            vol.Required("config"): PANEL_CONFIG_SCHEMA,
        }
    )
    @websocket_api.async_response
    async def websocket_save_config(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "not_configured", "Integration is not configured")
            return

        entry = entries[0]
        manager = get_manager(entry)
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Integration is not loaded")
            return
        try:
            cleaned = _clean_panel_config(hass, manager, msg["config"])
        except vol.Invalid as err:
            connection.send_error(msg["id"], "invalid_config", str(err))
            return
        hass.config_entries.async_update_entry(entry, options=cleaned)
        connection.send_result(msg["id"], {"saved": True})

    websocket_api.async_register_command(hass, websocket_get_config)
    websocket_api.async_register_command(hass, websocket_save_config)
    hass.data[DOMAIN][DATA_WEBSOCKET_REGISTERED] = True


def _migrate_config_values(values: Mapping[str, Any], *, include_defaults: bool) -> dict[str, Any]:
    """Migrate one config-entry data or options mapping to the current schema."""
    migrated = dict(values)

    if CONF_REMINDER_SECONDS not in migrated:
        if CONF_REMINDER_MINUTES in migrated:
            migrated[CONF_REMINDER_SECONDS] = max(
                1,
                int(migrated[CONF_REMINDER_MINUTES]) * 60,
            )
        elif include_defaults:
            migrated[CONF_REMINDER_SECONDS] = DEFAULT_REMINDER_SECONDS
    migrated.pop(CONF_REMINDER_MINUTES, None)

    if include_defaults:
        migrated.setdefault(CONF_DELIVERY_MODE, DEFAULT_DELIVERY_MODE)
        migrated.setdefault(CONF_SOUND_ENABLED, DEFAULT_SOUND_ENABLED)
        migrated.setdefault(CONF_SOUND_NAME, DEFAULT_SOUND_NAME)
        migrated.setdefault(CONF_TARGET_SETTINGS, {})

    return migrated


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries created by earlier integration versions."""
    if entry.version > CONFIG_ENTRY_VERSION:
        _LOGGER.error(
            "Cannot migrate config entry from newer version %s.%s",
            entry.version,
            entry.minor_version,
        )
        return False

    if entry.version == CONFIG_ENTRY_VERSION and entry.minor_version >= CONFIG_ENTRY_MINOR_VERSION:
        return True

    try:
        migrated_data = _migrate_config_values(entry.data, include_defaults=True)
        migrated_options = _migrate_config_values(entry.options, include_defaults=False)
    except (TypeError, ValueError):
        _LOGGER.exception(
            "Unable to migrate config entry %s from version %s.%s",
            entry.entry_id,
            entry.version,
            entry.minor_version,
        )
        return False

    hass.config_entries.async_update_entry(
        entry,
        data=migrated_data,
        options=migrated_options,
        version=CONFIG_ENTRY_VERSION,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
    )
    _LOGGER.info(
        "Migrated config entry %s to version %s.%s",
        entry.entry_id,
        CONFIG_ENTRY_VERSION,
        CONFIG_ENTRY_MINOR_VERSION,
    )
    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await panel_helpers.async_register_static_path(hass)
    _register_websocket_commands(hass)

    async def async_send_test_notification(call: ServiceCall) -> None:
        if call.context.user_id is not None:
            user = await hass.auth.async_get_user(call.context.user_id)
            if user is None or not user.is_admin:
                raise Unauthorized(context=call.context)

        manager_entries = [
            manager
            for entry in hass.config_entries.async_entries(DOMAIN)
            if (manager := get_manager(entry)) is not None
        ]
        if not manager_entries:
            _LOGGER.warning("No Home Sensor Notifications entry is configured")
            return

        manager = manager_entries[0]
        sensor = call.data.get(ATTR_SENSOR)
        if sensor is not None and sensor not in (
            _available_binary_sensor_ids(hass) | set(manager.monitored_sensors)
        ):
            raise vol.Invalid(f"Unknown binary sensor: {sensor}")
        targets = list(call.data.get(ATTR_TARGETS, manager.notify_targets))
        known_targets = _available_notify_target_ids(hass) | set(manager.notify_targets)
        unknown_targets = set(targets) - known_targets
        if unknown_targets:
            raise vol.Invalid(f"Unknown notification target: {sorted(unknown_targets)[0]}")
        message = call.data.get(ATTR_MESSAGE)
        delivery_mode = call.data.get(ATTR_DELIVERY_MODE, manager.delivery_mode)
        sound_enabled = bool(call.data.get(ATTR_SOUND_ENABLED, manager.sound_enabled))
        sound_name = str(call.data.get(ATTR_SOUND_NAME, manager.sound_name))

        if message is None:
            if sensor is None:
                message = f"Test notification from {manager.entry.title}."
            else:
                message = manager._render_message(sensor, is_reminder=False)

        failures: list[str] = []
        for target in targets:
            try:
                await manager._send_notification_to_target(
                    target,
                    message,
                    entity_id=sensor,
                    delivery_mode_override=delivery_mode,
                    sound_enabled_override=sound_enabled,
                    sound_name_override=sound_name,
                )
            except HomeAssistantError:
                _LOGGER.exception("Test notification failed for target %s", target)
                failures.append(target)
        if failures:
            raise HomeAssistantError(f"Test notification failed for {len(failures)} target(s)")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TEST_NOTIFICATION,
        async_send_test_notification,
        schema=SERVICE_SCHEMA,
    )
    hass.data[DOMAIN][DATA_SERVICE_REGISTERED] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = HomeSensorNotificationsManager(hass, entry)
    entry.runtime_data = manager
    await manager.async_initialize()
    entry.async_on_unload(manager.async_shutdown)
    await panel_helpers.async_register_panel(hass, entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager = get_manager(entry)
        if manager is not None:
            await manager.async_shutdown()
        entry.runtime_data = None
        if not _has_loaded_entries(hass):
            panel_helpers.async_unregister_panel(hass)
            if hass.data[DOMAIN].pop(DATA_SERVICE_REGISTERED, False):
                hass.services.async_remove(DOMAIN, SERVICE_SEND_TEST_NOTIFICATION)
    return unload_ok
