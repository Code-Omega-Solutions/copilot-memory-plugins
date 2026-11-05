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
| `skills/memory-sync/SKILL.md` | Session-start, session-end and reconciliation workflow for agents. |
| `src/memory_store_sync/` | The `memory-store` CLI (Python standard library only). |
| `tests/` | Unit tests (`python -m unittest`). |

Setup, workflow and configuration are described in the
[repository README](../../README.md).

## CLI

```text
memory-store [--workspace DIR] [--host KEY] <command>

  init [--force]         opt the workspace in (.memory-store.json, host folder, .gitignore)
  setup                  install the server, init, write instructions, seed the database (run by the sessionStart hook)
  status                 own database and export, other hosts, pending records
  import [--dry-run]     add records from other hosts' exports; report conflicts
  export                 write the own durable export and checkpoint the database
  sync [--dry-run]       import, then export
  serve [-- ARGS]        run the MCP server on stdio for this host's store
```

`status`, `import`, `export` and `sync` exit with status 1 when the workspace
has not opted in. `serve` exits with status 2 when neither a server binary nor
Go is available.

### Workspace resolution

The workspace is the first of these that names a usable directory:
`MEMORY_WORKSPACE`, then `--workspace`, then the git work tree that contains the
working directory. Unexpanded placeholders such as `${workspaceFolder}` and the
plugin's own installation and data directories are skipped. Without a
workspace, or without `.memory-store.json` in it, `serve` uses a private store
under `PLUGIN_DATA` (or `~/.copilot-memory`) and never writes into the
repository.
