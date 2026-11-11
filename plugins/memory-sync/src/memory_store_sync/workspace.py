"""Find the workspace a memory server or sync command should operate on.

Clients start plugin servers in different working directories. VS Code, for
example, uses the plugin's install directory. The workspace is therefore
taken from the first usable candidate, in this order:

1. ``--workspace`` (the plugin passes ``${workspaceFolder}``)
2. ``MEMORY_WORKSPACE``
3. the git work tree that contains the working directory

Candidates inside the plugin's own directories, values that still contain an
unexpanded ``${...}`` placeholder, and paths that do not exist are rejected
when supplied explicitly. This prevents a broken host interpolation from
silently routing an MCP server to another workspace or fallback store. A
workspace without ``.memory-store.json`` has not opted in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .config import StoreConfig, load_config

WORKSPACE_ENV = "MEMORY_WORKSPACE"
PLUGIN_DIR_ENVS = ("PLUGIN_ROOT", "PLUGIN_DATA", "COPILOT_PLUGIN_ROOT", "COPILOT_PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA")
FALLBACK_DATA_ENVS = ("PLUGIN_DATA", "COPILOT_PLUGIN_DATA", "CLAUDE_PLUGIN_DATA")
FALLBACK_HOME_DIRNAME = ".copilot-memory"

# The plugin directory (``plugins/memory-sync``) when run from a checkout or install.
PACKAGE_PLUGIN_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StoreLocation:
    """Where the store lives and how it was chosen."""

    workspace: Path | None
    config: StoreConfig
    store_root: Path
    rag_root: Path
    server_cwd: Path
    synced: bool
    notes: tuple[str, ...] = field(default_factory=tuple)


class WorkspaceRoutingError(ValueError):
    """A supplied workspace route cannot safely identify the intended workspace."""


def find_git_root(path: Path) -> Path | None:
    """Nearest ancestor (inclusive) holding a ``.git`` directory or worktree file."""
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def excluded_roots(environ: Mapping[str, str]) -> list[Path]:
    roots = [Path(environ[name]) for name in PLUGIN_DIR_ENVS if environ.get(name, "").strip()]
    roots.append(PACKAGE_PLUGIN_ROOT)
    return roots


def resolve_workspace(
    explicit: str | None, cwd: Path, environ: Mapping[str, str]
) -> tuple[Path | None, list[str]]:
    """The workspace root and diagnostic notes about skipped candidates."""
    if explicit is not None and not explicit.strip():
        raise WorkspaceRoutingError(
            "--workspace is empty; refusing to route memory without the session workspace path."
        )
    notes: list[str] = []
    excluded = excluded_roots(environ)
    candidates = [
        ("--workspace", explicit or "", True),
        (WORKSPACE_ENV, environ.get(WORKSPACE_ENV, ""), True),
        ("working directory", str(cwd), False),
    ]
    for source, raw, explicit_choice in candidates:
        value = raw.strip()
        if not value:
            continue
        if "${" in value:
            raise WorkspaceRoutingError(
                f"{source} contains an unexpanded placeholder; the MCP host did not supply "
                "the workspace path. Configure a workspace-scoped server with an explicit "
                "`--workspace DIR` and restart the connection."
            )
        path = Path(value).expanduser()
        if not path.is_dir():
            raise WorkspaceRoutingError(
                f"{source} does not name an existing directory; refusing to route memory "
                "to a different workspace."
            )
        root = find_git_root(path)
        if root is None:
            if not explicit_choice:
                notes.append(f"ignored {source}: {path} is not inside a git work tree")
                continue
            root = path.resolve()
        if any(_is_within(root, parent) for parent in excluded):
            if explicit_choice:
                raise WorkspaceRoutingError(
                    f"{source} resolves inside the plugin's own directories; refusing to "
                    "route memory to the plugin installation."
                )
            notes.append(f"ignored {source}: {root} is inside the plugin's own directories")
            continue
        return root, notes
    return None, notes


def fallback_root(environ: Mapping[str, str]) -> Path:
    for name in FALLBACK_DATA_ENVS:
        value = environ.get(name, "").strip()
        if value and "${" not in value:
            return Path(value).expanduser()
    return Path.home() / FALLBACK_HOME_DIRNAME


def locate_store(
    explicit: str | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
    require_config: bool = False,
) -> StoreLocation:
    env = os.environ if environ is None else environ
    workspace, notes = resolve_workspace(explicit, cwd or Path.cwd(), env)
    config = load_config(workspace) if workspace else None
    if workspace is not None and config is not None:
        return StoreLocation(
            workspace=workspace,
            config=config,
            store_root=workspace / config.store_dir,
            rag_root=workspace / config.rag_dir,
            server_cwd=workspace,
            synced=True,
            notes=tuple(notes),
        )
    if require_config and workspace is not None:
        raise WorkspaceRoutingError(
            f"{workspace} has no .memory-store.json; run `memory-store setup` in that "
            "workspace before starting the memory MCP server."
        )
    root = fallback_root(env)
    reason = "no workspace found" if workspace is None else f"{workspace} has no .memory-store.json (run `memory-store init` to opt in)"
    notes.append(f"using the unsynced fallback store under {root}: {reason}")
    return StoreLocation(
        workspace=workspace,
        config=StoreConfig(),
        store_root=root / "memory-store",
        rag_root=root / "rag-index",
        server_cwd=workspace or root,
        synced=False,
        notes=tuple(notes),
    )
