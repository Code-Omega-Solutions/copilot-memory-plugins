# Implementation Plan: Memory MCP Setup

## Summary

The setup operation already provisions workspace configuration, installs the memory server, and imports committed records, but its success output does not tell users when the running MCP connection must reload. Track changes to the workspace memory configuration and managed server installation, then report a restart-required next step only when those inputs change. Keep restart under the client's control and document the expected action, including the VS Code path.

## Constitution Check

The project constitution contains only unfilled template placeholders, so it defines no ratified principles to assess. No principle conflict or added complexity is identified.

## Project Structure

```text
plugins/memory-sync/src/memory_store_sync/setup.py   # detect setup changes and report restart state
plugins/memory-sync/src/memory_store_sync/init.py    # keep standalone init advice, suppress it within setup
plugins/memory-sync/tests/test_setup.py              # cover fresh setup, repeat setup, and restart output
plugins/memory-sync/README.md                        # document CLI and hook restart behavior
README.md                                             # keep workspace setup guidance consistent
specs/001-memory-mcp-setup/data-model.md              # setup outcome and restart state
specs/001-memory-mcp-setup/contracts/                 # setup command output contract
```

**Structure Decision**: Extend the existing setup path and tests. Do not add a separate restart service because the CLI does not own the MCP client process.

## Setup Flow

Both a manual invocation and the session-start hook resolve the workspace, then use the same setup routine. Setup records whether it created the workspace memory configuration or installed the managed server. If either changed, it reports provisioning success separately from the pending client restart and gives the user a restart action. An unchanged rerun does not ask for a restart. Setup does not claim that a client has reconnected because it cannot observe that state.

## Restart Outcome

| Setup result | User-visible outcome |
|---|---|
| Workspace memory configuration or managed server newly installed | Provisioning result plus a restart-required message and client action |
| No server-affecting changes | Provisioning result without a restart request |
| Blocking install or workspace error | Existing failure result; no success claim |
| Registration scan has warnings | Existing warning result remains distinct from restart state |
