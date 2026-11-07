# Bug Verification: Installed memory-sync MCP server unavailable

- **Slug**: mcp-server-unavailable
- **Tested**: 2026-11-07
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

The packaged MCP registration starts successfully in a local Unix test with resolved plugin/workspace paths and uses the opted-in workspace store. The unexpanded workspace case emits a rejection note and `synced=no`; the original VS Code marketplace startup failure was not reproduced because its sanitized host output and process environment are unavailable.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | Ran the `mcp.json` command and arguments with resolved placeholders through `uv` | pass | Started the fake server from an opted-in workspace; original VS Code-specific failure remains unverified. |
| New / updated tests | `cd plugins/memory-sync && TMPDIR=/tmp PYTHONPATH=src python3 -m unittest tests.test_packaged_mcp` | pass | 2 integration tests passed. |
| Regression suite | `cd plugins/memory-sync && TMPDIR=/tmp PYTHONPATH=src python3 -m unittest discover -s tests` | pass | 79 tests passed. |
| Lint / type-check | Not configured for this plugin | skipped | The plugin documents `python -m unittest`; no lint/type-check command is configured in `pyproject.toml`. |
| Diff whitespace | `git diff --check` | pass | No whitespace errors. |

## Output Excerpts

```text
Ran 2 tests in 0.420s
OK

Ran 79 tests in 0.537s
OK
```

## Residual Risks

- The integration test substitutes plugin/workspace placeholders; it does not exercise VS Code's marketplace installation, its process environment, or its placeholder expansion.
- If `uv` is missing or `${PLUGIN_ROOT}` is unresolved, the Python launcher cannot run to provide plugin diagnostics; the MCP host must report that launch failure.
- The initial full-suite run with the host's default temporary directory failed because temporary directories were under `/home/pgfeller`, where ancestor git-root discovery selected that directory. The isolated rerun with `TMPDIR=/tmp` passed.

## Recommendation

Hold for reporter verification. The package's command path and workspace selection pass locally, but do not close the issue until sanitized VS Code MCP output confirms the actual failure boundary or the reporter verifies the installed server works.
