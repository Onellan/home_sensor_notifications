from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_sensor_notifications import async_migrate_entry
from custom_components.home_sensor_notifications.const import (
    CONF_DELIVERY_MODE,
    CONF_REMINDER_MINUTES,
    CONF_REMINDER_SECONDS,
    CONF_SOUND_ENABLED,
    CONF_SOUND_NAME,
    CONF_TARGET_SETTINGS,
    DEFAULT_DELIVERY_MODE,
    DEFAULT_SOUND_ENABLED,
    DEFAULT_SOUND_NAME,
    DOMAIN,
)


@pytest.mark.parametrize(
    ("version", "minor_version", "data", "options", "expected_seconds"),
    [
        (1, 1, {CONF_REMINDER_MINUTES: 5}, {}, 300),
        (2, 1, {CONF_REMINDER_MINUTES: 30}, {}, 1800),
        (3, 0, {CONF_REMINDER_MINUTES: 2}, {CONF_REMINDER_MINUTES: 3}, 180),
    ],
)
async def test_migrate_entry_to_3_1(
    hass,
    version: int,
    minor_version: int,
    data: dict[str, Any],
    options: dict[str, Any],
    expected_seconds: int,
) -> None:
    """All historical schemas migrate to seconds and delivery defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options=options,
        version=version,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 3
    assert entry.minor_version == 1
    assert CONF_REMINDER_MINUTES not in entry.data
    assert CONF_REMINDER_MINUTES not in entry.options
    assert entry.options.get(CONF_REMINDER_SECONDS, entry.data[CONF_REMINDER_SECONDS]) == expected_seconds
    assert entry.data[CONF_DELIVERY_MODE] == DEFAULT_DELIVERY_MODE
    assert entry.data[CONF_SOUND_ENABLED] is DEFAULT_SOUND_ENABLED
    assert entry.data[CONF_SOUND_NAME] == DEFAULT_SOUND_NAME
    assert entry.data[CONF_TARGET_SETTINGS] == {}


async def test_migrate_entry_preserves_existing_seconds_and_settings(hass) -> None:
    """Migration does not overwrite values already stored by a newer schema."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REMINDER_SECONDS: 45,
            CONF_DELIVERY_MODE: "critical",
            CONF_SOUND_ENABLED: True,
            CONF_SOUND_NAME: "doorbell.wav",
            CONF_TARGET_SETTINGS: {"mobile_app_phone": {CONF_DELIVERY_MODE: "both"}},
        },
        version=3,
        minor_version=0,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.data[CONF_REMINDER_SECONDS] == 45
    assert entry.data[CONF_DELIVERY_MODE] == "critical"
    assert entry.data[CONF_SOUND_ENABLED] is True
    assert entry.data[CONF_SOUND_NAME] == "doorbell.wav"


async def test_migrate_entry_rejects_newer_major_version(hass) -> None:
    """Downgrades fail closed instead of corrupting newer config data."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, version=4, minor_version=0)
    entry.add_to_hass(hass)

    assert not await async_migrate_entry(hass, entry)
    assert entry.version == 4

