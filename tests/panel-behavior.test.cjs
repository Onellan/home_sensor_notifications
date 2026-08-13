const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadPanelSource() {
  return fs.readFileSync(path.join(__dirname, "..", "custom_components", "home_sensor_notifications", "static", "home-sensor-notifications-panel.js"), "utf8");
}

test("panel form validation rejects incomplete saves", () => {
  const source = loadPanelSource().replace(/customElements\.define[\s\S]*/, "globalThis.PanelFormState = PanelFormState;");
  const context = { globalThis: {}, HTMLElement: class {}, customElements: { define() {} } };
  vm.runInNewContext(source, context);
  const form = new context.globalThis.PanelFormState();
  assert.equal(form.validate({ monitored_sensors: [], notify_targets: [], reminder_seconds: 0 }), false);
  assert.match(form.validation.sensors, /Choose/);
  assert.match(form.validation.targets, /Choose/);
  assert.match(form.validation.reminder_seconds, /1 to 86,400/);
});

test("panel source versions in-flight loads and disconnect cleanup", () => {
  const source = loadPanelSource();
  assert.match(source, /\+\+this\._requestId/);
  assert.match(source, /this\._connected = false/);
  assert.match(source, /clearTimeout\(this\._toastTimer\)/);
  assert.match(source, /if \(!this\._connected \|\| requestId !== this\._requestId\) return/);
});
