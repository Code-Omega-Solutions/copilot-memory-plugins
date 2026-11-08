# Tasks: Memory MCP Setup

## Phase 1: User Story 1 - Set up and connect workspace memory

**Goal**: Make setup report a required MCP restart when it changes the workspace server configuration, while keeping unchanged runs quiet.

**Independent Test**: Exercise setup in a fresh workspace and in a repeated unchanged workspace. Verify the restart message, manual action, and warning/result separation.

**Files**: `plugins/memory-sync/tests/test_setup.py`, `plugins/memory-sync/src/memory_store_sync/setup.py`, `plugins/memory-sync/src/memory_store_sync/init.py`

### Tests

**Wave 1 — independent:**

- [x] **T001** [US1] Add tests for restart-required first setup, unchanged reruns, and registration warnings coexisting with restart status. Write the tests to fail before the implementation change. · `plugins/memory-sync/tests/test_setup.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T002** [US1] Detect workspace memory configuration creation and managed server installation; report restart pending with the VS Code action and a generic client instruction, without changing successful provisioning exit behavior. · `plugins/memory-sync/src/memory_store_sync/setup.py`

**Checkpoint**: A fresh setup clearly reports the required restart, while an unchanged setup does not request another restart and existing warnings remain visible.

### Follow-up: remove unconditional restart advice

The shared initialization routine also prints a generic restart recommendation. Setup must suppress that recommendation because it already reports whether its own changes require a restart.

**Wave 3 — independent test:**

- [x] **T006** [US1] Assert that setup suppresses generic restart advice while standalone initialization retains it. · `plugins/memory-sync/tests/test_setup.py`

**⟶ Wait for Wave 3 to finish, then:**

- [x] **T007** [US1] Keep the standalone initialization recommendation while allowing setup to suppress it in favor of conditional restart status. · `plugins/memory-sync/src/memory_store_sync/init.py`, `plugins/memory-sync/src/memory_store_sync/setup.py`

**Checkpoint**: Setup emits restart guidance only when its server-affecting inputs changed, while standalone initialization retains its existing guidance.

## Phase 2: Polish

**Files**: `plugins/memory-sync/README.md`, `README.md`, `.github/workflows/ci.yml`

**Wave 1 — independent (different files):**

- [x] **T003** [P] [US1] Document the setup restart outcome and repeat-run behavior in the plugin guide. · `plugins/memory-sync/README.md`
- [x] **T004** [P] [US1] Align the repository setup instructions with the setup command's restart guidance. · `README.md`
- [x] **T005** [P] [US1] Run the existing CI validation: unit tests, CLI package startup, and manifest JSON checks. · `.github/workflows/ci.yml`

## Dependencies & Execution Order

- User Story 1: Wave 1 tests (T001) must finish before Wave 2 implementation (T002).
- Polish begins after User Story 1 is functional. T003, T004, and T005 are independent and may run in any order.
