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
CONF_DELIVERY_MODE = "delivery_mode"
CONF_SOUND_ENABLED = "sound_enabled"
CONF_SOUND_NAME = "sound_name"
CONF_TARGET_SETTINGS = "target_settings"

DEFAULT_TITLE = NAME
DEFAULT_REMINDER_MINUTES = 30
DEFAULT_NOTIFICATION_MODE = "global"
DEFAULT_GLOBAL_OPEN_MESSAGE = "{sensor} opened."
DEFAULT_GLOBAL_REMINDER_MESSAGE = "Reminder: {sensor} is still open."
DEFAULT_DELIVERY_MODE = "normal"
DEFAULT_SOUND_ENABLED = False
DEFAULT_SOUND_NAME = "default"

DELIVERY_MODE_NORMAL = "normal"
DELIVERY_MODE_CRITICAL = "critical"
DELIVERY_MODE_BOTH = "both"
VALID_DELIVERY_MODES = [DELIVERY_MODE_NORMAL, DELIVERY_MODE_CRITICAL, DELIVERY_MODE_BOTH]

STATE_OPEN = "on"
STATE_CLOSED = "off"

SERVICE_SEND_TEST_NOTIFICATION = "send_test_notification"

ATTR_SENSOR = "sensor"
ATTR_TARGETS = "targets"
ATTR_MESSAGE = "message"
ATTR_DELIVERY_MODE = "delivery_mode"
ATTR_SOUND_NAME = "sound_name"
ATTR_SOUND_ENABLED = "sound_enabled"

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
