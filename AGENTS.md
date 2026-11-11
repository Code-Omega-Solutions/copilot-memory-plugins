# Agent contribution guidance

## Plugin versions

When changing a plugin's shipped behavior or content, bump its version according
to Semantic Versioning before release:

- **PATCH** for backward-compatible bug fixes and shipped documentation updates.
- **MINOR** for backward-compatible features or capabilities.
- **MAJOR** for breaking behavior, configuration, or data compatibility changes.

For `memory-sync`, keep the release version identical in
`plugins/memory-sync/plugin.json`, `plugins/memory-sync/pyproject.toml`, the
`memory-sync` entry in `.github/plugin/marketplace.json`, and that catalog's
`metadata.version`. Update those fields together and run the version-alignment
test. Do not bump plugin versions for repository-only instructions, tests, or
CI changes that do not alter shipped plugin content; do not change unrelated
plugin entries.

## Verifying an installed plugin

The checkout version does not prove which plugin build a Copilot session loaded.
When reporting an installation, inspect the installed plugin's manifest and
compare its version and relevant file hashes with the intended source revision.
Treat the package version as a release label, not a source-commit identity.
Report the installed source/revision separately when the plugin manager exposes
it, and do not claim a runtime update from a successful update command alone.
For the Python CLI build, verify the reported version from a fresh environment
with `uv tool run --no-cache --isolated --from ./plugins/memory-sync memory-store
--version`; cached tool environments can report an older build.
