class HomeSensorNotificationsPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this._config = null;
      this._availableSensors = [];
      this._availableNotifyTargets = [];
      this._openSensors = [];
      this._loading = false;
      this._saving = false;
      this._error = "";
      this._toast = "";
      this.loadData();
    }
  }

  connectedCallback() {
    if (this._hass && !this._config) this.loadData();
  }

  async loadData() {
    if (!this._hass) return;
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

  targetInfo(target) {
    return (
      this._availableNotifyTargets.find((item) => item.entity_id === target || item.name === target) || {
        entity_id: target,
        name: target,
        supports_mobile_app: "false",
      }
    );
  }

  brandIconUrl() {
    return "/api/home_sensor_notifications/static/home-sensor-notifications-mark.svg";
  }

  ensureSensorMessage(entityId) {
    if (!this._config.sensor_messages) this._config.sensor_messages = {};
    if (!this._config.sensor_messages[entityId]) {
      this._config.sensor_messages[entityId] = { open_message: "", reminder_message: "" };
    }
    return this._config.sensor_messages[entityId];
  }

  ensureTargetSetting(target) {
    if (!this._config.target_settings) this._config.target_settings = {};
    if (!this._config.target_settings[target]) {
      this._config.target_settings[target] = {
        delivery_mode: this._config.delivery_mode || "normal",
        sound_enabled: !!this._config.sound_enabled,
        sound_name: this._config.sound_name || "default",
      };
    }
    return this._config.target_settings[target];
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

  async sendSoundTest() {
    const openSensor = this._config.monitored_sensors?.[0];
    const data = {
      delivery_mode: "critical",
      sound_enabled: true,
    };
    if (openSensor) data.sensor = openSensor;
    await this._hass.callService("home_sensor_notifications", "send_test_notification", data);
    this.showToast("Sound test notification sent");
  }

  renderCheckboxList(items, selected, onChange, subLabel) {
    return items
      .map(
        (item) => `
      <label class="check-row">
        <input type="checkbox" data-entity-id="${item.entity_id || item}" ${selected.includes(item.entity_id || item) ? "checked" : ""} data-action="${onChange}">
        <span>
          <strong>${item.name || item}</strong>
          ${subLabel ? `<div class="muted">${subLabel(item)}</div>` : ""}
        </span>
      </label>
    `
      )
      .join("");
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

    const reminder = root.getElementById("reminder_seconds");
    if (reminder)
      reminder.addEventListener("input", (ev) => {
        this._config.reminder_seconds = Number(ev.currentTarget.value || 1);
      });

    const enabled = root.getElementById("enabled");
    if (enabled)
      enabled.addEventListener("change", (ev) => {
        this._config.enabled = ev.currentTarget.checked;
      });

    const mode = root.getElementById("notification_mode");
    if (mode)
      mode.addEventListener("change", (ev) => {
        this._config.notification_mode = ev.currentTarget.value;
        this.render();
      });

    const delivery = root.getElementById("delivery_mode");
    if (delivery)
      delivery.addEventListener("change", (ev) => {
        this._config.delivery_mode = ev.currentTarget.value;
      });

    const soundEnabled = root.getElementById("sound_enabled");
    if (soundEnabled)
      soundEnabled.addEventListener("change", (ev) => {
        this._config.sound_enabled = ev.currentTarget.checked;
        this.render();
      });

    const soundName = root.getElementById("sound_name");
    if (soundName)
      soundName.addEventListener("input", (ev) => {
        this._config.sound_name = ev.currentTarget.value;
      });

    const openMsg = root.getElementById("global_open_message");
    if (openMsg)
      openMsg.addEventListener("input", (ev) => {
        this._config.global_open_message = ev.currentTarget.value;
      });

    const remMsg = root.getElementById("global_reminder_message");
    if (remMsg)
      remMsg.addEventListener("input", (ev) => {
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

    root.querySelectorAll("select[data-target-delivery]").forEach((el) => {
      el.addEventListener("change", (ev) => {
        const target = ev.currentTarget.dataset.targetDelivery;
        this.ensureTargetSetting(target).delivery_mode = ev.currentTarget.value;
      });
    });

    root.querySelectorAll("input[data-target-sound-enabled]").forEach((el) => {
      el.addEventListener("change", (ev) => {
        const target = ev.currentTarget.dataset.targetSoundEnabled;
        this.ensureTargetSetting(target).sound_enabled = ev.currentTarget.checked;
        this.render();
      });
    });

    root.querySelectorAll("input[data-target-sound-name]").forEach((el) => {
      el.addEventListener("input", (ev) => {
        const target = ev.currentTarget.dataset.targetSoundName;
        this.ensureTargetSetting(target).sound_name = ev.currentTarget.value;
      });
    });

    const save = root.getElementById("saveBtn");
    if (save) save.addEventListener("click", () => this.saveConfig());

    const reload = root.getElementById("reloadBtn");
    if (reload) reload.addEventListener("click", () => this.loadData());

    const test = root.getElementById("testBtn");
    if (test) test.addEventListener("click", () => this.sendTest());

    const soundTest = root.getElementById("soundTestBtn");
    if (soundTest) soundTest.addEventListener("click", () => this.sendSoundTest());
  }

  renderTargetSettings(cfg) {
    const selectedTargets = cfg.notify_targets || [];
    if (!selectedTargets.length) {
      return `<div class="muted">Select at least one notification target to configure delivery mode and sound.</div>`;
    }
    return selectedTargets
      .map((target) => {
        const info = this.targetInfo(target);
        const settings = this.ensureTargetSetting(target);
        const mobile = info.supports_mobile_app === "true";
        return `
        <div class="target-card">
          <div class="target-head">
            <strong>${info.name}</strong>
            <span class="muted">${mobile ? "mobile_app target" : "generic notify target"}</span>
          </div>
          <div class="field">
            <label>Delivery mode</label>
            <select data-target-delivery="${target}">
              <option value="normal" ${settings.delivery_mode === "normal" ? "selected" : ""}>In-app notification only</option>
              <option value="critical" ${settings.delivery_mode === "critical" ? "selected" : ""} ${mobile ? "" : "disabled"}>Ring / critical alert only</option>
              <option value="both" ${settings.delivery_mode === "both" ? "selected" : ""} ${mobile ? "" : "disabled"}>Both in-app and ring / critical</option>
            </select>
            <div class="muted">${mobile ? "Mobile app targets can use alarm / critical delivery." : "Generic notify targets fall back to normal notifications even if you select a richer mode."}</div>
          </div>
          <label class="check-row compact">
            <input type="checkbox" data-target-sound-enabled="${target}" ${settings.sound_enabled ? "checked" : ""}>
            <span><strong>Enable sound</strong><div class="muted">For iPhone, set a sound file name or use default. Android alarm delivery uses the alarm stream.</div></span>
          </label>
          <div class="field">
            <label>Sound name</label>
            <input type="text" data-target-sound-name="${target}" value="${settings.sound_name || "default"}" placeholder="default or your imported iOS sound file">
          </div>
        </div>
      `;
      })
      .join("");
  }

  render() {
    const cfg = this._config || {
      monitored_sensors: [],
      notify_targets: [],
      reminder_seconds: 1800,
      enabled: true,
      notification_mode: "global",
      global_open_message: "{sensor} opened.",
      global_reminder_message: "Reminder: {sensor} is still open.",
      sensor_messages: {},
      delivery_mode: "normal",
      sound_enabled: false,
      sound_name: "default",
      target_settings: {},
    };

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --brand-ink: #12384b;
          --brand-sky: #67d8ff;
          --brand-mint: #7be0b1;
          --brand-sun: #ffd36e;
          --brand-coral: #ff8b78;
          --card-bg: var(--ha-card-background, var(--card-background-color, #fff));
          --border-color: var(--divider-color, rgba(0,0,0,.12));
          display: block;
          padding: 24px;
          color: var(--primary-text-color);
          background:
            radial-gradient(circle at top left, rgba(103, 216, 255, 0.12), transparent 26%),
            radial-gradient(circle at top right, rgba(255, 139, 120, 0.12), transparent 22%),
            linear-gradient(180deg, rgba(123, 224, 177, 0.06), transparent 24%),
            var(--primary-background-color);
          box-sizing: border-box;
          font-family: var(--paper-font-body1_-_font-family);
        }
        .wrap { max-width: 1320px; margin: 0 auto; }
        .hero {
          position: relative;
          overflow: hidden;
          background:
            radial-gradient(circle at top right, rgba(255, 211, 110, 0.52), transparent 28%),
            radial-gradient(circle at bottom left, rgba(103, 216, 255, 0.38), transparent 32%),
            linear-gradient(135deg, rgba(17, 76, 102, 0.96), rgba(11, 48, 65, 0.98));
          border-radius: 32px;
          padding: 28px;
          margin-bottom: 22px;
          border: 1px solid var(--border-color);
        }
        .hero::before {
          content: "";
          position: absolute;
          inset: 0;
          background:
            linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px),
            linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px);
          background-size: 28px 28px;
          mask-image: linear-gradient(180deg, rgba(0,0,0,0.8), transparent 82%);
          pointer-events: none;
        }
        .hero-inner {
          position: relative;
          display: grid;
          grid-template-columns: minmax(0, 1.8fr) minmax(160px, 0.8fr);
          gap: 24px;
          align-items: center;
          z-index: 1;
        }
        .brand-badge {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 8px 14px;
          margin-bottom: 14px;
          border-radius: 999px;
          background: rgba(255, 249, 239, 0.16);
          color: #fff9ef;
          border: 1px solid rgba(255, 255, 255, 0.18);
          backdrop-filter: blur(8px);
        }
        .brand-badge strong { font-size: 13px; letter-spacing: .04em; text-transform: uppercase; }
        .brand-badge span { font-size: 12px; opacity: 0.9; }
        .hero h1 { margin: 0 0 10px; font-size: clamp(30px, 4vw, 42px); color: #fffdf7; }
        .hero p {
          margin: 0;
          max-width: 760px;
          color: rgba(255, 249, 239, 0.88);
          line-height: 1.55;
        }
        .hero-stats {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 20px;
        }
        .hero-stat {
          min-width: 120px;
          padding: 12px 14px;
          border-radius: 18px;
          background: rgba(255, 249, 239, 0.12);
          border: 1px solid rgba(255, 255, 255, 0.14);
          color: #fffdf7;
        }
        .hero-stat strong {
          display: block;
          font-size: 22px;
          line-height: 1.1;
          margin-bottom: 4px;
        }
        .hero-stat span {
          font-size: 12px;
          letter-spacing: .04em;
          text-transform: uppercase;
          opacity: 0.82;
        }
        .hero-mark {
          justify-self: end;
          width: min(220px, 100%);
          aspect-ratio: 1;
          padding: 16px;
          border-radius: 28px;
          background: linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0.08));
          border: 1px solid rgba(255,255,255,0.16);
          box-shadow: 0 18px 40px rgba(0, 0, 0, 0.18);
          backdrop-filter: blur(10px);
        }
        .hero-mark img {
          display: block;
          width: 100%;
          height: 100%;
          object-fit: contain;
        }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
        .card {
          position: relative;
          background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02)), var(--card-bg);
          border: 1px solid rgba(18, 56, 75, 0.08);
          border-radius: 26px;
          padding: 20px;
          box-shadow: 0 12px 30px rgba(17, 49, 65, 0.08);
        }
        .card::after {
          content: "";
          position: absolute;
          inset: 0 0 auto 0;
          height: 4px;
          border-radius: 26px 26px 0 0;
          background: linear-gradient(90deg, var(--brand-sky), var(--brand-mint), var(--brand-sun));
          opacity: 0.9;
        }
        h2 { margin: 0 0 14px; font-size: 20px; color: var(--brand-ink); }
        h3 { margin: 18px 0 10px; font-size: 16px; }
        .muted { color: var(--secondary-text-color); font-size: 12px; }
        .check-list { display: flex; flex-direction: column; gap: 10px; max-height: 320px; overflow: auto; }
        .check-row {
          display: flex; align-items: flex-start; gap: 12px; padding: 10px 12px;
          border: 1px solid rgba(18, 56, 75, 0.1); border-radius: 16px; cursor: pointer;
          background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)), var(--card-bg);
        }
        .check-row.compact { padding: 10px 0; border: none; border-radius: 0; }
        .field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
        .field input[type="number"], .field input[type="text"], .field select, textarea {
          background: var(--card-bg); color: var(--primary-text-color); border: 1px solid rgba(18, 56, 75, 0.12);
          border-radius: 14px; padding: 12px; font: inherit; box-sizing: border-box; width: 100%;
        }
        textarea { min-height: 100px; resize: vertical; }
        .inline { display: flex; gap: 12px; align-items: center; }
        .status-pill {
          display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 999px;
          background: rgba(123, 224, 177, 0.2); border: 1px solid rgba(18, 56, 75, 0.08); margin-right: 8px; margin-bottom: 8px;
        }
        .footer { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
        button {
          border: none; border-radius: 16px; padding: 12px 16px; font: inherit; font-weight: 600; cursor: pointer;
          background: linear-gradient(135deg, #0f6785, #169576); color: #fffdf7;
          box-shadow: 0 12px 24px rgba(14, 73, 97, 0.18);
        }
        button.secondary {
          background: var(--card-bg); color: var(--brand-ink); border: 1px solid rgba(18, 56, 75, 0.12);
          box-shadow: none;
        }
        .error { margin: 16px 0; background: rgba(244,67,54,.12); border: 1px solid rgba(244,67,54,.35); color: var(--error-color, #b00020); border-radius: 16px; padding: 12px; }
        .toast {
          position: sticky;
          bottom: 16px;
          margin-top: 16px;
          background: rgba(123, 224, 177, 0.22);
          border: 1px solid rgba(18, 56, 75, 0.12);
          padding: 12px 14px;
          border-radius: 14px;
          width: fit-content;
        }
        .target-card { border: 1px solid rgba(18, 56, 75, 0.08); border-radius: 20px; padding: 14px; margin-bottom: 14px; background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02)), var(--card-bg); }
        .target-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; align-items: center; flex-wrap: wrap; }
        @media (max-width: 900px) {
          .hero-inner { grid-template-columns: 1fr; }
          .hero-mark { justify-self: start; width: 160px; }
        }
      </style>
      <div class="wrap">
        <div class="hero">
          <div class="hero-inner">
            <div>
              <div class="brand-badge">
                <strong>Home Watch</strong>
                <span>Playful alerts for doors, windows, and openings</span>
              </div>
              <h1>Home Sensor Notifications</h1>
              <p>Choose monitored sensors, recipients, repeat timing, shared or per-sensor messages, and whether each phone gets a normal in-app alert, a ring / critical alert, or both.</p>
              <div class="hero-stats">
                <div class="hero-stat">
                  <strong>${(cfg.monitored_sensors || []).length}</strong>
                  <span>Tracked Sensors</span>
                </div>
                <div class="hero-stat">
                  <strong>${(cfg.notify_targets || []).length}</strong>
                  <span>Alert Targets</span>
                </div>
                <div class="hero-stat">
                  <strong>${this._openSensors.length}</strong>
                  <span>Open Right Now</span>
                </div>
              </div>
            </div>
            <div class="hero-mark">
              <img src="${this.brandIconUrl()}" alt="Home Sensor Notifications icon">
            </div>
          </div>
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
            <div class="muted">Select where alerts should be sent.</div>
            <div class="check-list">
              ${this.renderCheckboxList(this._availableNotifyTargets, cfg.notify_targets || [], "toggle-target", (item) => (item.supports_mobile_app === "true" ? `${item.entity_id} • mobile app target` : `${item.entity_id} • generic notify target`))}
            </div>
          </section>

          <section class="card">
            <h2>General behavior</h2>
            <div class="field">
              <label class="check-row compact">
                <input id="enabled" type="checkbox" ${cfg.enabled ? "checked" : ""}>
                <span><strong>Enable notifications</strong><div class="muted">When enabled, opening a selected sensor triggers notifications and reminders.</div></span>
              </label>
            </div>
            <div class="field">
              <label for="reminder_seconds">Reminder interval in seconds</label>
              <input id="reminder_seconds" type="number" min="1" max="86400" value="${cfg.reminder_seconds || 1800}">
            </div>
            <div class="field">
              <label for="delivery_mode">Default delivery mode</label>
              <select id="delivery_mode">
                <option value="normal" ${cfg.delivery_mode === "normal" ? "selected" : ""}>In-app notification only</option>
                <option value="critical" ${cfg.delivery_mode === "critical" ? "selected" : ""}>Ring / critical alert only</option>
                <option value="both" ${cfg.delivery_mode === "both" ? "selected" : ""}>Both in-app and ring / critical</option>
              </select>
              <div class="muted">This is the default for selected targets. Generic notify services still receive a single normal notification, while mobile_app targets can use critical delivery.</div>
            </div>
            <div class="field">
              <label class="check-row compact">
                <input id="sound_enabled" type="checkbox" ${cfg.sound_enabled ? "checked" : ""}>
                <span><strong>Enable sound by default</strong><div class="muted">iPhone can use default or imported custom sounds. Android alarm delivery uses the alarm stream.</div></span>
              </label>
            </div>
            <div class="field">
              <label for="sound_name">Default sound name</label>
              <input id="sound_name" type="text" value="${cfg.sound_name || "default"}" placeholder="default or custom iOS sound file name">
            </div>
          </section>

          <section class="card">
            <h2>Messages</h2>
            <div class="field">
              <label for="notification_mode">Message mode</label>
              <select id="notification_mode">
                <option value="global" ${cfg.notification_mode === "global" ? "selected" : ""}>Use one message for all sensors</option>
                <option value="per_sensor" ${cfg.notification_mode === "per_sensor" ? "selected" : ""}>Use custom messages per sensor</option>
              </select>
            </div>
            <div class="field">
              <label for="global_open_message">Open notification message</label>
              <textarea id="global_open_message">${cfg.global_open_message || ""}</textarea>
              <div class="muted">Placeholders: {sensor}, {entity_id}, {state}</div>
            </div>
            <div class="field">
              <label for="global_reminder_message">Reminder message</label>
              <textarea id="global_reminder_message">${cfg.global_reminder_message || ""}</textarea>
            </div>
          </section>

          <section class="card" style="grid-column: 1 / -1;">
            <h2>Per-target delivery and sound</h2>
            <div class="muted">Fine-tune each selected phone or notify target.</div>
            ${this.renderTargetSettings(cfg)}
          </section>

          ${cfg.notification_mode === "per_sensor" ? `
          <section class="card" style="grid-column: 1 / -1;">
            <h2>Per-sensor messages</h2>
            ${(cfg.monitored_sensors || []).map((entityId) => {
              const messages = this.ensureSensorMessage(entityId);
              return `
                <div class="target-card">
                  <h3>${this.sensorName(entityId)}</h3>
                  <div class="field">
                    <label>Open message</label>
                    <textarea data-sensor-open="${entityId}">${messages.open_message || ""}</textarea>
                  </div>
                  <div class="field">
                    <label>Reminder message</label>
                    <textarea data-sensor-reminder="${entityId}">${messages.reminder_message || ""}</textarea>
                  </div>
                </div>
              `;
            }).join("")}
          </section>
          ` : ""}

          <section class="card" style="grid-column: 1 / -1;">
            <h2>Currently open sensors</h2>
            ${this._openSensors.length ? this._openSensors.map((entityId) => `<span class="status-pill">${this.sensorName(entityId)}</span>`).join("") : `<div class="muted">No selected sensor is currently open.</div>`}
          </section>
        </div>

        <div class="footer">
          <button id="saveBtn">${this._saving ? "Saving..." : "Save changes"}</button>
          <button class="secondary" id="reloadBtn">Reload panel</button>
          <button class="secondary" id="testBtn">Send test notification</button>
          <button class="secondary" id="soundTestBtn">Send sound test</button>
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
