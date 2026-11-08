# Memory MCP Setup

## User Scenarios & Testing

### User Story 1 - Set up and connect workspace memory (Priority: P1)

As a developer opening a workspace, I want one setup operation to prepare its memory service and tell me when the running connection must restart so that project memory uses the intended workspace store without risking existing settings or records.

**Why this priority**: Provisioning and reconnecting the service are both necessary before project memory can be used reliably.

**Independent Test**: Run setup in a valid workspace with a connected memory service, follow any restart instruction, and verify the resulting connection uses the configured workspace store. Repeat setup to verify that unchanged configuration does not request another restart.

**Acceptance Scenarios**:
1. **Given** a valid workspace with no memory settings, **When** I run setup, **Then** it prepares the workspace and reports the restart action needed to apply the new configuration.
2. **Given** a workspace with existing memory settings and user-authored instructions, **When** I run setup, **Then** it preserves those settings and instructions while updating only its managed content.
3. **Given** setup has already completed, **When** I run it again without server-affecting changes, **Then** it succeeds without duplicating settings or requesting an unnecessary restart.
4. **Given** other workstations have committed memory exports, **When** setup initializes a new local store, **Then** their durable records are added without replacing local records or silently resolving conflicting versions.
5. **Given** setup changes server configuration but the client cannot be restarted by setup, **When** setup finishes, **Then** it reports that restart is pending and gives an actionable manual instruction without claiming that the active connection adopted the new settings.
6. **Given** the workspace cannot be resolved or a required server prerequisite is unavailable, **When** I run setup, **Then** it reports the specific blocker and does not report successful setup.
7. **Given** a competing or unreadable memory-service registration is found, **When** I run setup, **Then** it reports the conflict or incomplete scan instead of claiming that routing is conflict-free.

## Edge Cases

- The workspace contains no prior memory exports, so setup still leaves a usable local store.
- Existing configuration is valid but differs from the defaults; setup keeps it unless the user explicitly requests replacement.
- A host store exists but has no records; setup does not treat it as an uninitialized workspace.
- Import finds the same record on multiple workstations or finds newer conflicting content; setup reports the conflict without overwriting either version.
- The memory service is not currently running or the client does not expose a restart action; setup gives a manual restart instruction.
- The workspace path supplied by a hook is missing, a placeholder, or outside a usable repository; setup fails with an actionable diagnostic.

## Requirements

### Functional Requirements

- **FR-001**: The setup operation MUST prepare memory for the workspace from a single user-invoked operation.
- **FR-002**: Setup MUST preserve existing workspace configuration and user-authored instructions, changing only missing settings and content within its managed instruction section unless the user explicitly requests replacement.
- **FR-003**: Setup MUST verify that the memory service can be launched with the configured server version or report the prerequisite or installation failure that prevents launch.
- **FR-004**: Setup MUST initialize the workspace's host-specific store and add eligible records from other workstations without overwriting existing records.
- **FR-005**: Setup MUST report records changed on another workstation for later reconciliation and MUST NOT silently choose a conflicting version.
- **FR-006**: Setup MUST check known MCP registration locations for competing memory-service registrations and report incomplete checks when a configuration cannot be read or understood.
- **FR-007**: When setup changes settings that require reconnection, it MUST request a restart through the active client when supported; otherwise it MUST provide an actionable manual restart instruction and report that restart is pending.
- **FR-008**: Setup MUST distinguish completed provisioning from a running connection that still requires restart, and MUST NOT claim that the active service uses the workspace store before reconnection is verified.
- **FR-009**: Setup MUST be safe to repeat and MUST NOT create duplicate managed settings, host stores, or instruction content.
- **FR-010**: Setup MUST return a failure result for blocking errors and MUST surface warnings without presenting an incomplete configuration check as conflict-free.

### Key Entities

- **Workspace setup**: The selected repository, its memory configuration, the service registration, and the provisioning result.
- **Host store**: The local workstation's memory records and its shareable export, distinct from other workstations' stores.
- **MCP registration**: A client configuration that determines how the memory service starts and which workspace store it uses.
- **Restart state**: Whether the running client has adopted the setup changes, still needs a restart, or could not be checked.
- **Import conflict**: A durable record present in multiple workstation exports with differing content that requires explicit reconciliation.

## Success Criteria

### Measurable Outcomes

- **SC-001**: In a valid fresh workspace with prerequisites available, one setup invocation prepares a usable workspace store and service registration without requiring the developer to perform separate provisioning commands.
- **SC-002**: Repeating setup on an unchanged workspace produces no duplicate managed configuration or instruction content.
- **SC-003**: In every restart-required test, setup either requests a supported restart or displays a manual restart action and reports the connection as pending until it reconnects.
- **SC-004**: In all tested blocking-failure cases, setup returns a non-success result and identifies the failed prerequisite or workspace condition.
- **SC-005**: In all tested conflicting or unreadable-registration cases, setup reports the conflict or incomplete check and never reports the check as clean.

## Assumptions

- Setup continues to support both a manually invoked command and the workspace session-start hook.
- Setup may request a restart only when the active client exposes a supported mechanism. Otherwise the developer performs the restart using the client UI.
- Existing memory records remain authoritative until a person reconciles a reported conflict.
- Restarting the client is required only when setup changes settings or server state that the active connection must reload.

## Non-Goals

- Automatically reconciling conflicting memory records.
- Restarting arbitrary clients that do not expose a supported restart mechanism.
- Changing how agents create, search, or retrieve memories after setup is complete.
