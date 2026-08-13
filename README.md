# Home Sensor Notifications

Home Sensor Notifications is a HACS custom integration for door, window, and opening sensors. It sends an immediate alert and repeat reminders while an enabled, selected sensor remains open.

## Requirements

- A currently supported Home Assistant installation.
- At least one `binary_sensor` and a notification destination.
- An administrator account to configure the integration, panel, and test action.

## Install and set up

### HACS

1. In HACS, add `https://github.com/Onellan/home_sensor_notifications` as an **Integration** custom repository.
2. Download **Home Sensor Notifications** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, then select **Home Sensor Notifications**.

### Manual

Copy `custom_components/home_sensor_notifications` into your Home Assistant configuration directory and restart Home Assistant. Manual installs must be updated manually.

During setup choose sensors, notification targets, a reminder interval, messages, and the enabled state. The **Home Sensor Notifications** sidebar panel provides the same configuration with search, bulk selection, advanced per-target controls, current open state, and a test action.

## Notifications

Opening a selected sensor sends its open message. If it remains open, a reminder is scheduled after the configured interval and repeats until the sensor closes or notifications are disabled.

Messages support `{sensor}`, `{entity_id}`, and `{state}`. Choose global messages or per-sensor messages.

### Delivery modes

- **Normal** sends one standard notification.
- **Critical** uses the Home Assistant Companion mobile-app service for an urgent mobile alert. On iOS it uses critical sound; on Android it uses high priority and the alarm channel.
- **Both** intentionally sends one critical notification, not two. Two mobile notifications with the same tag can replace each other, so a single high-priority visible alert is more reliable.

Critical delivery and custom sounds apply only to legacy `notify.mobile_app_*` service targets. Generic `notify.*` entities are supported through `notify.send_message` and receive a normal message; their provider controls sound/priority support.

## Enable switch and safety

The integration switch is backed by config-entry options, so its state survives reloads consistently with the panel and options flow. It is unavailable when no valid sensor or target is configured.

Configuration and test notifications are administrator-only. Do not place secrets in messages or custom sound names. Diagnostics expose only redacted counts and operational state, never messages or target IDs.

## Troubleshooting

- **No alert:** confirm the sensor is selected, the switch is on, and at least one target remains available. The panel lists unavailable selections without silently deleting them.
- **No critical sound:** verify the target is `notify.mobile_app_*`, Companion permissions are granted, and the mobile device’s notification settings allow critical/alarm alerts.
- **Panel errors:** reload the panel after resolving its shown configuration issue; unsaved changes require confirmation before reload.
- **Logs:** enable debug logging for `custom_components.home_sensor_notifications`; messages are intentionally not logged.

To remove the integration, disable it, remove the config entry, restart Home Assistant, then remove the custom-component folder if manually installed. Back up your Home Assistant configuration before upgrades or removal.

## Development and support

Run the documented checks in [CONTRIBUTING.md](CONTRIBUTING.md). Please use the issue templates for defects and feature requests; report vulnerabilities privately using [SECURITY.md](SECURITY.md). This project follows [Keep a Changelog](https://keepachangelog.com/) in [CHANGELOG.md](CHANGELOG.md).
