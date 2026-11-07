# Bug Assessment: Installed memory-sync MCP server unavailable

- **Slug**: mcp-server-unavailable
- **Created**: 2026-11-07
- **Source**: https://github.com/Code-Omega-Solutions/copilot-memory-plugins/issues/1 (host: `github.com`; URL policy: allowlisted)
- **Verdict**: likely valid, needs reproduction
- **Severity**: medium

## Report (verbatim or summarized)

Issue [#1](https://github.com/Code-Omega-Solutions/copilot-memory-plugins/issues/1), “Installed memory-sync plugin can leave its MCP server unavailable,” reports that installing the plugin in VS Code/Linux did not leave `agent-memory-mcp` usable. The issue notes that `mcp.json` launches `uv` with `${PLUGIN_ROOT}` and `${workspaceFolder}` placeholders; a direct workspace-scoped CLI registration worked, but did not prove the marketplace-installed server launches or selects the opted-in workspace. The exact startup diagnostic was not retained. A later comment confirms marketplace discovery and MCP registration through Copilot CLI, while actual VS Code startup and workspace expansion remain unverified.

## Symptom

After installing and enabling `memory-sync` in a VS Code workspace, its `agent-memory-mcp` server may be unavailable, or may start against the unsynced fallback store instead of the opted-in workspace. The expected behavior is a usable server targeting the workspace, with actionable diagnostics if its launcher or paths cannot be resolved.

## Reproduction

1. On VS Code/Linux, install and enable `memory-sync` from the marketplace in a workspace containing `.memory-store.json`.
2. Observe whether `agent-memory-mcp` starts and inspect the sanitized MCP startup output.
3. [NEEDS CLARIFICATION: Capture the installed plugin's resolved command, process environment, workspace-folder expansion, and startup diagnostic.]

## Suspected Code Paths

- `plugins/memory-sync/mcp.json:6-14` — starts the launcher via `uv` and passes `${PLUGIN_ROOT}` and `${workspaceFolder}`.
- `plugins/memory-sync/src/memory_store_sync/workspace.py:71-103` — rejects unexpanded placeholders and unusable/plugin-owned workspace candidates; an unresolved workspace can result in the private fallback store.
- `plugins/memory-sync/src/memory_store_sync/server.py:37-79` — selects the server runtime and launches the child process; missing runtime errors are reported only after the Python launcher itself starts.
- `plugins/memory-sync/tests/test_workspace.py:44-56` — covers workspace resolution for placeholders and plugin-owned directories, but does not exercise the packaged MCP launcher.
- `plugins/memory-sync/tests/test_mcp_registrations.py` — checks static registration conflicts and setup behavior, not process startup through the packaged `mcp.json`.

## Root Cause Hypothesis

The report is plausible but the exact failing boundary is unknown. The packaged registration requires `uv` to be available to the MCP host and the client to expand `${PLUGIN_ROOT}` to a valid launcher path; failures at either point occur before this project's Python diagnostics can run. If startup succeeds but `${workspaceFolder}` remains unresolved, `resolve_workspace` can reject it and fall back to the private unsynced store, while logging a note to stderr. Confidence: medium.

## Proposed Remediation

**Preferred**: Add a focused integration test that reads the packaged `plugins/memory-sync/mcp.json`, substitutes realistic plugin/workspace paths and invokes its command shape in a controlled environment. Verify startup reaches `serve`, the selected store is the opted-in workspace, and missing `uv` or unresolved launcher/workspace paths produce explicit, actionable diagnostics. Improve the launcher/preflight only where the test identifies a failure that can be handled by the plugin; do not treat a static registration check as proof of VS Code host behavior.

**Alternatives**:
- Replace the `uv` launcher with a packaged executable/runtime. This could reduce host prerequisites but changes packaging and update behavior, so prefer it only if supported VS Code environments cannot reliably provide `uv`.

**Files likely to change**:
- `plugins/memory-sync/mcp.json`
- `plugins/memory-sync/bin/memory-store.py` or startup/runtime preflight code
- `plugins/memory-sync/tests/test_mcp_registrations.py` or a targeted packaged-registration integration test
- `plugins/memory-sync/README.md`

**Tests to add or update**:
- Exercise the command and argument shape from the packaged `mcp.json` with resolved paths and assert it selects the opted-in workspace.
- Cover missing launcher runtime and unexpanded plugin/workspace placeholders, asserting explicit diagnostics and a non-success result where startup cannot proceed.

## Risks & Considerations

- The issue does not include the exact VS Code version, process environment, or startup log, so a client-specific behavior may remain outside this repository's control.
- Preserve MCP stdio protocol purity: diagnostics must remain on stderr, not stdout.
- Do not silently interpret fallback-store startup as successful workspace synchronization.

## Open Questions

- [NEEDS CLARIFICATION: Can the reporter provide sanitized VS Code MCP output and the resolved process command/environment for the failing installation?]
- [NEEDS CLARIFICATION: Does the failure occur before the Python launcher starts, during workspace resolution, or while starting `agent-memory-mcp`?]
