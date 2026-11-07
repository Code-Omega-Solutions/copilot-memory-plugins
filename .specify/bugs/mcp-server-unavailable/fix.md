# Bug Fix: Installed memory-sync MCP server unavailable

- **Slug**: mcp-server-unavailable
- **Fixed**: 2026-11-07
- **Assessment**: ./assessment.md
- **Status**: partial

## Summary

Added an integration check that launches the exact packaged `mcp.json` command and arguments with resolved plugin/workspace paths, and documented how VS Code reports a missing `uv` and how to identify an unresolved workspace fallback. The integration passes in this environment; the original VS Code failure cannot be conclusively attributed or reproduced without its sanitized startup output.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `plugins/memory-sync/tests/test_packaged_mcp.py` | added integration tests | Exercises packaged registration against an opted-in workspace and verifies diagnostics when `${workspaceFolder}` remains unexpanded. |
| `plugins/memory-sync/README.md` | modified | Documents the `uv` MCP-host prerequisite and where to inspect startup diagnostics. |

## Tests Added or Updated

- `plugins/memory-sync/tests/test_packaged_mcp.py::test_packaged_registration_starts_against_opted_in_workspace` — starts the packaged command with resolved placeholders and verifies the child process uses the opted-in workspace store.
- `plugins/memory-sync/tests/test_packaged_mcp.py::test_packaged_registration_reports_unexpanded_workspace` — verifies the rejected placeholder, fallback-store warning, and `synced=no` startup line.

## Local Verification

- Commands run: `cd plugins/memory-sync && TMPDIR=/tmp PYTHONPATH=src python3 -m unittest discover -s tests` → 79 tests passed.
- Commands run: `git diff --check` → passed.
- Manual checks: Confirmed the integration used the `uv` command and argument list loaded from the packaged `plugins/memory-sync/mcp.json`; `uv` and resolved paths are available in this environment.
- The initial full-suite run with the host's configured temporary directory failed five tests because temporary workspaces were created beneath `/home/pgfeller`, where ancestor git-root discovery selected that directory. Rerunning with isolated temporary paths (`TMPDIR=/tmp`) passed.

## Deviations from Assessment

- No runtime code change was made: the packaged launch succeeded and the unexpanded workspace case already emits a rejection note and `synced=no`. A missing `uv` or unresolved `${PLUGIN_ROOT}` fails before the Python launcher can run; those failures must be diagnosed from VS Code's MCP output. Since the exact reported host failure remains unknown, changing the runtime or weakening cross-platform launcher behavior would be speculative.
- The report status is partial because the issue's original VS Code startup failure has not been independently reproduced.

## Follow-ups

- If the server still fails in VS Code, provide sanitized **MCP: List Servers → agent-memory-mcp → Show Output** content, including the resolved command and whether the plugin/workspace placeholders expanded.
- Run `/speckit-bug-test slug=mcp-server-unavailable` to record the verification outcome.
