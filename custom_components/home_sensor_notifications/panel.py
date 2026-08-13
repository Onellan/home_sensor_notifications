"""Custom-panel static asset and sidebar lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.frontend import async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.panel_custom import async_register_panel as ha_async_register_panel
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    PANEL_CONFIG_KEY_ENTRY_ID,
    PANEL_ICON,
    PANEL_JS_FILENAME,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PANEL_WEBCOMPONENT,
    STATIC_PANEL_DIR,
)

DATA_PANEL_REGISTERED = "panel_registered"
PANEL_VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))[
    "version"
]


async def async_register_static_path(hass: HomeAssistant) -> None:
    """Register the panel files once per Home Assistant lifecycle."""
    panel_dir = Path(__file__).parent / STATIC_PANEL_DIR
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"/api/{DOMAIN}/static", str(panel_dir), False)]
    )


async def async_register_panel(hass: HomeAssistant, entry_id: str) -> None:
    """Register a single admin-only sidebar panel."""
    if hass.data[DOMAIN].get(DATA_PANEL_REGISTERED):
        return
    panel_url = f"/api/{DOMAIN}/static"
    await ha_async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_WEBCOMPONENT,
        js_url=f"{panel_url}/{PANEL_JS_FILENAME}?v={PANEL_VERSION}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        config={PANEL_CONFIG_KEY_ENTRY_ID: entry_id},
        require_admin=True,
    )
    hass.data[DOMAIN][DATA_PANEL_REGISTERED] = True


@callback
def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the panel only after the final entry unloads."""
    if hass.data[DOMAIN].pop(DATA_PANEL_REGISTERED, False):
        async_remove_panel(hass, PANEL_URL_PATH)
