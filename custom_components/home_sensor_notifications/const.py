from __future__ import annotations

DOMAIN = "home_sensor_notifications"
NAME = "Home Sensor Notifications"
PLATFORMS = ["switch"]

CONF_MONITORED_SENSORS = "monitored_sensors"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_REMINDER_MINUTES = "reminder_minutes"
CONF_ENABLED = "enabled"
CONF_NOTIFICATION_MODE = "notification_mode"
CONF_GLOBAL_OPEN_MESSAGE = "global_open_message"
CONF_GLOBAL_REMINDER_MESSAGE = "global_reminder_message"
CONF_SENSOR_MESSAGES = "sensor_messages"

DEFAULT_TITLE = NAME
DEFAULT_REMINDER_MINUTES = 30
DEFAULT_NOTIFICATION_MODE = "global"
DEFAULT_GLOBAL_OPEN_MESSAGE = "{sensor} opened."
DEFAULT_GLOBAL_REMINDER_MESSAGE = "Reminder: {sensor} is still open."

STATE_OPEN = "on"
STATE_CLOSED = "off"

SERVICE_SEND_TEST_NOTIFICATION = "send_test_notification"

ATTR_SENSOR = "sensor"
ATTR_TARGETS = "targets"
ATTR_MESSAGE = "message"

NOTIFY_DOMAIN = "notify"
NOTIFY_SEND_MESSAGE = "send_message"

PANEL_URL_PATH = "home-sensor-notifications"
PANEL_TITLE = NAME
PANEL_ICON = "mdi:door-open"
STATIC_PANEL_DIR = "static"
PANEL_JS_FILENAME = "home-sensor-notifications-panel.js"
PANEL_WEBCOMPONENT = "home-sensor-notifications-panel"
PANEL_CONFIG_KEY_ENTRY_ID = "entry_id"

WS_TYPE_GET_CONFIG = f"{DOMAIN}/get_config"
WS_TYPE_SAVE_CONFIG = f"{DOMAIN}/save_config"
