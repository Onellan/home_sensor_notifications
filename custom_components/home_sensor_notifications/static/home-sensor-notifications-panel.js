class HomeSensorNotificationsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._loading = true;
    this._saving = false;
    this._error = "";
    this._toast = "";
    this._availableSensors = [];
    this._availableNotifyTargets = [];
    this._openSensors = [];
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loadedOnce) {
      this._loadedOnce = true;
      this.loadData();
    } else {
      this.render();
    }
  }

  set narrow(value) {
    this._narrow = value;
  }

  set route(value) {
    this._route = value;
  }

  set panel(value) {
    this._panel = value;
  }

  async loadData() {
    this._loading = true;
    this._error = "";
    this.render();
    try {
      const result = await this._hass.callWS({ type: "home_sensor_notifications/get_config" });
      this._config = result.config;
      this._availableSensors = result.available_sensors || [];
      this._availableNotifyTargets = result.available_notify_targets || [];
      this._openSensors = result.open_sensors || [];
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this.render();
    }
  }

  showToast(msg) {
    this._toast = msg;
    this.render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = "";
      this.render();
    }, 2500);
  }

  sensorName(entityId) {
    return this._availableSensors.find((item) => item.entity_id === entityId)?.name || entityId;
  }

  ensureSensorMessage(entityId) {
    if (!this._config.sensor_messages) this._config.sensor_messages = {};
    if (!this._config.sensor_messages[entityId]) {
      this._config.sensor_messages[entityId] = { open_message: "", reminder_message: "" };
    }
    return this._config.sensor_messages[entityId];
  }

  updateSelected(list, value, checked) {
    const current = new Set(list || []);
    if (checked) current.add(value);
    else current.delete(value);
    return [...current].sort();
  }

  async saveConfig() {
    this._saving = true;
    this._error = "";
    this.render();
    try {
      await this._hass.callWS({
        type: "home_sensor_notifications/save_config",
        config: this._config,
      });
      this.showToast("Saved");
      await this.loadData();
    } catch (err) {
      this._error = err?.message || String(err);
      this.render();
    } finally {
      this._saving = false;
      this.render();
    }
  }

  async sendTest() {
    const openSensor = this._config.monitored_sensors?.[0];
    await this._hass.callService("home_sensor_notifications", "send_test_notification", openSensor ? { sensor: openSensor } : {});
    this.showToast("Test notification sent");
  }

  renderCheckboxList(items, selected, onChange, subLabel) {
    return items.map((item) => `
      <label class="check-row">
        <input type="checkbox" data-entity-id="${item.entity_id || item}" ${selected.includes(item.entity_id || item) ? "checked" : ""} data-action="${onChange}">
        <span>
          <strong>${item.name || item}</strong>
          ${subLabel ? `<div class="muted">${subLabel(item)}</div>` : ""}
        </span>
      </label>
    `).join("");
  }

  bindEvents() {
    const root = this.shadowRoot;
    root.querySelectorAll('input[data-action="toggle-sensor"]').forEach((el) => {
      el.addEventListener("change", (ev) => {
        const entityId = ev.currentTarget.dataset.entityId;
        this._config.monitored_sensors = this.updateSelected(this._config.monitored_sensors, entityId, ev.currentTarget.checked);
        this.render();
      });
    });

    root.querySelectorAll('input[data-action="toggle-target"]').forEach((el) => {
      el.addEventListener("change", (ev) => {
        const target = ev.currentTarget.dataset.entityId;
        this._config.notify_targets = this.updateSelected(this._config.notify_targets, target, ev.currentTarget.checked);
        this.render();
      });
    });

    const reminder = root.getElementById("reminder_minutes");
    if (reminder) reminder.addEventListener("input", (ev) => {
      this._config.reminder_minutes = Number(ev.currentTarget.value || 1);
    });

    const enabled = root.getElementById("enabled");
    if (enabled) enabled.addEventListener("change", (ev) => {
      this._config.enabled = ev.currentTarget.checked;
    });

    const mode = root.getElementById("notification_mode");
    if (mode) mode.addEventListener("change", (ev) => {
      this._config.notification_mode = ev.currentTarget.value;
      this.render();
    });

    const openMsg = root.getElementById("global_open_message");
    if (openMsg) openMsg.addEventListener("input", (ev) => {
      this._config.global_open_message = ev.currentTarget.value;
    });

    const remMsg = root.getElementById("global_reminder_message");
    if (remMsg) remMsg.addEventListener("input", (ev) => {
      this._config.global_reminder_message = ev.currentTarget.value;
    });

    root.querySelectorAll("textarea[data-sensor-open]").forEach((el) => {
      el.addEventListener("input", (ev) => {
        const entityId = ev.currentTarget.dataset.sensorOpen;
        this.ensureSensorMessage(entityId).open_message = ev.currentTarget.value;
      });
    });

    root.querySelectorAll("textarea[data-sensor-reminder]").forEach((el) => {
      el.addEventListener("input", (ev) => {
        const entityId = ev.currentTarget.dataset.sensorReminder;
        this.ensureSensorMessage(entityId).reminder_message = ev.currentTarget.value;
      });
    });

    const save = root.getElementById("saveBtn");
    if (save) save.addEventListener("click", () => this.saveConfig());

    const reload = root.getElementById("reloadBtn");
    if (reload) reload.addEventListener("click", () => this.loadData());

    const test = root.getElementById("testBtn");
    if (test) test.addEventListener("click", () => this.sendTest());
  }

  render() {
    const cfg = this._config || {
      monitored_sensors: [],
      notify_targets: [],
      reminder_minutes: 30,
      enabled: true,
      notification_mode: "global",
      global_open_message: "{sensor} opened.",
      global_reminder_message: "Reminder: {sensor} is still open.",
      sensor_messages: {},
    };

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --card-bg: var(--ha-card-background, var(--card-background-color, #fff));
          --border-color: var(--divider-color, rgba(0,0,0,.12));
          display: block;
          padding: 24px;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          box-sizing: border-box;
          font-family: var(--paper-font-body1_-_font-family);
        }
        .wrap { max-width: 1280px; margin: 0 auto; }
        .hero {
          background: linear-gradient(135deg, rgba(33,150,243,.18), rgba(76,175,80,.14));
          border-radius: 24px;
          padding: 24px;
          margin-bottom: 20px;
          border: 1px solid var(--border-color);
        }
        .hero h1 { margin: 0 0 8px; font-size: 30px; }
        .hero p { margin: 0; opacity: .85; }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 20px;
        }
        .card {
          background: var(--card-bg);
          border: 1px solid var(--border-color);
          border-radius: 24px;
          padding: 20px;
          box-shadow: 0 8px 24px rgba(0,0,0,.08);
        }
        h2 { margin: 0 0 14px; font-size: 20px; }
        h3 { margin: 18px 0 10px; font-size: 16px; }
        .muted { color: var(--secondary-text-color); font-size: 12px; }
        .check-list { display: flex; flex-direction: column; gap: 10px; max-height: 320px; overflow: auto; }
        .check-row {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 10px 12px;
          border: 1px solid var(--border-color);
          border-radius: 16px;
          cursor: pointer;
        }
        .field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
        .field input[type="number"], .field select, textarea {
          background: var(--card-bg);
          color: var(--primary-text-color);
          border: 1px solid var(--border-color);
          border-radius: 14px;
          padding: 12px;
          font: inherit;
          box-sizing: border-box;
          width: 100%;
        }
        textarea { min-height: 100px; resize: vertical; }
        .inline { display: flex; gap: 12px; align-items: center; }
        .status-pill {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          border-radius: 999px;
          background: rgba(76,175,80,.14);
          border: 1px solid var(--border-color);
          margin-right: 8px;
          margin-bottom: 8px;
        }
        .footer { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
        button {
          border: none;
          border-radius: 14px;
          padding: 12px 16px;
          font: inherit;
          cursor: pointer;
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
        button.secondary {
          background: var(--card-bg);
          color: var(--primary-text-color);
          border: 1px solid var(--border-color);
        }
        .error {
          margin: 16px 0;
          background: rgba(244,67,54,.12);
          border: 1px solid rgba(244,67,54,.35);
          color: var(--error-color, #b00020);
          border-radius: 16px;
          padding: 12px;
        }
        .toast {
          position: sticky;
          bottom: 16px;
          margin-top: 16px;
          background: rgba(76,175,80,.18);
          border: 1px solid rgba(76,175,80,.35);
          padding: 12px 14px;
          border-radius: 14px;
          width: fit-content;
        }
      </style>
      <div class="wrap">
        <div class="hero">
          <h1>Home Sensor Notifications</h1>
          <p>Choose the monitored sensors, where notifications go, how often reminders repeat, and whether each sensor uses the same message or its own custom message.</p>
        </div>

        ${this._loading ? `<div class="card">Loading configuration...</div>` : `
        <div class="grid">
          <section class="card">
            <h2>Monitored sensors</h2>
            <div class="muted">Door, window, and opening binary sensors are listed here.</div>
            <div class="check-list">
              ${this.renderCheckboxList(this._availableSensors, cfg.monitored_sensors || [], "toggle-sensor", (item) => `${item.entity_id} • ${item.device_class || "binary_sensor"} • current: ${item.state}`)}
            </div>
          </section>

          <section class="card">
            <h2>Notification targets</h2>
            <div class="muted">These are available notify services, such as mobile app targets.</div>
            <div class="check-list">
              ${this.renderCheckboxList(this._availableNotifyTargets, cfg.notify_targets || [], "toggle-target", (item) => `notify.${item}`)}
            </div>
          </section>

          <section class="card">
            <h2>Behaviour</h2>
            <div class="field inline">
              <input id="enabled" type="checkbox" ${cfg.enabled ? "checked" : ""}>
              <label for="enabled"><strong>Notifications enabled</strong></label>
            </div>
            <div class="field">
              <label for="reminder_minutes"><strong>Reminder interval in minutes</strong></label>
              <input id="reminder_minutes" type="number" min="1" max="1440" value="${cfg.reminder_minutes || 30}">
            </div>
            <div class="field">
              <label for="notification_mode"><strong>Notification message mode</strong></label>
              <select id="notification_mode">
                <option value="global" ${cfg.notification_mode === "global" ? "selected" : ""}>Use one message for all sensors</option>
                <option value="per_sensor" ${cfg.notification_mode === "per_sensor" ? "selected" : ""}>Use custom messages per sensor</option>
              </select>
            </div>
            <div>
              <h3>Currently open sensors</h3>
              ${(this._openSensors || []).length ? this._openSensors.map((entityId) => `<span class="status-pill">${this.sensorName(entityId)}</span>`).join("") : `<div class="muted">No monitored sensor is currently open.</div>`}
            </div>
          </section>

          <section class="card">
            <h2>Shared messages</h2>
            <div class="muted">Placeholders supported: <code>{sensor}</code>, <code>{entity_id}</code>, <code>{state}</code></div>
            <div class="field">
              <label for="global_open_message"><strong>Message when a sensor opens</strong></label>
              <textarea id="global_open_message">${cfg.global_open_message || ""}</textarea>
            </div>
            <div class="field">
              <label for="global_reminder_message"><strong>Reminder message while it stays open</strong></label>
              <textarea id="global_reminder_message">${cfg.global_reminder_message || ""}</textarea>
            </div>
          </section>
        </div>

        ${cfg.notification_mode === "per_sensor" ? `
          <section class="card" style="margin-top:20px;">
            <h2>Per-sensor custom messages</h2>
            <div class="muted">Leave a field blank to fall back to the shared message above.</div>
            ${(cfg.monitored_sensors || []).map((entityId) => {
              const sensorCfg = cfg.sensor_messages?.[entityId] || { open_message: "", reminder_message: "" };
              return `
                <div style="border:1px solid var(--border-color); border-radius:20px; padding:16px; margin-top:14px;">
                  <h3>${this.sensorName(entityId)}</h3>
                  <div class="muted">${entityId}</div>
                  <div class="field">
                    <label><strong>Open message</strong></label>
                    <textarea data-sensor-open="${entityId}">${sensorCfg.open_message || ""}</textarea>
                  </div>
                  <div class="field">
                    <label><strong>Reminder message</strong></label>
                    <textarea data-sensor-reminder="${entityId}">${sensorCfg.reminder_message || ""}</textarea>
                  </div>
                </div>
              `;
            }).join("") || `<div class="muted">Select at least one monitored sensor first.</div>`}
          </section>
        ` : ""}

        <div class="footer">
          <button id="saveBtn">${this._saving ? "Saving..." : "Save configuration"}</button>
          <button id="testBtn" class="secondary">Send test notification</button>
          <button id="reloadBtn" class="secondary">Reload panel</button>
        </div>
        `}
        ${this._error ? `<div class="error">${this._error}</div>` : ""}
        ${this._toast ? `<div class="toast">${this._toast}</div>` : ""}
      </div>
    `;
    this.bindEvents();
  }
}

customElements.define("home-sensor-notifications-panel", HomeSensorNotificationsPanel);
