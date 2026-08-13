function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

const DEFAULT_CONFIG = {
  monitored_sensors: [], notify_targets: [], reminder_seconds: 1800, enabled: true,
  notification_mode: "global", global_open_message: "{sensor} opened.",
  global_reminder_message: "Reminder: {sensor} is still open.", sensor_messages: {},
  delivery_mode: "normal", sound_enabled: false, sound_name: "default", target_settings: {},
};

class PanelLocalizer {
  constructor(getHass) { this._getHass = getHass; }
  text(key, fallback) { return PanelLocalizer.catalog[this._getHass()?.language]?.[key] || PanelLocalizer.catalog.en[key] || fallback; }
}
PanelLocalizer.catalog = { en: { save: "Save changes", reload: "Reload panel", test: "Send test notification", soundTest: "Send sound test", unsaved: "Unsaved changes" } };

class PanelDataClient {
  constructor(getHass) { this._getHass = getHass; }
  async load() { return this._getHass().callWS({ type: "home_sensor_notifications/get_config" }); }
  async save(config) { return this._getHass().callWS({ type: "home_sensor_notifications/save_config", config }); }
  async test(data) { return this._getHass().callService("home_sensor_notifications", "send_test_notification", data); }
}

class PanelFormState {
  constructor() { this.dirty = false; this.validation = {}; }
  normalise(config) {
    return { ...DEFAULT_CONFIG, ...(config || {}), monitored_sensors: [...(config?.monitored_sensors || [])], notify_targets: [...(config?.notify_targets || [])], sensor_messages: { ...(config?.sensor_messages || {}) }, target_settings: { ...(config?.target_settings || {}) } };
  }
  validate(config) {
    const errors = {};
    if (!config.monitored_sensors?.length) errors.sensors = "Choose at least one monitored sensor.";
    if (!config.notify_targets?.length) errors.targets = "Choose at least one notification target.";
    const seconds = Number(config.reminder_seconds);
    if (!Number.isInteger(seconds) || seconds < 1 || seconds > 86400) errors.reminder_seconds = "Use a whole number from 1 to 86,400 seconds.";
    this.validation = errors;
    return Object.keys(errors).length === 0;
  }
}

class HomeSensorNotificationsPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    this._initialise();
    if (!this._config) this.loadData();
    else this._syncLiveState();
    this._startRefreshTimer();
  }

  connectedCallback() {
    this._initialise();
    this._connected = true;
    if (this._hass && !this._config) this.loadData();
    this._startRefreshTimer();
  }

  disconnectedCallback() {
    this._connected = false;
    ++this._requestId;
    clearInterval(this._refreshTimer);
    this._refreshTimer = null;
    clearTimeout(this._toastTimer);
    globalThis.window?.removeEventListener("beforeunload", this._beforeUnload);
  }

  _initialise() {
    if (this._initialised) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._initialised = true;
    this._connected = this.isConnected;
    this._config ??= null; this._availableSensors ??= []; this._availableNotifyTargets ??= []; this._openSensors ??= [];
    this._loading ??= false; this._saving ??= false; this._testing ??= ""; this._error ??= ""; this._toast ??= "";
    this._requestId ??= 0; this._lastUpdated ??= "";
    this._form ??= new PanelFormState();
    this._data ??= new PanelDataClient(() => this._hass);
    this._localizer ??= new PanelLocalizer(() => this._hass);
    this._ui ??= { sensorQuery: "", targetQuery: "", sensorFilter: "all", targetFilter: "all" };
    this._beforeUnload = (event) => {
      if (!this._form.dirty) return;
      event.preventDefault();
      event.returnValue = "You have unsaved Home Sensor Notifications changes.";
    };
  }

  _t(key, fallback) { return this._localizer.text(key, fallback); }

  _startRefreshTimer() {
    if (this._refreshTimer || !this._hass) return;
    this._refreshTimer = setInterval(() => this.loadData({ silent: true }), 60000);
  }

  async loadData({ silent = false } = {}) {
    if (!this._hass || this._loading) return;
    const requestId = ++this._requestId;
    this._loading = true;
    if (!silent) this._error = "";
    this.render();
    try {
      const result = await this._data.load();
      if (!this._connected || requestId !== this._requestId) return;
      this._availableSensors = result.available_sensors || [];
      this._availableNotifyTargets = result.available_notify_targets || [];
      this._openSensors = result.open_sensors || [];
      if (!this._form.dirty) this._config = this._form.normalise(result.config);
      this._lastUpdated = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      this._syncLiveState(false);
    } catch (err) {
      if (requestId === this._requestId) this._error = `Could not load current configuration: ${err?.message || String(err)}`;
    } finally {
      if (this._connected && requestId === this._requestId) {
        this._loading = false;
        this.render();
      }
    }
  }

  _syncLiveState(render = true) {
    if (!this._hass?.states || !this._config) return;
    const states = this._hass.states;
    let changed = false;
    this._availableSensors = this._availableSensors.map((sensor) => {
      const live = states[sensor.entity_id];
      if (!live || live.state === sensor.state) return sensor;
      changed = true;
      return { ...sensor, state: live.state, name: live.attributes?.friendly_name || sensor.name };
    });
    const open = (this._config.monitored_sensors || []).filter((id) => states[id]?.state === "on");
    if (open.join("|") !== this._openSensors.join("|")) { this._openSensors = open; changed = true; }
    if (changed && render) this.render();
  }

  _captureViewState() {
    const root = this.shadowRoot;
    const active = root?.activeElement;
    const state = { focus: active?.dataset?.focusKey || active?.id || "", start: active?.selectionStart, end: active?.selectionEnd, scroll: {} };
    root?.querySelectorAll("[data-scroll-key]").forEach((element) => { state.scroll[element.dataset.scrollKey] = element.scrollTop; });
    return state;
  }

  _restoreViewState(state) {
    if (!state || !this.shadowRoot) return;
    Object.entries(state.scroll || {}).forEach(([key, top]) => {
      const element = this.shadowRoot.querySelector(`[data-scroll-key="${key}"]`);
      if (element) element.scrollTop = top;
    });
    if (!state.focus) return;
    const focus = this.shadowRoot.querySelector(`[data-focus-key="${state.focus}"], #${state.focus}`);
    if (!focus) return;
    focus.focus({ preventScroll: true });
    if (typeof state.start === "number" && typeof focus.setSelectionRange === "function") focus.setSelectionRange(state.start, state.end);
  }

  _markDirty() {
    this._form.dirty = true;
    globalThis.window?.addEventListener("beforeunload", this._beforeUnload);
    this._updateActionState();
  }

  _markClean() {
    this._form.dirty = false;
    globalThis.window?.removeEventListener("beforeunload", this._beforeUnload);
  }

  _updateActionState() {
    const root = this.shadowRoot;
    const indicator = root?.getElementById("dirtyIndicator");
    if (indicator) { indicator.hidden = !this._form.dirty; indicator.textContent = this._form.dirty ? this._t("unsaved", "Unsaved changes") : ""; }
    const save = root?.getElementById("saveBtn");
    if (save) save.disabled = this._saving || !this._form.dirty;
  }

  showToast(message) {
    this._toast = message;
    this.render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { this._toast = ""; this.render(); }, 3000);
  }

  sensorName(entityId) { return this._availableSensors.find((item) => item.entity_id === entityId)?.name || entityId; }
  targetInfo(target) { return this._availableNotifyTargets.find((item) => item.entity_id === target || item.name === target) || { entity_id: target, name: target, supports_mobile_app: "false", unavailable: true }; }
  brandIconUrl() { return "/api/home_sensor_notifications/static/home-sensor-notifications-mark.svg"; }
  updateSelected(list, value, checked) { const result = new Set(list || []); checked ? result.add(value) : result.delete(value); return [...result].sort(); }

  ensureSensorMessage(entityId) {
    this._config.sensor_messages ||= {};
    return (this._config.sensor_messages[entityId] ||= { open_message: "", reminder_message: "" });
  }
  ensureTargetSetting(target) {
    this._config.target_settings ||= {};
    return (this._config.target_settings[target] ||= { delivery_mode: this._config.delivery_mode || "normal", sound_enabled: !!this._config.sound_enabled, sound_name: this._config.sound_name || "default" });
  }

  _sensorItems(cfg) {
    const known = new Set(this._availableSensors.map((item) => item.entity_id));
    return [...this._availableSensors, ...(cfg.monitored_sensors || []).filter((id) => !known.has(id)).map((entity_id) => ({ entity_id, name: entity_id, state: "unavailable", unavailable: true }))];
  }
  _targetItems(cfg) {
    const known = new Set(this._availableNotifyTargets.map((item) => item.entity_id));
    return [...this._availableNotifyTargets, ...(cfg.notify_targets || []).filter((id) => !known.has(id)).map((entity_id) => ({ entity_id, name: entity_id, supports_mobile_app: "false", unavailable: true }))];
  }
  _filterItems(items, selected, query, filter, openOnly = false) {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      const id = item.entity_id || item; const chosen = selected.includes(id);
      if (filter === "selected" && !chosen) return false;
      if (filter === "open" && !this._openSensors.includes(id)) return false;
      if (openOnly && !this._openSensors.includes(id)) return false;
      return !needle || `${item.name || ""} ${id}`.toLowerCase().includes(needle);
    });
  }

  async saveConfig() {
    if (this._saving || !this._form.validate(this._config)) { this.render(); return; }
    this._saving = true; this._error = ""; this.render();
    try {
      await this._data.save(this._config);
      this._markClean(); this.showToast("Changes saved. The integration is reloading with the new configuration.");
      await this.loadData({ silent: true });
    } catch (err) { this._error = `Could not save changes: ${err?.message || String(err)}`; }
    finally { this._saving = false; this.render(); }
  }

  async _sendTest(kind) {
    if (this._testing) return;
    this._testing = kind; this._error = ""; this.render();
    try {
      const sensor = this._config.monitored_sensors?.[0];
      const data = kind === "sound" ? { delivery_mode: "critical", sound_enabled: true } : {};
      if (sensor) data.sensor = sensor;
      await this._data.test(data);
      this.showToast(kind === "sound" ? "Sound test notification sent." : "Test notification sent.");
    } catch (err) { this._error = `Could not send test notification: ${err?.message || String(err)}`; }
    finally { this._testing = ""; this.render(); }
  }

  _renderChecklist(items, selected, type) {
    return items.map((item) => {
      const id = item.entity_id || item; const isUnavailable = item.unavailable || item.state === "unavailable" || item.state === "unknown";
      const detail = type === "sensor" ? `${id} · ${item.device_class || "binary_sensor"} · ${item.state || "unknown"}` : `${id} · ${item.supports_mobile_app === "true" ? "mobile app target" : "notify target"}`;
      return `<label class="check-row ${isUnavailable ? "unavailable" : ""}">
        <input type="checkbox" data-action="toggle-${type}" data-entity-id="${escapeHtml(id)}" ${selected.includes(id) ? "checked" : ""}>
        <span><strong>${escapeHtml(item.name || id)}</strong><span class="muted entity-id">${escapeHtml(detail)}${isUnavailable ? " · unavailable" : ""}</span></span>
      </label>`;
    }).join("") || `<p class="muted">No matching ${type === "sensor" ? "sensors" : "targets"}.</p>`;
  }

  _renderTargetSettings(cfg) {
    if (!cfg.notify_targets.length) return `<p class="muted">Select a notification target to configure its advanced delivery settings.</p>`;
    return cfg.notify_targets.map((target) => {
      const info = this.targetInfo(target); const settings = this.ensureTargetSetting(target); const mobile = info.supports_mobile_app === "true"; const key = `target-${target}`;
      return `<details class="advanced-card" data-detail-key="${escapeHtml(key)}"><summary><span><strong>${escapeHtml(info.name)}</strong><span class="muted entity-id">${escapeHtml(info.entity_id)}</span></span><span class="muted">Advanced delivery settings</span></summary>
        <div class="advanced-content" aria-label="Settings for ${escapeHtml(info.name)}">
          ${info.unavailable ? `<p class="inline-error">This configured target is currently unavailable. Its settings are retained until you remove it.</p>` : ""}
          <div class="field"><label for="${escapeHtml(key)}-delivery">Delivery mode</label><select id="${escapeHtml(key)}-delivery" data-target-delivery="${escapeHtml(target)}">
            <option value="normal" ${settings.delivery_mode === "normal" ? "selected" : ""}>In-app notification only</option>
            <option value="critical" ${settings.delivery_mode === "critical" ? "selected" : ""} ${mobile ? "" : "disabled"}>Ring / critical alert only</option>
            <option value="both" ${settings.delivery_mode === "both" ? "selected" : ""} ${mobile ? "" : "disabled"}>Both in-app and ring / critical</option>
          </select></div>
          <label class="check-row compact"><input type="checkbox" data-target-sound-enabled="${escapeHtml(target)}" ${settings.sound_enabled ? "checked" : ""}><span><strong>Enable sound</strong><span class="muted">Use default or an imported iOS sound. Android alarm delivery uses the alarm stream.</span></span></label>
          <div class="field"><label for="${escapeHtml(key)}-sound">Sound name</label><input id="${escapeHtml(key)}-sound" data-focus-key="${escapeHtml(key)}-sound" type="text" data-target-sound-name="${escapeHtml(target)}" value="${escapeHtml(settings.sound_name || "default")}" placeholder="default or imported iOS sound"></div>
        </div></details>`;
    }).join("");
  }

  bindEvents() {
    const root = this.shadowRoot;
    const changed = (callback, redraw = false) => (event) => { callback(event); this._markDirty(); if (redraw) this.render(); };
    root.querySelectorAll('[data-action="toggle-sensor"]').forEach((element) => element.addEventListener("change", changed((event) => { this._config.monitored_sensors = this.updateSelected(this._config.monitored_sensors, event.currentTarget.dataset.entityId, event.currentTarget.checked); }, true)));
    root.querySelectorAll('[data-action="toggle-target"]').forEach((element) => element.addEventListener("change", changed((event) => { this._config.notify_targets = this.updateSelected(this._config.notify_targets, event.currentTarget.dataset.entityId, event.currentTarget.checked); }, true)));
    const fields = [
      ["enabled", "change", (e) => { this._config.enabled = e.currentTarget.checked; }], ["reminder_seconds", "input", (e) => { this._config.reminder_seconds = Number(e.currentTarget.value); }],
      ["notification_mode", "change", (e) => { this._config.notification_mode = e.currentTarget.value; }, true], ["delivery_mode", "change", (e) => { this._config.delivery_mode = e.currentTarget.value; }],
      ["sound_enabled", "change", (e) => { this._config.sound_enabled = e.currentTarget.checked; }], ["sound_name", "input", (e) => { this._config.sound_name = e.currentTarget.value; }],
      ["global_open_message", "input", (e) => { this._config.global_open_message = e.currentTarget.value; }], ["global_reminder_message", "input", (e) => { this._config.global_reminder_message = e.currentTarget.value; }],
    ];
    fields.forEach(([id, event, handler, redraw]) => root.getElementById(id)?.addEventListener(event, changed(handler, redraw)));
    root.querySelectorAll("textarea[data-sensor-open]").forEach((el) => el.addEventListener("input", changed((e) => { this.ensureSensorMessage(e.currentTarget.dataset.sensorOpen).open_message = e.currentTarget.value; })));
    root.querySelectorAll("textarea[data-sensor-reminder]").forEach((el) => el.addEventListener("input", changed((e) => { this.ensureSensorMessage(e.currentTarget.dataset.sensorReminder).reminder_message = e.currentTarget.value; })));
    root.querySelectorAll("select[data-target-delivery]").forEach((el) => el.addEventListener("change", changed((e) => { this.ensureTargetSetting(e.currentTarget.dataset.targetDelivery).delivery_mode = e.currentTarget.value; })));
    root.querySelectorAll("input[data-target-sound-enabled]").forEach((el) => el.addEventListener("change", changed((e) => { this.ensureTargetSetting(e.currentTarget.dataset.targetSoundEnabled).sound_enabled = e.currentTarget.checked; })));
    root.querySelectorAll("input[data-target-sound-name]").forEach((el) => el.addEventListener("input", changed((e) => { this.ensureTargetSetting(e.currentTarget.dataset.targetSoundName).sound_name = e.currentTarget.value; })));
    ["sensor", "target"].forEach((type) => {
      root.getElementById(`${type}Search`)?.addEventListener("input", (e) => { this._ui[`${type}Query`] = e.currentTarget.value; this.render(); });
      root.getElementById(`${type}Filter`)?.addEventListener("change", (e) => { this._ui[`${type}Filter`] = e.currentTarget.value; this.render(); });
      root.getElementById(`${type}SelectVisible`)?.addEventListener("click", () => this._bulkSelect(type, true));
      root.getElementById(`${type}ClearVisible`)?.addEventListener("click", () => this._bulkSelect(type, false));
    });
    root.getElementById("saveBtn")?.addEventListener("click", () => this.saveConfig());
    root.getElementById("reloadBtn")?.addEventListener("click", () => { if (!this._form.dirty || globalThis.window?.confirm("Discard unsaved changes and reload current configuration?")) { this._markClean(); this.loadData(); } });
    root.getElementById("testBtn")?.addEventListener("click", () => this._sendTest("notification"));
    root.getElementById("soundTestBtn")?.addEventListener("click", () => this._sendTest("sound"));
  }

  _bulkSelect(type, selected) {
    const cfg = this._config; const items = type === "sensor" ? this._sensorItems(cfg) : this._targetItems(cfg);
    const visible = this._filterItems(items, type === "sensor" ? cfg.monitored_sensors : cfg.notify_targets, this._ui[`${type}Query`], this._ui[`${type}Filter`]);
    const key = type === "sensor" ? "monitored_sensors" : "notify_targets";
    const values = new Set(cfg[key]); visible.forEach((item) => selected ? values.add(item.entity_id) : values.delete(item.entity_id));
    cfg[key] = [...values].sort(); this._markDirty(); this.render();
  }

  render() {
    this._initialise();
    const state = this._captureViewState(); const cfg = this._config || this._form.normalise(DEFAULT_CONFIG); const sensors = this._sensorItems(cfg); const targets = this._targetItems(cfg);
    const filteredSensors = this._filterItems(sensors, cfg.monitored_sensors, this._ui.sensorQuery, this._ui.sensorFilter);
    const filteredTargets = this._filterItems(targets, cfg.notify_targets, this._ui.targetQuery, this._ui.targetFilter);
    const errorList = Object.values(this._form.validation || []);
    this.shadowRoot.innerHTML = `<style>
      :host { --brand-sky:#67d8ff; --brand-mint:#7be0b1; --brand-sun:#ffd36e; --card-bg:var(--ha-card-background,var(--card-background-color,#fff)); --border:var(--divider-color,rgba(127,127,127,.35)); display:block; box-sizing:border-box; min-width:0; padding:clamp(12px,3vw,24px); color:var(--primary-text-color); background:var(--primary-background-color); font-family:var(--paper-font-body1_-_font-family,sans-serif); }
      *,*::before,*::after { box-sizing:border-box; min-width:0; } .wrap { max-width:1320px; margin:auto; } .hero { overflow:hidden; border-radius:26px; padding:clamp(18px,4vw,28px); margin-bottom:18px; color:#fff; background:radial-gradient(circle at top right,rgba(255,211,110,.45),transparent 28%),linear-gradient(135deg,#114c66,#0b3041); } .hero-inner { display:grid; grid-template-columns:minmax(0,1fr) minmax(120px,220px); gap:20px; align-items:center; } .brand-badge,.status-pill { display:inline-flex; gap:8px; align-items:center; border:1px solid rgba(255,255,255,.22); border-radius:999px; padding:7px 11px; background:rgba(255,255,255,.13); } .brand-badge { font-size:12px; } .hero h1 { margin:12px 0 8px; color:#fff; font-size:clamp(26px,5vw,42px); overflow-wrap:anywhere; } .hero p { margin:0; line-height:1.5; color:rgba(255,255,255,.9); } .hero-stats { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; } .hero-stat { min-width:104px; padding:10px 12px; border-radius:14px; background:rgba(255,255,255,.12); } .hero-stat strong { display:block; font-size:20px; } .hero-stat span,.muted { color:var(--secondary-text-color); font-size:12px; } .hero .muted { color:rgba(255,255,255,.82); } .hero-mark { width:100%; padding:14px; border-radius:22px; background:rgba(255,255,255,.12); } .hero-mark img { display:block; width:100%; height:auto; }
      .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr)); gap:18px; } .card { min-width:0; border:1px solid var(--border); border-radius:20px; padding:18px; background:var(--card-bg); box-shadow:0 8px 24px rgba(0,0,0,.08); } .wide { grid-column:1 / -1; } h2 { margin:0 0 10px; color:var(--primary-text-color); font-size:20px; } h3 { margin:0; font-size:16px; } .toolbar { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 10px; } .toolbar input,.toolbar select { flex:1 1 10rem; } .check-list { display:flex; flex-direction:column; gap:8px; max-height:320px; overflow-y:auto; overflow-x:hidden; padding-right:2px; } .check-row { display:flex; gap:10px; align-items:flex-start; padding:10px; border:1px solid var(--border); border-radius:12px; cursor:pointer; overflow-wrap:anywhere; } .check-row:hover { border-color:var(--primary-color); } .check-row.unavailable { opacity:.72; border-style:dashed; } .check-row.compact { padding:8px 0; border:0; } .check-row span { display:grid; gap:3px; } .entity-id { overflow-wrap:anywhere; word-break:break-word; } .field { display:grid; gap:7px; margin:0 0 14px; } input,select,textarea { width:100%; max-width:100%; border:1px solid var(--border); border-radius:10px; padding:10px; color:var(--primary-text-color); background:var(--card-bg); font:inherit; } input[type=checkbox] { width:20px; height:20px; flex:none; margin:1px 0 0; } textarea { min-height:96px; resize:vertical; } input:focus-visible,select:focus-visible,textarea:focus-visible,button:focus-visible,summary:focus-visible { outline:3px solid var(--primary-color); outline-offset:2px; } [aria-invalid=true] { border-color:var(--error-color,#b00020); } button { min-height:44px; border:1px solid transparent; border-radius:11px; padding:10px 14px; background:var(--primary-color,#1677a0); color:var(--text-primary-color,#fff); font:inherit; font-weight:600; cursor:pointer; } button.secondary { background:var(--card-bg); color:var(--primary-text-color); border-color:var(--border); } button:disabled { opacity:.55; cursor:not-allowed; } .advanced-card { border:1px solid var(--border); border-radius:13px; margin-top:10px; overflow:hidden; } summary { display:flex; justify-content:space-between; gap:12px; align-items:center; padding:13px; cursor:pointer; } summary span { display:grid; gap:3px; } .advanced-content { padding:0 13px 13px; } .status-pill { margin:0 8px 8px 0; color:var(--primary-text-color); border-color:var(--border); background:color-mix(in srgb,var(--primary-color) 12%,var(--card-bg)); } .notice,.error,.inline-error { border-radius:11px; padding:11px; margin:14px 0; } .notice { background:color-mix(in srgb,var(--primary-color) 12%,var(--card-bg)); border:1px solid var(--border); } .error,.inline-error { color:var(--error-color,#b00020); background:color-mix(in srgb,var(--error-color,#b00020) 10%,var(--card-bg)); border:1px solid var(--error-color,#b00020); } .inline-error { font-size:13px; } .footer { position:sticky; bottom:0; z-index:2; display:flex; flex-wrap:wrap; gap:9px; margin-top:18px; padding:12px 0; background:var(--primary-background-color); border-top:1px solid var(--border); } #dirtyIndicator { align-self:center; color:var(--warning-color,#a15c00); font-size:13px; font-weight:600; } .toast { margin-top:12px; } @media (max-width:600px) { :host { padding:12px; } .hero { padding:18px; border-radius:18px; } .hero-inner { grid-template-columns:1fr; } .hero-mark { display:none; } .hero-stats { margin-top:12px; } .hero-stat { min-width:0; flex:1 1 30%; } .card { padding:14px; } .toolbar > * { flex-basis:100%; } .footer button { flex:1 1 100%; } }
      @media (prefers-contrast:more) { .card,.check-row,.advanced-card,input,select,textarea,button.secondary { border-width:2px; } }
    </style><main class="wrap" aria-busy="${this._loading || this._saving ? "true" : "false"}">
      <header class="hero"><div class="hero-inner"><div><div class="brand-badge"><strong>Home Watch</strong><span>Door, window, and opening alerts</span></div><h1>Home Sensor Notifications</h1><p>Choose monitored sensors, recipients, repeat timing, messages, and delivery options.</p><div class="hero-stats"><div class="hero-stat"><strong>${cfg.monitored_sensors.length}</strong><span>Tracked sensors</span></div><div class="hero-stat"><strong>${cfg.notify_targets.length}</strong><span>Alert targets</span></div><div class="hero-stat"><strong>${this._openSensors.length}</strong><span>Open now</span></div></div></div><div class="hero-mark"><img src="${escapeHtml(this.brandIconUrl())}" alt=""></div></div></header>
      ${this._error ? `<div class="error" role="alert">${escapeHtml(this._error)}</div>` : ""}${errorList.length ? `<div class="error" role="alert">${escapeHtml(errorList.join(" "))}</div>` : ""}
      <div class="grid"><section class="card"><h2>Monitored sensors</h2><p class="muted">${cfg.monitored_sensors.length} selected. Unavailable selections remain visible so they can be corrected safely.</p><div class="toolbar"><input id="sensorSearch" data-focus-key="sensorSearch" type="search" value="${escapeHtml(this._ui.sensorQuery)}" placeholder="Search sensors" aria-label="Search sensors"><select id="sensorFilter" aria-label="Filter sensors"><option value="all" ${this._ui.sensorFilter === "all" ? "selected" : ""}>All sensors</option><option value="selected" ${this._ui.sensorFilter === "selected" ? "selected" : ""}>Selected only</option><option value="open" ${this._ui.sensorFilter === "open" ? "selected" : ""}>Open only</option></select><button class="secondary" id="sensorSelectVisible" type="button">Select filtered</button><button class="secondary" id="sensorClearVisible" type="button">Clear filtered</button></div><div class="check-list" data-scroll-key="sensors" aria-describedby="sensorHelp">${this._renderChecklist(filteredSensors, cfg.monitored_sensors, "sensor")}</div><p id="sensorHelp" class="muted">States update from Home Assistant while this panel is open.</p></section>
      <section class="card"><h2>Notification targets</h2><p class="muted">${cfg.notify_targets.length} selected.</p><div class="toolbar"><input id="targetSearch" data-focus-key="targetSearch" type="search" value="${escapeHtml(this._ui.targetQuery)}" placeholder="Search targets" aria-label="Search notification targets"><select id="targetFilter" aria-label="Filter notification targets"><option value="all" ${this._ui.targetFilter === "all" ? "selected" : ""}>All targets</option><option value="selected" ${this._ui.targetFilter === "selected" ? "selected" : ""}>Selected only</option></select><button class="secondary" id="targetSelectVisible" type="button">Select filtered</button><button class="secondary" id="targetClearVisible" type="button">Clear filtered</button></div><div class="check-list" data-scroll-key="targets">${this._renderChecklist(filteredTargets, cfg.notify_targets, "target")}</div></section>
      <section class="card"><h2>General behavior</h2><label class="check-row compact"><input id="enabled" type="checkbox" ${cfg.enabled ? "checked" : ""}><span><strong>Enable notifications</strong><span class="muted">Opening a selected sensor triggers alerts and reminders.</span></span></label><div class="field"><label for="reminder_seconds">Reminder interval in seconds</label><input id="reminder_seconds" data-focus-key="reminder_seconds" aria-describedby="reminderHelp" aria-invalid="${this._form.validation.reminder_seconds ? "true" : "false"}" type="number" min="1" max="86400" value="${escapeHtml(cfg.reminder_seconds)}"><span id="reminderHelp" class="muted">Whole seconds, from 1 to 86,400.</span></div><div class="field"><label for="delivery_mode">Default delivery mode</label><select id="delivery_mode"><option value="normal" ${cfg.delivery_mode === "normal" ? "selected" : ""}>In-app notification only</option><option value="critical" ${cfg.delivery_mode === "critical" ? "selected" : ""}>Ring / critical alert only</option><option value="both" ${cfg.delivery_mode === "both" ? "selected" : ""}>Both in-app and ring / critical</option></select></div><label class="check-row compact"><input id="sound_enabled" type="checkbox" ${cfg.sound_enabled ? "checked" : ""}><span><strong>Enable sound by default</strong><span class="muted">iPhone can use default or imported sounds.</span></span></label><div class="field"><label for="sound_name">Default sound name</label><input id="sound_name" data-focus-key="sound_name" type="text" value="${escapeHtml(cfg.sound_name)}" placeholder="default or imported iOS sound"></div></section>
      <section class="card"><h2>Messages</h2><div class="field"><label for="notification_mode">Message mode</label><select id="notification_mode"><option value="global" ${cfg.notification_mode === "global" ? "selected" : ""}>Use one message for all sensors</option><option value="per_sensor" ${cfg.notification_mode === "per_sensor" ? "selected" : ""}>Use custom messages per sensor</option></select></div><div class="field"><label for="global_open_message">Open notification message</label><textarea id="global_open_message" data-focus-key="global_open_message" aria-describedby="messageHelp">${escapeHtml(cfg.global_open_message)}</textarea><span id="messageHelp" class="muted">Placeholders: {sensor}, {entity_id}, {state}</span></div><div class="field"><label for="global_reminder_message">Reminder message</label><textarea id="global_reminder_message" data-focus-key="global_reminder_message">${escapeHtml(cfg.global_reminder_message)}</textarea></div></section>
      <section class="card wide"><h2>Per-target delivery and sound</h2><p class="muted">Advanced controls are collapsed to keep large target lists manageable.</p>${this._renderTargetSettings(cfg)}</section>
      ${cfg.notification_mode === "per_sensor" ? `<section class="card wide"><h2>Per-sensor messages</h2>${cfg.monitored_sensors.map((id) => { const messages = this.ensureSensorMessage(id); const key = `sensor-${id}`; return `<details class="advanced-card"><summary><span><strong>${escapeHtml(this.sensorName(id))}</strong><span class="muted entity-id">${escapeHtml(id)}</span></span><span class="muted">Custom messages</span></summary><div class="advanced-content"><div class="field"><label for="${escapeHtml(key)}-open">Open message</label><textarea id="${escapeHtml(key)}-open" data-focus-key="${escapeHtml(key)}-open" data-sensor-open="${escapeHtml(id)}">${escapeHtml(messages.open_message)}</textarea></div><div class="field"><label for="${escapeHtml(key)}-reminder">Reminder message</label><textarea id="${escapeHtml(key)}-reminder" data-focus-key="${escapeHtml(key)}-reminder" data-sensor-reminder="${escapeHtml(id)}">${escapeHtml(messages.reminder_message)}</textarea></div></div></details>`; }).join("") || `<p class="muted">Select a sensor first.</p>`}</section>` : ""}
      <section class="card wide"><h2>Currently open sensors</h2>${this._openSensors.length ? this._openSensors.map((id) => `<span class="status-pill">${escapeHtml(this.sensorName(id))}</span>`).join("") : `<p class="muted">No selected sensor is currently open.</p>`}<p class="muted">Last updated: ${escapeHtml(this._lastUpdated || "waiting for data")}${this._loading ? " · refreshing…" : ""}</p></section></div>
      <footer class="footer"><span id="dirtyIndicator" ${this._form.dirty ? "" : "hidden"}>Unsaved changes</span><button id="saveBtn" type="button" ${this._saving || !this._form.dirty ? "disabled" : ""}>${this._saving ? "Saving…" : "Save changes"}</button><button class="secondary" id="reloadBtn" type="button" ${this._loading || this._saving ? "disabled" : ""}>Reload panel</button><button class="secondary" id="testBtn" type="button" ${this._testing ? "disabled" : ""}>${this._testing === "notification" ? "Sending…" : "Send test notification"}</button><button class="secondary" id="soundTestBtn" type="button" ${this._testing ? "disabled" : ""}>${this._testing === "sound" ? "Sending…" : "Send sound test"}</button></footer>${this._toast ? `<div class="notice toast" role="status" aria-live="polite">${escapeHtml(this._toast)}</div>` : ""}</main>`;
    this.bindEvents(); this._restoreViewState(state); this._updateActionState();
  }
}

customElements.define("home-sensor-notifications-panel", HomeSensorNotificationsPanel);
