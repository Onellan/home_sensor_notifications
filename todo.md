# Home Sensor Notifications improvement plan

Reviewed 2026-08-12 against the current `main` branch (`49f88ca`). This list is ordered by user/security impact first, then distribution readiness, reliability, and maintainability.

Priority legend: **P0** = release blocker, **P1** = next release, **P2** = hardening, **P3** = optional enhancement.

## P0 — release blockers

- [x] **Restrict configuration changes to administrators and close the stored-XSS path.**
  - Add `@websocket_api.require_admin` to `home_sensor_notifications/save_config`; strongly consider making the panel and read endpoint admin-only as well (`require_admin=True`). Review whether non-admin users should be able to invoke the test-notification action.
  - Stop interpolating entity names, IDs, states, messages, targets, and sound names directly into `shadowRoot.innerHTML`. Build text with `textContent`/DOM APIs or apply context-correct escaping for both text and attribute values.
  - Add regression tests proving a value such as `<img src=x onerror=...>` is rendered as text and a non-admin WebSocket connection cannot save configuration.
  - Evidence: `__init__.py:519,563-646` permits non-admin reads/writes; panel JS lines `133-146`, `267-303`, and `322+` render Home Assistant and stored config data through `innerHTML`. Home Assistant documents `@require_admin` for privileged WebSocket endpoints, and MDN identifies `innerHTML` with untrusted strings as an XSS injection sink.

- [x] **Make config-entry upgrades and reloads safe on current Home Assistant.**
  - Implement `async_migrate_entry` for config-flow `VERSION = 3`, including migration from the old minute-based reminder setting and defaults for newer delivery/message fields. Add migration tests for every supported prior version.
  - Remove double-reload/race paths. The integration registers an update listener, but reconfigure calls `async_update_reload_and_abort`, and WebSocket save calls `async_update_entry` followed by an explicit `async_reload`. With a listener, use `async_update_and_abort` and let one owner perform each reload.
  - Register the static path once per Home Assistant lifecycle and make panel registration/unregistration idempotent; prove setup → reload → unload → setup works without duplicate-route or missing-panel errors.
  - Evidence: Home Assistant 2026.6 deprecated combining an update listener with reload helpers and plans an error in 2026.12; its config-flow documentation requires `async_migrate_entry` when using major config-entry versions.

- [x] **Get HACS validation green before publishing another build.**
  - Replace the root `hacs.json` with one canonical, supported manifest: remove the unsupported `domains` key and the inapplicable manifest-path `filename`; reconcile the minimum Home Assistant version. Remove the ignored/conflicting `custom_components/home_sensor_notifications/hacs.json`.
  - Supply the brand asset HACS actually checks (`custom_components/home_sensor_notifications/brand/icon.png`) or register the brand in `home-assistant/brands`; keep SVG assets only as supplemental panel artwork.
  - Add a concise GitHub repository description and relevant topics such as `home-assistant`, `hacs`, `custom-integration`, and `notifications`.
  - Correct `manifest.json` documentation and issue links from the nonexistent `onellan/home-sensor-notifications` repository to `Onellan/home_sensor_notifications`.
  - Replace the one-line `LICENSE` placeholder with the complete MIT license text and copyright notice.
  - Evidence: the latest remote HACS run and the nine preceding runs all failed. Run `23692232916` specifically reports `domains`, brand assets, repository description, and topics; both manifest links currently return HTTP 404.

## P1 — next release

- [ ] **Add a real automated test suite.** Use `pytest-homeassistant-custom-component` (or the current recommended Home Assistant harness) to cover config flow, migration, setup/unload/reload, switch state, open/close transitions, reminder cancellation/rescheduling, disabled mode, per-sensor messages, per-target overrides, mobile/generic payloads, service errors, WebSocket authorization/validation, and panel registration. Set a meaningful coverage threshold.

- [ ] **Make CI a complete release gate.** Add Hassfest, Python lint/format/type checks, unit tests across the supported Home Assistant/Python matrix, and a JS syntax/lint/test job. Give workflows explicit least privileges (`permissions: {}`), add `workflow_dispatch` and a scheduled validation run, use a Node 24-capable checkout action, and pin third-party actions to immutable versions or commit SHAs with Dependabot/Renovate updates.

- [ ] **Use one authoritative enabled state.** The config entry, private `Store`, manager, and `RestoreEntity` can disagree: `switch.async_added_to_hass` may restore a switch value without applying it to the manager. Define precedence, synchronize all UI/config changes through one manager method, update the entity when options change, and test restart/reload scenarios. Prefer config-entry options unless independent persistence has a demonstrated need.

- [ ] **Validate all external input without uncaught exceptions.** Replace the loose WebSocket `dict` schema with a full Voluptuous schema: valid existing binary-sensor IDs, allowed notification modes/delivery modes, reminder range `1..86400`, bounded string lengths, and typed nested maps. Catch conversion errors and use `connection.send_error`. Apply equivalent enum/target validation to `send_test_notification` instead of accepting arbitrary service names.

- [ ] **Support both modern notify entities and legacy notify services deliberately.** Discover `notify` entities and call `notify.send_message` with entity targets where supported, while retaining documented compatibility for `notify.mobile_app_*` service actions and their platform-specific payloads. Do not exclude `notify.send_message` without offering the entity-based path.

