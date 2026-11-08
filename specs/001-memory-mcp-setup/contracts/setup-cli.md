# Setup CLI Contract

## Entry points

- Manual setup: `memory-store setup` with the common `--workspace DIR` and `--host KEY` options.
- Session-start setup: `memory-store setup --hook-input`, which reads the workspace directory from the hook payload.

Both entry points use the same provisioning behavior. Existing options and exit codes remain compatible.

## Results

| Condition | Exit status | Required output |
|---|---:|---|
| Provisioning succeeds and no server-affecting input changed | 0 | Setup result; no restart request |
| Provisioning succeeds and the workspace configuration is created or the managed server is installed | 0 | Setup result, restart-required state, and an actionable restart instruction |
| Provisioning succeeds with MCP registration warnings | 0 | Existing warning details and completion-with-warnings status; restart state is reported separately |
| A blocking workspace or server installation error occurs | Nonzero | The blocking error and incomplete setup status; no success claim |

When VS Code is the client, the manual action is **MCP: List Servers** → `agent-memory-mcp` → **Restart**. For other clients, the output directs the user to restart the `agent-memory-mcp` connection in that client. Setup does not claim the active connection has adopted the new store until a later client connection verifies it.

An unchanged repeated setup does not request another restart. Setup does not modify user MCP configuration files or attempt to terminate and relaunch the client.
