---
name: memory-sync
description: "Use when starting or ending a session in a workspace that contains .memory-store.json, when a memory MCP tool is missing or reports a malformed database, or when knowledge learned on another machine must become available locally. Keeps the per-host agent-memory-mcp databases under <storeDir>/<host>/ converged through committed JSON exports."
argument-hint: "Optional: status | import | export | sync | init, or a reconciliation question about a conflicting record"
---

# Memory Store Sync

## Role and Scope

Keep this machine's own `agent-memory-mcp` database converged with the other
machines' committed exports. Every host owns exactly one database and one JSON
export under `<storeDir>/<host>/` (default `data/memory-store/<host>/`, set in
the workspace's `.memory-store.json`). The host key is the system hostname, or
`MEMORY_STORE_HOST` when set. A host only reads the exports it did not author.

This skill governs the sync workflow only. What knowledge is worth storing is
governed by the workspace's own instructions.

## Constraints

- Agents MUST run the CLI from the workspace root as `memory-store <command>`.
  When `memory-store` is not on `PATH`, agents MUST use
  `uvx --from "git+https://github.com/Code-Omega-Solutions/copilot-memory-plugins@v0.1.0#subdirectory=plugins/memory-sync" memory-store <command>`.
- Agents MUST NOT run `init` unless the user asked to enable synchronized memory
  for the workspace. The plugin's `sessionStart` hook runs `setup` automatically;
  with `MEMORY_STORE_AUTO_SETUP=0` the server uses a private per-user store and
  `status`/`export`/`import` refuse to run until the user asks for `setup`.
- Agents MUST NOT edit, copy or hand-merge `memories.db` or `memories.json`.
  The CLI is the only sanctioned writer; it uses the upstream
  `agent-memory-mcp export` / `import` commands.
- Agents MUST NOT write into another host's directory.
- Review historical records for relevance before import. Exact obsolete IDs may
  be excluded in `.memory-store.json` under `excludedMemoryIds`, mapping each ID
  to a nonempty review reason. Never infer exclusions solely from age or type,
  delete another active host's files, or silently convert legacy memory types.
- Import verifies stored IDs and content after the upstream command. A nonzero
  result means synchronization is incomplete; do not report success or run
  export as though all requested records were accepted.
- Only durable types (`semantic`, `procedural`, `documentation`, `episodic`)
  cross hosts. `working` memories stay local.
- `import` only adds records whose id is unknown locally. A record reported as
  "changed on another host" MUST be reconciled through the memory MCP update
  tools after reading both versions, or left as is with a note in the final
  response. Agents MUST NOT resolve it by editing JSON.
- Agents MUST commit the own host's `memories.json` and `memories.db` together,
  immediately after `export`, which checkpoints the SQLite WAL so the committed
  database is self-contained.
- If the memory MCP exposes only `repo_*` tools or reports
  `database disk image is malformed`, agents MUST stop using it, run `status`,
  restore the own database from git
  (`git checkout -- <storeDir>/<host>/memories.db`), then run `import`.

## Workflow

1. **Session start**: `git pull`, then `memory-store status`. If another host
   shows records "not in own export", run `memory-store import`. On a fresh
   checkout without a database, `import` seeds it from all committed exports;
   then restart the memory MCP server.
2. **During the session**: use the memory MCP tools normally.
3. **Session end**: run `memory-store export`, review
   `git diff --stat <storeDir>/<host>/`, and commit both files of the own host
   (for example `chore(memory): export <host> memory store`). Push if the user
   allows pushing.
4. **Reconciliation**: for each record listed as changed elsewhere, read the
   local version (`recall_memory`) and the remote version (the other host's
   `memories.json`), decide, apply the result with the memory MCP update or
   mark-outdated tools, then export again.
5. **Adding a machine**: clone, run `memory-store import` and
   `memory-store export`, and commit the new host directory.

## Output Specification

Report in the final response:

- The host key and the commands run, with the counts printed by the CLI.
- Records flagged as changed elsewhere and how each was handled.
- Whether the own host's files were committed, with the commit hash.
- Any limitation: memory MCP unavailable, `go` or `uv` missing, embedding
  provider unreachable during import, or a restored database.
