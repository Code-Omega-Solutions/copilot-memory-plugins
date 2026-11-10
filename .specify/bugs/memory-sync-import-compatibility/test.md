# Bug Verification: Memory import persistence and reviewed exclusions

- **Slug**: memory-sync-import-compatibility
- **Tested**: 2026-11-10
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Checks Performed

| Check | Result | Evidence |
|---|---|---|
| Unit and regression suite | pass | 89 tests with live integration enabled; 16.583 seconds, exit 0. |
| Original failure shape | pass | Pinned v0.13.3 imports one semantic fixture and rejects one legacy documentation fixture while exiting zero; wrapper returns 1 for the missing record. |
| Reviewed recovery | pass | Exact obsolete-ID exclusion leaves current record intact; subsequent import returns 0, export includes only the current ID. |
| Source preservation | pass | Source export bytes remain unchanged in both mock and pinned-server integration tests. |
| Failure handling | pass | Missing IDs and mismatched title/content/type return 1; sync does not call export after failed import. |
| Diff whitespace | pass | `git diff --check`. |
| CLI installation | pass | `uv tool install <local plugin path>`; `memory-store --version` returns 0.1.0. |

Command:

```shell
TMPDIR=/tmp MEMORY_SYNC_LIVE_TEST=1 PYTHONPATH=plugins/memory-sync/src python3 -m unittest discover -s plugins/memory-sync/tests -q
```

## Residual Boundaries

This verifies the CLI and real upstream storage behavior in isolated temporary
stores, not marketplace-host discovery or lifecycle. A relevant legacy
`documentation` record still needs an explicitly reviewed migration; silently
changing its type is deliberately not part of this fix. Consuming-workspace
reconciliation and deployment are separate from these regression results.
