# Data Model: Memory MCP Setup

## Setup outcome

Represents the result of provisioning one selected workspace.

| Field | Meaning | Validation |
|---|---|---|
| Workspace | The repository root setup selected | Must resolve to a usable Git work tree |
| Provisioning result | Whether setup completed or encountered a blocking error | A blocking error cannot be reported as complete |
| Registration warnings | Whether a competing registration was found or the scan was incomplete | Warnings remain visible independently of restart state |
| Restart required | Whether setup changed the workspace memory configuration or installed the managed server | True only after successful provisioning with a server-affecting change |
| Restart action | What the user should do to reload the MCP connection | Present when restart is required; must not claim reconnection |

## Restart lifecycle

`not-required` means setup made no server-affecting changes. `pending` means provisioning succeeded but the connection may still use its previous configuration or server process. Setup cannot transition the state to `reconnected`; the client owns the restart and the current operation has no reliable signal that it occurred.

## Relationships

- One setup outcome belongs to one workspace and its selected host store.
- A setup outcome can contain registration warnings and a restart state at the same time.
- Imported records and conflicts affect the store but do not determine restart state.
