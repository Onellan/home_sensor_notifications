const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadPanel() {
  const elements = new Map();
  const context = {
    HTMLElement: class {},
    customElements: {
      define(name, element) {
        elements.set(name, element);
      },
    },
    clearTimeout,
    console,
    setTimeout,
  };
  const source = fs.readFileSync(
    path.join(
      __dirname,
      "..",
      "custom_components",
      "home_sensor_notifications",
      "static",
      "home-sensor-notifications-panel.js",
    ),
    "utf8",
  );
  vm.runInNewContext(source, context);
  return elements.get("home-sensor-notifications-panel");
}

test("panel escapes Home Assistant and stored configuration values", () => {
  const Panel = loadPanel();
  const panel = new Panel();
  panel.shadowRoot = {
    innerHTML: "",
    getElementById() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };

  const maliciousTag = '<img src=x onerror="globalThis.compromised=true">';
  const maliciousAttribute = 'binary_sensor.door" autofocus onfocus="globalThis.compromised=true';
  panel._loading = false;
  panel._saving = false;
  panel._error = maliciousTag;
  panel._toast = maliciousTag;
  panel._availableSensors = [
    {
      entity_id: maliciousAttribute,
      name: maliciousTag,
      device_class: "door",
      state: "on",
    },
  ];
  panel._availableNotifyTargets = [
    {
      entity_id: 'mobile_app_phone" onclick="globalThis.compromised=true',
      name: maliciousTag,
      supports_mobile_app: "true",
    },
  ];
  panel._openSensors = [maliciousAttribute];
  panel._config = {
    monitored_sensors: [maliciousAttribute],
    notify_targets: ['mobile_app_phone" onclick="globalThis.compromised=true'],
    reminder_seconds: 30,
    enabled: true,
    notification_mode: "per_sensor",
    global_open_message: maliciousTag,
    global_reminder_message: maliciousTag,
    sensor_messages: {
      [maliciousAttribute]: {
        open_message: maliciousTag,
        reminder_message: maliciousTag,
      },
    },
    delivery_mode: "normal",
    sound_enabled: true,
    sound_name: 'default" autofocus onfocus="globalThis.compromised=true',
    target_settings: {},
  };

  panel.render();

  assert.ok(panel.shadowRoot.innerHTML.includes("&lt;img src=x onerror=&quot;"));
  assert.ok(!panel.shadowRoot.innerHTML.includes(maliciousTag));
  assert.ok(!panel.shadowRoot.innerHTML.includes('data-entity-id="binary_sensor.door" autofocus'));
  assert.ok(!panel.shadowRoot.innerHTML.includes('value="default" autofocus'));
});

