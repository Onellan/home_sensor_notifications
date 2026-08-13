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

test("panel places live sensor status and actions before configuration cards", () => {
  const source = loadPanelSource();
  const header = source.indexOf('<header class="hero">');
  const openSensors = source.indexOf('<section class="priority-row"');
  const actions = source.indexOf('<footer class="footer">');
  const configuration = source.indexOf('<div class="grid"><section class="card"><h2>Monitored sensors</h2>');

  assert.ok(header >= 0);
  assert.ok(openSensors > header);
  assert.ok(actions > openSensors);
  assert.ok(configuration > actions);
  assert.match(source, /\.grid \{ grid-template-columns:minmax\(0,1\.2fr\) minmax\(0,1fr\)/);
  assert.match(source, /@media \(max-width:760px\) \{ \.grid \{ grid-template-columns:1fr/);
});
