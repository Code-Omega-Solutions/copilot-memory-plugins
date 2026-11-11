# copilot-memory-plugins

A [GitHub Copilot plugin](https://code.visualstudio.com/docs/copilot/customization/agent-plugins)
marketplace that gives coding agents durable project memory, shared between all
the workstations you work on.

| Plugin | What it adds |
| --- | --- |
| [`memory-sync`](plugins/memory-sync/README.md) | The [agent-memory-mcp](https://github.com/ipiton/agent-memory-mcp) server, a `memory-store` CLI and a `memory-sync` skill. Every workstation keeps its own memory database inside the repository and exchanges knowledge with the others through ordinary git commits. |

## How it works

Agents store decisions, verified fixes, incidents and runbooks in a memory MCP
server. A single SQLite database shared between machines would cause merge
conflicts, so every machine owns one store:

```text
<workspace>/
├── .memory-store.json            # opt-in and configuration (committed)
└── data/memory-store/
    ├── laptop/
    │   ├── memories.db           # laptop's database (committed, only laptop writes it)
    │   └── memories.json         # laptop's durable export (committed, reviewable)
    └── workstation/
        ├── memories.db
        └── memories.json
```

- At **session start**, `memory-store import` adds every record from the other
  machines' committed `memories.json` files that the own database does not have
  yet. Nothing is overwritten. When a record changed on both sides, the command
  lists it so an agent or a person can reconcile it with the memory tools.
- At **session end**, `memory-store export` writes the durable records of the
  own database (`semantic`, `procedural`, `documentation`, `episodic`) to the
  own `memories.json`. You commit and push both files of your machine.

Each machine only ever changes its own folder, so the store never produces a
git merge conflict.

## Prerequisites

- **git**. The workspace must be a git repository.
- **[uv](https://docs.astral.sh/uv/)**. It runs the plugin's Python launcher.
  Python 3.10 or newer is fetched by uv when needed; the plugin has no Python
  dependencies.
- **[Go](https://go.dev/dl/) 1.22 or newer**, *or* a prebuilt `agent-memory-mcp`
  binary. By default the server is started with `go run` of a pinned version,
  so the first start downloads and compiles it (about a minute) and later starts
  use Go's build cache. To use a binary instead:

  ```shell
  go install github.com/ipiton/agent-memory-mcp/cmd/agent-memory-mcp@v0.13.3
  ```

  and set `AGENT_MEMORY_MCP_BIN` to the installed path (for example in your
  shell profile), or put `"binary"` in `.memory-store.json` when every machine
  installs it in the same place.

## Install the plugin

### VS Code

Use one of these:

- Open this deep link, which adds the marketplace and installs the plugin after
  you confirm:
  `vscode://chat-plugin/install?source=Code-Omega-Solutions%2Fcopilot-memory-plugins&plugin=memory-sync`
- Or add the marketplace in the **Agent Customizations** editor
  (**Chat: Open Customizations** → **Browse** → **Configure Marketplaces** →
  **Add Marketplace** → `Code-Omega-Solutions/copilot-memory-plugins`), or in
  settings with `"chat.plugins.marketplaces": ["Code-Omega-Solutions/copilot-memory-plugins"]`,
  then select `memory-sync` and **Install**.
- Or run **Chat: Install Plugin from Source** and enter
  `https://github.com/Code-Omega-Solutions/copilot-memory-plugins`.

Agent plugins require `chat.plugins.enabled`. Trust the marketplace when VS Code
asks; the plugin starts an MCP server on your machine.

The plugin registers the server `agent-memory-mcp` and the skill `memory-sync`.
A repository change does not update a plugin already installed on a machine.
After a release containing a fix is available, update or reinstall `memory-sync`
from **Agent Customizations** in VS Code, then restart its `agent-memory-mcp`
connection (**MCP: List Servers** → **Restart**). For Copilot CLI, refresh the
plugin installation and start a new `copilot` process.

### Copilot CLI

```shell
copilot plugin marketplace add Code-Omega-Solutions/copilot-memory-plugins
copilot plugin install memory-sync@copilot-memory-plugins
```

The plugin's Copilot extension binds the server to the current session's
working directory. Approve its pre-tool hook when prompted; a client that
cannot load the extension must supply a supported workspace path itself.

## Enable synchronized memory in a workspace

Nothing to do by hand: the plugin's `sessionStart` hook runs
`memory-store setup` in every git workspace you open. The command is idempotent
and:

- checks that `git` is available and installs the pinned server with
  `go install` into `~/.copilot-memory/bin` (skipped when
  `AGENT_MEMORY_MCP_BIN` or `server.binary` is set; without Go it reports what
  is missing);
- runs `init` (below);
- writes the agent instructions into a managed block of
  `.github/copilot-instructions.md` (the rest of the file is untouched);
- seeds the own database from the committed exports of other machines when it
  does not exist yet.

Commit `.memory-store.json`, `.gitignore` and `.github/copilot-instructions.md`
once. Set `MEMORY_STORE_AUTO_SETUP=0` to turn the automatic setup off; configure the
workspace with `memory-store setup` or `memory-store init` yourself before
starting its server. When setup creates the
workspace configuration or installs the managed server, it reports that the
MCP connection must restart. In VS Code, use **MCP: List Servers** →
`agent-memory-mcp` → **Restart**. Unchanged setup runs do not request another
restart.

To run it manually, or when your client does not run plugin hooks:

```shell
uvx --from "git+https://github.com/Code-Omega-Solutions/copilot-memory-plugins@main#subdirectory=plugins/memory-sync" memory-store setup
```

To get a shorter command, install the CLI once per machine:

```shell
uv tool install "git+https://github.com/Code-Omega-Solutions/copilot-memory-plugins@main#subdirectory=plugins/memory-sync"
memory-store init
```

The examples below use the short `memory-store` form.

`init`:

- writes `.memory-store.json` with the defaults (an existing file is kept;
  `--force` rewrites it);
- creates `data/memory-store/<host>/`;
- adds `.gitignore` rules for the rebuildable RAG index and SQLite `-wal`/`-shm`
  side files.

Commit `.memory-store.json` and `.gitignore`, then restart the MCP server
(VS Code: **MCP: List Servers** → `agent-memory-mcp` → **Restart**).

## Daily workflow

The `memory-sync` skill teaches agents this workflow. You can also run it
yourself.

**Session start**

```shell
git pull
memory-store status   # own database, own export, other hosts and their pending records
memory-store import   # add new records from other hosts (--dry-run to preview)
```

On a machine without a database yet, `import` seeds it from all committed
exports, including its own. Restart the MCP server afterwards.

**Session end**

```shell
memory-store export
git add data/memory-store/<host>/
git commit -m "chore(memory): export <host> memory store"
git push
```

`memory-store sync` runs `import` followed by `export`.

Import verifies that requested records were actually stored; partial upstream
success is a failure, not a completed sync. For reviewed obsolete records,
configure exact IDs and reasons in `excludedMemoryIds` rather than editing
another host's export. See [import verification and exclusions](plugins/memory-sync/README.md#reviewed-obsolete-records-and-import-verification).

`export` checkpoints the SQLite write-ahead log, so the committed
`memories.db` is self-contained. Always commit `memories.db` and
`memories.json` of your host together.

### Adding a machine

Clone the repository, then run `memory-store import` and `memory-store export`
and commit the new `data/memory-store/<host>/` folder. The host key is the
system hostname; set `MEMORY_STORE_HOST` when a machine's hostname is not
stable or not unique (containers, CI, renamed laptops).

### Conflicts

`import` never overwrites. When a record you already have changed on another
machine, it prints, for example:

```text
1 record(s) changed on another host; reconcile them with the memory update tools:
  - 3f2a…  'Release checklist'  from workstation  (own 2026-03-01 / other 2026-03-04)
```

Ask the agent to compare both versions and update or mark the record outdated
with the memory tools, then `export` again. Do not edit the JSON files.

### Recovery

If the memory tools disappear or the server reports
`database disk image is malformed`, restore your database from git and import
again:

```shell
git checkout -- data/memory-store/<host>/memories.db
memory-store import
```

## Configuration reference

`.memory-store.json` (all keys optional):

```json
{
  "storeDir": "data/memory-store",
  "ragDir": "data/rag-index",
  "server": {
    "module": "github.com/ipiton/agent-memory-mcp/cmd/agent-memory-mcp@v0.13.3",
    "binary": "tools/agent-memory-mcp",
    "env": { "MCP_ALLOW_DIRS": "docs,src" }
  }
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `storeDir` | `data/memory-store` | Workspace-relative folder that holds one subfolder per host. |
| `ragDir` | `data/rag-index` | Workspace-relative folder for the local, git-ignored RAG index. |
| `server.module` | pinned upstream version | Go module run with `go run` when no binary is configured. Must be pinned (`path@version`). |
| `server.binary` | none | Server executable to use instead of `go run`. |
| `server.env` | see below | Extra or overriding environment variables for the server. `MCP_MEMORY_DB_PATH` and `MCP_RAG_INDEX_PATH` are reserved. |

The server runs with memory enabled and RAG, auto-indexing, the file watcher
and automatic stewarding disabled (`MCP_STEWARD_MODE=manual`). Override any of
these through `server.env`; see the
[agent-memory-mcp documentation](https://github.com/ipiton/agent-memory-mcp)
for all variables.

Environment variables read by the plugin:

| Variable | Effect |
| --- | --- |
| `AGENT_MEMORY_MCP_BIN` | Server executable; wins over `server.binary` and `go run`. |
| `MEMORY_STORE_HOST` | Host key instead of the system hostname. |
| `MEMORY_STORE_RUNTIME_DIR` | Override the managed server binary directory; set consistently for setup and server processes. |
| `MEMORY_WORKSPACE` | Workspace root when `--workspace` was not supplied and the process cannot infer it. |

## Registering the server per workspace instead

Clients that do not support plugins, or a team that wants the configuration in
the repository, can register the same server in the workspace's MCP
configuration (`.vscode/mcp.json` shown; `.mcp.json` works the same way for
the Copilot CLI and SDK):

```json
{
  "servers": {
    "agent-memory-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Code-Omega-Solutions/copilot-memory-plugins@5b4a479f7484e9a924a1dea9d64caa4245cd56ab#subdirectory=plugins/memory-sync",
        "memory-store",
        "serve",
        "--workspace",
        "${workspaceFolder}"
      ]
    }
  }
}
```

Pin the commit of a release tag (shown: `v0.1.0`) rather than the tag itself.
uv caches a build by commit and starts it in about two seconds. A tag reference
makes uv contact GitHub on every server start to resolve it, which adds several
seconds and fails offline. With `uv tool install` (see above) you can use
`"command": "memory-store"` and `"args": ["serve", "--workspace", "${workspaceFolder}"]`
instead.

Clients that start the server from the workspace root, such as the Copilot CLI
and SDK with a workspace `.mcp.json`, can omit `--workspace`: the server then
uses the git work tree of its working directory.

Register the server **once** per workspace: either the plugin or a workspace
entry, not both. Two server processes on the same database work, because
SQLite serializes them, but the agent sees every memory tool twice.

## Limitations

- The plugin passes `${workspaceFolder}` for VS Code. Copilot CLI/desktop
  instead uses its session extension to rebind the server to the actual
  working directory. When the extension cannot load or has not been approved,
  an unexpanded placeholder fails closed; other clients need a
  workspace-scoped registration with a supported path. See
  [workspace resolution](plugins/memory-sync/README.md#workspace-resolution).
- Records are imported without re-embedding when the server's embedding
  provider is unreachable; semantic recall of those records improves once the
  store is re-embedded.
- The SQLite database is committed as a binary file. Each machine's folder is
  only written by that machine, so git never has to merge it, but repository
  size grows with each exported change.

## Development

```shell
uv run --no-project --python 3.11 python -m unittest discover -s plugins/memory-sync/tests -t plugins/memory-sync
```

## License

[MIT](LICENSE)
