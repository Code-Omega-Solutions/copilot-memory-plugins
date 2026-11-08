# Research: Memory MCP Setup

## Restart ownership

**Decision**: Keep restart handling in setup's user-facing result. When setup changes the server registration inputs, it reports that the memory connection must be restarted and gives the client action. Do not have the setup process restart its own MCP host.

**Rationale**: Setup runs both as a CLI and as a session-start hook. It has no portable control over the editor or CLI process hosting the MCP connection, and restarting that host from setup could interrupt the setup process itself.

**Alternatives considered**: Restart automatically from the command, which is not supported by the current client integration and can terminate its caller; always require a restart, which would produce unnecessary interruptions on unchanged repeated setup.

## Restart-needed detection

**Decision**: Report restart pending when setup creates or changes the workspace memory configuration or installs the managed server binary. Do not request a restart for unchanged repeat runs.

**Rationale**: These changes can affect which server process or store the MCP client uses. Setup does not control the active client, so it must distinguish provisioning success from connection readiness.

**Alternatives considered**: Treat every successful setup as restart-required, which is noisy for the session-start hook; infer readiness from workspace files alone, which cannot prove that the active client reconnected.

## Provisioning result

**Decision**: Keep restart pending as a successful provisioning result with an explicit next action, not as a setup failure.

**Rationale**: Configuration and server installation can be complete even while the hosting client still has to reload its connection. A blocking exit code would incorrectly imply that provisioning failed.

**Alternatives considered**: Return an error until a client reconnects, which cannot be verified by the current setup process; report setup complete without restart state, which can leave the client on a private or stale store.
