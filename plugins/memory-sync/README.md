# memory-sync

Project memory for coding agents, using
[agent-memory-mcp](https://github.com/ipiton/agent-memory-mcp), with one store
per workstation. The stores are synchronized through the workspace's git
history.

Contents:

| Path | Purpose |
| --- | --- |
| `mcp.json` | Registers the `agent-memory-mcp` server, started through `bin/memory-store.py serve`. |
| `com.github.copilot/hooks/hooks.json` | `sessionStart` hook that runs `memory-store setup` in the workspace. |
| `com.github.copilot/extensions/memory-routing/` | Copilot CLI/desktop session workspace routing. |
| `skills/memory-sync/SKILL.md` | Session-start, session-end and reconciliation workflow for agents. |
| `src/memory_store_sync/` | The `memory-store` CLI (Python standard library only). |
| `tests/` | Unit tests (`python -m unittest`). |

Setup, workflow and configuration are described in the
[repository README](../../README.md).

## CLI

```text
memory-store [--workspace DIR] [--host KEY] <command>

  init [--force]         opt the workspace in (.memory-store.json, host folder, .gitignore)
  setup [--hook-input]   check MCP registrations, install the server, init, write instructions, seed the database (run by the sessionStart hook)
  status                 own database and export, other hosts, pending records
  import [--dry-run]     add records from other hosts' exports; report conflicts
  export                 write the own durable export and checkpoint the database
  sync [--dry-run]       import, then export
  serve [-- ARGS]        run the MCP server on stdio for this host's store
```

`status`, `import`, `export` and `sync` exit with status 1 when the workspace
has not opted in. `serve` exits with status 2 when neither a server binary nor
Go is available.

On a fresh host, `import` initializes the database even when no records are
available. `import --dry-run` does not initialize it.

### Setup restart behavior

When setup creates `.memory-store.json` or installs the managed server, it
reports that the `agent-memory-mcp` connection must restart before using the
workspace settings. In VS Code, use **MCP: List Servers** →
`agent-memory-mcp` → **Restart**. Setup cannot restart or verify the client
connection itself. An unchanged setup run does not request another restart.

### MCP registration checks at setup

The installation/session-start `setup` flow checks the plugin's own `mcp.json`,
`~/.copilot/mcp-config.json`, and the selected workspace's `.vscode/mcp.json`
and `.mcp.json`. It understands both `mcpServers` and `servers` maps. The
plugin's own `agent-memory-mcp` entry is expected, not a conflict; additional
entries with that name, or recognizable memory-server commands (including
`memory-store serve` aliases), produce warnings identifying the file and entry.
Other workspaces are not inspected or changed.

Multiple registrations may shadow one another or expose separate tools.
Consequently, memory tools may reach a different database or workspace from
`memory-store setup`, `import` and `export`. Keep one intended registration
active. For an intentional workspace override, disable the plugin registration
in the client and set an explicit `serve --workspace DIR`.
In VS Code, set `"chat.mcp.collisionBehavior": "disable"` in the affected
workspace's settings to disable lower-priority **same-name** duplicates.
`"suffix"` enables duplicates with numeric suffixes; neither setting resolves
differently named aliases. Restart affected MCP connections after manual changes.

Setup never removes or rewrites MCP configs, and never prints commands,
arguments, environment values or config contents. Missing optional configs are
normal; unreadable, malformed or unsupported server structures produce an
explicit **conflict check incomplete** warning, not a conflict-free report.
The check uses strict JSON (comments/trailing commas are reported as incomplete).
Provisioning continues with exit status 0 when successful, but its final message
states **setup complete with MCP registration warnings** when attention is
needed. Runtime installation failures retain exit status 2.
This is a static check of these four files, not proof of active MCP routing:
other clients/config locations and aliases hidden behind opaque wrappers cannot
be detected. Verify the active connection and store path in your client.

### Workspace resolution

The workspace is the first of these that names a usable directory:
`--workspace`, then `MEMORY_WORKSPACE`, then the git work tree that contains
the working directory. The explicit `--workspace` argument wins over
`MEMORY_WORKSPACE` so a per-session worktree cannot be redirected by a stale
environment value. A supplied but invalid path, including an unexpanded
`${workspaceFolder}` placeholder, is rejected rather than skipped. When
`serve` resolves a workspace that lacks `.memory-store.json`, it exits with
setup guidance instead of connecting to an unrelated fallback store. A
private fallback under `PLUGIN_DATA` (or `~/.copilot-memory`) remains available
only when no workspace context can be identified at all.

The session-start hook uses `setup --hook-input` to read the workspace `cwd`
from the JSON payload on stdin, because the hook process may start in the
plugin installation directory.

In Copilot CLI and desktop, the plugin extension reads the current session's
working directory through the Copilot SDK and restarts the plugin's own
`agent-memory-mcp` connection with that workspace explicitly. It does not use
the session artifact directory, a global workspace variable, or another
session's state. An unexpanded `${workspaceFolder}` fails closed until that
restart completes. The extension requires permission to register its pre-tool
hook; when permission is denied or extension loading is unavailable, the
server does not start with the unresolved placeholder. Resolve any reported
routing error and restart the session. SDK hosts must support loading plugin
extensions and the session MCP restart API.

The extension checks the effective server's plugin provenance and enabled
state before replacing it and refuses additional same-prefix memory-server
registrations. If the expected plugin-owned registration is missing, disabled,
or owned by another source, memory calls are explicitly denied rather than
allowed to use an unverified server. Registration checks cannot detect every
differently named alias; remove those manually. VS Code uses its existing
workspace interpolation and does not require the Copilot CLI extension.
Some SDK hosts omit `source` or `sourcePlugin` from the effective MCP
registration. On those hosts the extension cannot prove ownership, so it
surfaces a routing error and denies memory calls until the host exposes both
fields; it will not infer ownership from a matching server name or readiness.
The session restart omits an environment override, preserving the host's
inherited server environment and configured runtime settings.

The Copilot app session API currently does not expose the server-level MCP
discovery or session-list methods to this extension. In the verified desktop
runtime, `mcp.list()` also omitted the registration's source, plugin owner,
version, and owned-registration receipt. The session-management list was
disabled, so the extension could not verify a coordinated child session either.
It therefore routes only from its own session working directory, denies memory
calls when plugin ownership is missing, and never selects a child by name,
recency, or an unverified path supplied by another session. A parent
conversation cannot automatically resolve or verify a child worktree with the
current API. The SDK does offer `mcp.startServer` for a caller-configured,
session-scoped server that is reaped when the session ends and does not change
persistent MCP configuration. A future explicit coordinator workflow could use
that API with a uniquely named server and a child path freshly obtained from the
host app, leaving the existing `agent-memory-mcp` registration untouched.
However, the extension cannot validate the supplied session ID/path relationship
or detect a later child path change; tool namespace and startup permission
behavior also need a controlled runtime test. This is not currently implemented
or an automatic routing guarantee. Fully validated routing requires the host to
provide a direct-child identity/current-working-directory capability and an
ownership-aware way to operate on the selected server registration.

Setup installs the pinned server binary in `~/.copilot-memory/bin`, independent
of `PLUGIN_DATA`, so both the hook and session extension resolve the same
binary. Set `MEMORY_STORE_RUNTIME_DIR` consistently in the host environment to
choose another binary directory. Setup reuses the same-version managed binary
from the previous plugin data directory when available; otherwise it installs
the pinned binary again. Existing plugin data and memory stores are not moved
or removed.

The packaged plugin registration also requires `uv` to be on the MCP host's
`PATH`. If VS Code cannot start the server, inspect **MCP: List Servers** →
`agent-memory-mcp` → **Show Output**: a missing `uv` or unresolved
`${PLUGIN_ROOT}` prevents the launcher from starting and is reported by the MCP
host before this plugin can emit diagnostics. If `${workspaceFolder}` reaches
the launcher unexpanded, its stderr reports the rejected placeholder and the
server exits without starting against a fallback store.

### Reviewed obsolete records and import verification

Review relevance before importing historical knowledge. To exclude a specific
obsolete record without modifying another active host's files, add its exact ID
and a nonempty review reason to the workspace's `.memory-store.json`:

```json
{
  "excludedMemoryIds": {
    "obsolete-documentation-id": "References removed files; current guidance is maintained elsewhere"
  }
}
```

Keep the other existing configuration keys. `status` and `import` (including
`--dry-run`) print each excluded source record and reason. Exclusions apply to
new imports and conflict reporting, including seeds from the own export, but
never delete existing local memories or edit source exports. Remove an exclusion
to reconsider the record in a future sync. Keep both stores when both hosts are
active; do not remove a host directory merely because one memory is obsolete.

After an import, the CLI re-exports the database through the upstream CLI and
verifies the requested IDs, titles, content and types. Missing or mismatched
records cause exit status 1 even if the upstream process exited zero. Partial
successes remain stored; retry selects only still-unknown IDs. `sync` does not
export after a failed import verification. A mismatched existing record requires
manual reconciliation rather than an automatic overwrite.

The pinned server does not accept the legacy `documentation` type, although old
exports may contain it. Relevant legacy records require an explicit migration
decision; the sync CLI never silently converts them. Review obsolete records
for an exclusion instead of repeatedly attempting an unsupported import.
