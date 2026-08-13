from __future__ import annotations

from unittest.mock import patch

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_sensor_notifications import (
    HomeSensorNotificationsManager,
    _available_notify_targets,
    _clean_panel_config,
)
from custom_components.home_sensor_notifications.const import (
    CONF_DELIVERY_MODE,
    CONF_ENABLED,
    CONF_GLOBAL_OPEN_MESSAGE,
    CONF_GLOBAL_REMINDER_MESSAGE,
    CONF_MONITORED_SENSORS,
    CONF_NOTIFICATION_MODE,
    CONF_NOTIFY_TARGETS,
    CONF_REMINDER_SECONDS,
    CONF_SENSOR_MESSAGES,
    CONF_SOUND_ENABLED,
    CONF_SOUND_NAME,
    CONF_TARGET_SETTINGS,
    DELIVERY_MODE_NORMAL,
    DOMAIN,
    NOTIFY_DOMAIN,
    NOTIFY_SEND_MESSAGE,
)


def _config(**overrides):
    config = {
        CONF_MONITORED_SENSORS: ["binary_sensor.front_door"],
        CONF_NOTIFY_TARGETS: ["mobile_app_phone"],
        CONF_REMINDER_SECONDS: 60,
        CONF_ENABLED: True,
        CONF_NOTIFICATION_MODE: "global",
        CONF_GLOBAL_OPEN_MESSAGE: "{sensor} opened.",
        CONF_GLOBAL_REMINDER_MESSAGE: "{sensor} is still open.",
        CONF_SENSOR_MESSAGES: {},
        CONF_DELIVERY_MODE: DELIVERY_MODE_NORMAL,
        CONF_SOUND_ENABLED: False,
        CONF_SOUND_NAME: "default",
        CONF_TARGET_SETTINGS: {},
    }
    config.update(overrides)
    return config


def _manager(hass, **overrides) -> HomeSensorNotificationsManager:
    entry = MockConfigEntry(domain=DOMAIN, data=_config(**overrides))
    entry.add_to_hass(hass)
    return HomeSensorNotificationsManager(hass, entry)


async def test_modern_notify_entity_is_discovered_and_uses_send_message(hass) -> None:
    hass.states.async_set(
        "notify.household", "2026-08-13T10:00:00+00:00", {"friendly_name": "Household"}
    )
    manager = _manager(hass, **{CONF_NOTIFY_TARGETS: ["notify.household"]})

    targets = _available_notify_targets(hass)
    assert {item["entity_id"] for item in targets} == {"notify.household"}

    calls = []

    async def capture(call) -> None:
        calls.append(call)

    hass.services.async_register(NOTIFY_DOMAIN, NOTIFY_SEND_MESSAGE, capture)
    await manager._send_notification_to_target("notify.household", "Door opened")
    await hass.async_block_till_done()

    assert calls[0].domain == NOTIFY_DOMAIN
    assert calls[0].service == NOTIFY_SEND_MESSAGE
    assert calls[0].data == {
        "entity_id": "notify.household",
        "message": "Door opened",
        "title": entry_title(manager),
    }


def entry_title(manager: HomeSensorNotificationsManager) -> str:
    return manager.entry.title


async def test_legacy_mobile_app_service_retains_platform_payload(hass) -> None:
    manager = _manager(hass)
    calls = []

    async def capture(call) -> None:
        calls.append(call)

    hass.services.async_register(NOTIFY_DOMAIN, "mobile_app_phone", capture)
    await manager._send_notification_to_target(
        "mobile_app_phone",
        "Door opened",
        delivery_mode_override="critical",
        sound_enabled_override=True,
    )
    await hass.async_block_till_done()

    payload = calls[0].data
    assert calls[0].domain == NOTIFY_DOMAIN
    assert calls[0].service == "mobile_app_phone"
    assert payload["data"]["priority"] == "high"
    assert payload["data"]["push"]["sound"]["critical"] == 1


async def test_both_delivery_mode_sends_one_critical_mobile_notification(hass) -> None:
    manager = _manager(hass)
    calls = []

    async def capture(call) -> None:
        calls.append(call)

    hass.services.async_register(NOTIFY_DOMAIN, "mobile_app_phone", capture)
    await manager._send_notification_to_target(
        "mobile_app_phone", "Door opened", delivery_mode_override="both"
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["data"]["priority"] == "high"


async def test_options_are_the_authoritative_enabled_state(hass) -> None:
    manager = _manager(hass, **{CONF_ENABLED: False})
    assert manager.enabled is False

    with patch.object(hass.config_entries, "async_update_entry") as update_entry:
        await manager.async_set_enabled(True)

    update_entry.assert_called_once_with(manager.entry, options={CONF_ENABLED: True})


async def test_panel_config_rejects_unknown_or_invalid_values(hass) -> None:
    hass.states.async_set("binary_sensor.front_door", "off", {"device_class": "door"})
    hass.services.async_register(NOTIFY_DOMAIN, "mobile_app_phone", lambda call: None)
    manager = _manager(hass)

    cleaned = _clean_panel_config(hass, manager, _config())
    assert cleaned[CONF_MONITORED_SENSORS] == ["binary_sensor.front_door"]
    assert cleaned[CONF_NOTIFY_TARGETS] == ["mobile_app_phone"]
    with pytest.raises(vol.Invalid, match="Unknown monitored sensor"):
        _clean_panel_config(
            hass, manager, _config(**{CONF_MONITORED_SENSORS: ["binary_sensor.fake"]})
        )
    with pytest.raises(vol.Invalid):
        _clean_panel_config(hass, manager, _config(**{CONF_REMINDER_SECONDS: 0}))
    with pytest.raises(vol.Invalid):
        _clean_panel_config(hass, manager, _config(**{CONF_DELIVERY_MODE: "invalid"}))


async def test_configured_unavailable_target_is_retained_for_safe_editing(hass) -> None:
    manager = _manager(hass, **{CONF_NOTIFY_TARGETS: ["mobile_app_missing"]})
    config = _config(**{CONF_NOTIFY_TARGETS: ["mobile_app_missing"]})
    assert _clean_panel_config(hass, manager, config)[CONF_NOTIFY_TARGETS] == ["mobile_app_missing"]
