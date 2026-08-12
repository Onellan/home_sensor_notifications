from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized

from custom_components.home_sensor_notifications import (
    _async_register_panel,
    _async_unregister_panel,
    async_setup,
)
from custom_components.home_sensor_notifications.const import (
    DOMAIN,
    SERVICE_SEND_TEST_NOTIFICATION,
    WS_TYPE_GET_CONFIG,
    WS_TYPE_SAVE_CONFIG,
)


async def test_websocket_configuration_requires_admin(hass, hass_ws_client) -> None:
    """A normal authenticated user cannot read or modify integration config."""
    with patch(
        "custom_components.home_sensor_notifications._async_register_static_path",
        new=AsyncMock(),
    ):
        assert await async_setup(hass, {})

    user = await hass.auth.async_create_user("non-admin")
    refresh_token = await hass.auth.async_create_refresh_token(
        user,
        client_id="https://example.com",
    )
    access_token = hass.auth.async_create_access_token(refresh_token)
    client = await hass_ws_client(hass, access_token)

    for message in (
        {"type": WS_TYPE_GET_CONFIG},
        {"type": WS_TYPE_SAVE_CONFIG, "config": {}},
    ):
        await client.send_json_auto_id(message)
        response = await client.receive_json()
        assert response["success"] is False
        assert response["error"]["code"] == "unauthorized"

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_TEST_NOTIFICATION,
            {},
            blocking=True,
            context=Context(user_id=user.id),
        )


async def test_panel_registration_is_idempotent_across_reload() -> None:
    """Setup/reload/unload cycles register one panel at a time."""
    hass = Mock()
    hass.data = {DOMAIN: {}}

    with (
        patch(
            "custom_components.home_sensor_notifications.async_register_panel",
            new=AsyncMock(),
        ) as register_panel,
        patch(
            "custom_components.home_sensor_notifications.async_remove_panel",
        ) as remove_panel,
    ):
        await _async_register_panel(hass, "entry-id")
        await _async_register_panel(hass, "entry-id")
        register_panel.assert_awaited_once()

        _async_unregister_panel(hass)
        _async_unregister_panel(hass)
        remove_panel.assert_called_once()

        await _async_register_panel(hass, "entry-id")
        assert register_panel.await_count == 2
