from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLED
from .runtime import get_manager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([HomeSensorNotificationsEnabledSwitch(hass, entry)], True)


class HomeSensorNotificationsEnabledSwitch(SwitchEntity):
    """Switch entity to enable/disable notifications."""

    _attr_has_entity_name = True
    _attr_name = "Enabled"
    _attr_icon = "mdi:doorbell"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_enabled"
        self._attr_translation_key = "enabled"
        self._attr_is_on = entry.options.get(CONF_ENABLED, entry.data.get(CONF_ENABLED, True))

    @property
    def available(self) -> bool:
        """Expose a configuration problem rather than a synthetic service device."""
        manager = get_manager(self.entry)
        return manager is not None and bool(manager.monitored_sensors and manager.notify_targets)

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        manager = get_manager(self.entry)
        if manager is not None:
            await manager.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        manager = get_manager(self.entry)
        if manager is not None:
            await manager.async_set_enabled(False)
        self.async_write_ha_state()
