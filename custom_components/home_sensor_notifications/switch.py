from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_ENABLED, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([HomeSensorNotificationsEnabledSwitch(hass, entry)], True)


class HomeSensorNotificationsEnabledSwitch(RestoreEntity, SwitchEntity):
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
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": self.entry.title,
            "manufacturer": "Custom",
            "model": "Home Sensor Notifications",
            "entry_type": DeviceEntryType.SERVICE,
        }

    async def async_added_to_hass(self) -> None:
        manager = self.hass.data[DOMAIN][self.entry.entry_id]
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state == "on"
        else:
            self._attr_is_on = manager.enabled

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        await self.hass.data[DOMAIN][self.entry.entry_id].set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        await self.hass.data[DOMAIN][self.entry.entry_id].set_enabled(False)
        self.async_write_ha_state()