- [ ] **Correct and test notification delivery semantics.** Verify iOS critical sound and Android alarm-channel payloads against current Companion documentation; avoid presenting unsupported sound choices to generic targets. Decide whether `both` should create two visible notifications—its identical tag can cause the second delivery to replace the first—and isolate per-target failures in the test-notification action just as normal delivery does.

- [ ] **Ship complete custom-integration translations.** `translations/en.json` currently contains only the switch entity, while Home Assistant custom integrations do not build runtime translations from `strings.json`. Move/copy every config, reconfigure, options, abort, entity, and action string into the full English translation, including the missing delivery/sound/target-setting labels, then validate with Hassfest.

- [ ] **Improve the panel’s correctness and accessibility.** Catch and display test-action failures instead of always claiming success; disable controls during save/test operations; validate reminder input before submit; retain unsaved edits across incidental re-renders; subscribe to state/config changes so “open right now” is live; add explicit label associations, focus states, keyboard behavior, ARIA live status, and dark/high-contrast checks.

- [ ] **Document and automate releases.** Create tagged GitHub releases whose tag and `manifest.json` version agree, publish release notes, and add a release checklist/workflow that runs every gate before publication. HACS prefers full GitHub releases, not bare tags.

## P2 — reliability and maintainability

- [ ] **Split the 700+ line integration module by responsibility.** Move the manager, WebSocket API, panel registration, notification adapters, schemas, and service action into focused modules. Use a typed config-entry alias with `runtime_data` instead of storing managers alongside a string sentinel in `hass.data[DOMAIN]`.

- [ ] **Use Home Assistant lifecycle helpers consistently.** Register listeners/cancellations with `entry.async_on_unload`, annotate unsubscribe callbacks, clean up global services/panel state when the last entry unloads, and handle partially loaded/failed entries in WebSocket handlers without indexing `hass.data` blindly.

- [ ] **Define sensor edge-case behavior.** Decide and test what happens for `unknown`/`unavailable`, entity removal/rename, an already-open sensor at startup, re-enabling while a sensor is open, changing the reminder interval mid-cycle, and a sensor that closes while a blocking notification call is still running.

- [ ] **Prevent overlapping reminder work.** Track reminder tasks explicitly, avoid launching a new cycle until the prior send completes, and make shutdown cancellation race-safe. Consider sending targets concurrently with bounded fan-out so one slow target does not delay all others.

- [ ] **Add diagnostics without leaking message contents.** Provide debug logging for lifecycle and scheduling decisions, a redacted diagnostics payload, and user-visible repair/config issues for missing sensors or notification targets. Avoid blanket `except Exception` where a narrower Home Assistant/service exception can be handled.

- [ ] **Improve entity/device modeling.** Reassess whether a service integration needs a synthetic service device; ensure the switch’s device/entity metadata follows current conventions; expose useful availability or problem state when no valid targets/sensors remain.

- [ ] **Expand the README into user documentation.** Include HACS/manual installation, minimum versions, setup and screenshots, placeholder examples, reminder behavior, normal vs critical delivery, iOS/Android limitations, permissions/security expectations, upgrade/backup steps, troubleshooting, removal, contribution, and support instructions.

- [ ] **Add repository hygiene.** Add `.gitignore`, `pyproject.toml`, contributor/development instructions, issue templates, a security policy, changelog strategy, and pre-commit hooks. Keep generated `__pycache__`, coverage output, and local Home Assistant state out of commits.

## P3 — optional product enhancements

- [ ] Offer an optional close notification and/or clear the tagged open notification when the sensor closes.
- [ ] Add per-sensor reminder intervals, quiet hours, and escalation only after the basic scheduler is fully tested.
- [ ] Add search/filtering for large sensor and target lists, show friendly target names, and warn inline about unavailable selections.
- [ ] Consider importing existing automations or generating an equivalent automation blueprint for users who do not need a custom panel/runtime manager.

## Completion criteria for the next release

- [ ] Security regression tests pass for admin authorization and HTML injection.
- [ ] Config entries migrate and setup/reload/unload cleanly on every supported Home Assistant version.
- [ ] HACS, Hassfest, lint, tests, and JS checks are green locally and remotely.
- [ ] The README, manifest version, HACS metadata, tag, and GitHub release agree.
- [ ] A clean Home Assistant test instance completes configuration, panel save, open/reminder/close behavior, switch enable/disable, normal notification, critical notification, restart, and uninstall without log errors.

## Reference guidance

- [HACS integration requirements](https://hacs.xyz/docs/publish/integration/)
- [HACS repository and `hacs.json` requirements](https://hacs.xyz/docs/publish/start/)
- [Home Assistant WebSocket permissions](https://developers.home-assistant.io/docs/auth_permissions/)
- [Home Assistant config-flow migration](https://developers.home-assistant.io/docs/core/integration/config_flow/)
- [Home Assistant custom-integration localization](https://developers.home-assistant.io/docs/internationalization/custom_integration/)
- [Home Assistant notify entities](https://developers.home-assistant.io/docs/core/entity/notify/)
- [MDN `innerHTML` security guidance](https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML)
