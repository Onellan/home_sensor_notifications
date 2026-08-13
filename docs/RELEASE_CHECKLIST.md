# Release checklist

1. Set `manifest.json` to the intended semantic version and update `CHANGELOG.md`.
2. Run the full `Validate` workflow successfully on the release commit.
3. Run **Release** manually with a `v` tag that exactly matches the manifest version.
4. Confirm the generated GitHub release notes and HACS validation before announcing the release.
