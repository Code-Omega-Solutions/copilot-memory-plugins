<!-- memory-sync:begin (managed by the memory-sync plugin; edits inside are overwritten) -->
## Project memory (memory-sync)

This workspace keeps durable project memory in the `agent-memory-mcp` MCP server,
one store per workstation, synchronized through git.

- At session start, run `memory-store status` and, when another host has pending
  records, `memory-store import`. Follow the `memory-sync` skill.
- Store decisions, verified fixes, incidents and runbooks with the memory tools;
  recall before re-deriving earlier findings.
- At session end, run `memory-store export` and commit the own host folder under
  the store directory together with `.memory-store.json`.
- Never edit `memories.db` or `memories.json` by hand and never write into another
  host's folder.
- If `memory-store` is not on `PATH`, run it with `uv run --no-project` on the
  plugin's `bin/memory-store.py`, or install it with
  `uv tool install "git+https://github.com/Code-Omega-Solutions/copilot-memory-plugins#subdirectory=plugins/memory-sync"`.
<!-- memory-sync:end -->
