"""Redacted diagnostics for Home Sensor Notifications."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MONITORED_SENSORS, CONF_NOTIFY_TARGETS, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return operational state without notification messages, names, or target IDs."""
    manager = getattr(entry, "runtime_data", None)
    options = {**entry.data, **entry.options}
    monitored = options.get(CONF_MONITORED_SENSORS, [])
    targets = options.get(CONF_NOTIFY_TARGETS, [])
    return {
        "configured_sensor_count": len(monitored),
        "configured_target_count": len(targets),
        "available_sensor_count": sum(
            hass.states.get(entity_id) is not None for entity_id in monitored
        ),
        "available_target_count": sum(
            entity_id.startswith("notify.") and hass.states.get(entity_id) is not None
            for entity_id in targets
        ),
        "enabled": bool(options.get("enabled", True)),
        "open_sensor_count": len(getattr(manager, "open_sensors", {})),
        "runtime_loaded": manager is not None,
        "integration": DOMAIN,
    }
