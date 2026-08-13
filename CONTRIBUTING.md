# Contributing

Use Python 3.14. Install test dependencies with `python -m pip install -r requirements-test.txt`.

Before opening a pull request, run:

```sh
ruff format --check .
ruff check .
mypy custom_components/home_sensor_notifications
pytest -q --cov=custom_components.home_sensor_notifications --cov-fail-under=50
node --check custom_components/home_sensor_notifications/static/home-sensor-notifications-panel.js
node --test tests/panel-security.test.cjs
```

Do not commit Home Assistant configuration, runtime storage, coverage output, or compiled Python files. Preserve existing user configuration during migrations and never log notification contents or target identifiers.
