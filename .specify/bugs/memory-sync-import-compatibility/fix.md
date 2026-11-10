# Bug Fix: Verify imports and support reviewed obsolete-record exclusions

- **Slug**: memory-sync-import-compatibility
- **Fixed**: 2026-11-10
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Imports now verify the upstream database export and fail if requested records
are missing or have different titles, content or types. Workspace configuration
can explicitly exclude reviewed obsolete IDs without modifying either source
exports or existing local memories.

## Changes

| File | Change | Notes |
|---|---|---|
| `plugins/memory-sync/src/memory_store_sync/config.py` | modified | Validate and round-trip ID-to-reason exclusions. |
| `plugins/memory-sync/src/memory_store_sync/sync.py` | modified | Print reviewed exclusions; verify post-import persistence and return nonzero on incomplete import. |
| `plugins/memory-sync/tests/test_config.py` | modified | Invalid mappings/reasons and configuration round-trip. |
| `plugins/memory-sync/tests/test_sync.py` | modified | Partial/rejected/mismatched imports, retry, exclusions and unchanged source files. |
| `plugins/memory-sync/tests/test_init_cli.py` | modified | Failed import prevents sync export. |
| `plugins/memory-sync/tests/test_import_live.py` | added | Opt-in isolated pinned-server reproduction and recovery. |
| `README.md`, plugin README and skill | modified | Document review, failure behavior and explicit legacy-type migration boundary. |

## Local Verification

`TMPDIR=/tmp MEMORY_SYNC_LIVE_TEST=1 PYTHONPATH=plugins/memory-sync/src python3 -m unittest discover -s plugins/memory-sync/tests -q`:
89 tests passed, including a real partial upstream import, correct wrapper
failure, then reviewed exclusion and a successful export of only current data.
`git diff --check` passed.

The initial test invocation inherited a temporary directory inside an unrelated
ancestor git checkout; four git-discovery tests failed. Setting `TMPDIR=/tmp`
isolates their temporary workspaces and all tests pass. No unrelated git
discovery code was changed.

## Deviations from Assessment

None. No implicit legacy-type conversion or host removal.

## Follow-ups

Apply the fixed CLI to consuming workspaces, explicitly review their exclusions,
and reconcile still-relevant changed records through a workspace-bound MCP
connection. This fix does not establish marketplace host acceptance.
