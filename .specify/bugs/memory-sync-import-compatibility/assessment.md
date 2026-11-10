# Bug Assessment: Memory synchronization reports rejected imports as successful

- **Slug**: memory-sync-import-compatibility
- **Created**: 2026-11-10
- **Source**: User report and local CLI reproduction in pgfeller/agents
- **Verdict**: valid
- **Severity**: medium

## Report

`memory-store import` reports `Imported 0/1 memories` and an invalid
`documentation` memory type warning, but exits zero. Every subsequent status
continues to show the same pending record.

The user requested that only still-relevant entries be imported and explicitly
confirmed that neither ThinkPad-T14 nor SHS1CX7N44C is retired. Keep both stores.
The user approved this bug slug. No implicit memory-type conversion is approved.

## Reproduction

1. Use the plugin CLI with agent-memory-mcp v0.13.3.
2. Select an unknown durable record with legacy type `documentation`.
3. Upstream rejects the record but exits zero; the wrapper forwards its output
   and returns zero without checking the resulting store.

## Suspected Code Paths

- `plugins/memory-sync/src/memory_store_sync/sync.py`: `command_import` trusts
  the upstream process exit status, even though upstream permits partial import.
- `plugins/memory-sync/src/memory_store_sync/store.py`: legacy `documentation`
  is considered durable, but that does not make it valid for the pinned server.
- `plugins/memory-sync/src/memory_store_sync/config.py`: no persistent reviewed
  exclusion exists for obsolete records on another still-active host.

## Root Cause

High confidence: upstream `runImport` catches individual store errors, prints
warnings, and returns success regardless of its imported count. The wrapper
must check the post-import export, not infer persistence from process success.

The only currently pending record, `doc-2026-09-22-mermaid-diagrams`, describes
changes to `docs/project-summary.md` and `agent-orchestrator/docs/project-summary.md`.
Neither path exists in the current agents checkout, and no project-summary file
was found. Current Mermaid tooling and guidance have separate maintained files.
The historical record is not a suitable current instruction to import blindly.

## Proposed Remediation

Add a workspace-owned `excludedMemoryIds` object mapping explicitly reviewed
obsolete IDs to nonempty reasons. Exclude only those IDs from status and import
selection and conflict reporting, with visible counts/reasons. Do not edit the
other host's export or remove host directories, mutate known local records,
infer relevance heuristically, or convert legacy memory types.

After import, export through the upstream CLI and verify every requested ID
exists with its intended title, content and type. Report missing/mismatched
records and return nonzero so `sync` cannot continue into a success-shaped
export. Preserve partial successes for retry; do not overwrite existing IDs.

## Files Likely to Change

- `plugins/memory-sync/src/memory_store_sync/config.py`
- `plugins/memory-sync/src/memory_store_sync/sync.py`
- `plugins/memory-sync/tests/test_config.py`
- `plugins/memory-sync/tests/test_sync.py`
- `plugins/memory-sync/README.md` and the memory-sync skill

## Tests

Cover validated exclusions, exclusion-aware status/dry-run/import/conflicts,
unchanged source exports, valid successful imports, zero-exit partial imports,
and mismatched persisted content/type. Existing regression tests must pass.

## Risks and Boundaries

An exclusion prevents future synchronization of that ID until removed, so it
must require an explicit durable reason and be printed rather than hidden.
Relevant legacy records still require an explicit migration decision; do not
silently convert them. No memory contents from the user's workspace belong in
this upstream source repository. Live conflict reconciliation must use MCP
updates on an explicitly workspace-bound server; chat tools currently expose
a different private store.
