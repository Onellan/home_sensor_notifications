"""Typed runtime-data access for the integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from . import HomeSensorNotificationsManager


def get_manager(entry: ConfigEntry) -> HomeSensorNotificationsManager | None:
    """Return runtime data only when an entry completed setup."""
    manager = getattr(entry, "runtime_data", None)
    return manager if manager is not None else None
