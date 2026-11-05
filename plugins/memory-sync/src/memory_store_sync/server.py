"""``serve``: run agent-memory-mcp against this host's own store.

Stdio is passed straight through, so the MCP client talks to the server
directly. Diagnostics go to stderr only, because stdout carries the protocol.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from .config import StoreConfig
from .store import host_paths
from .workspace import StoreLocation

BINARY_ENV = "AGENT_MEMORY_MCP_BIN"
NO_RUNTIME_EXIT = 2


class NoServerRuntime(RuntimeError):
    pass


def server_command(config: StoreConfig, environ: Mapping[str, str], which=shutil.which) -> list[str]:
    """Explicit binary first, otherwise ``go run`` of the pinned module."""
    binary = environ.get(BINARY_ENV, "").strip() or config.binary
    if binary:
        return [binary]
    go = which("go")
    if go is None:
        raise NoServerRuntime(
            f"neither {BINARY_ENV} nor server.binary is set and `go` is not on PATH; "
            f"install Go or build the server with `go install {config.module}`"
        )
    return [go, "run", config.module]


def _path_for_env(path: Path, cwd: Path) -> str:
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return str(path)


def server_environment(location: StoreLocation, host: str, base_env: Mapping[str, str]) -> dict[str, str]:
    paths = host_paths(host, location.store_root, location.rag_root)
    env = dict(base_env)
    env.update(location.config.server_env())
    env["MCP_MEMORY_DB_PATH"] = _path_for_env(paths.db_path, location.server_cwd)
    env["MCP_RAG_INDEX_PATH"] = _path_for_env(paths.rag_index_dir, location.server_cwd)
    return env


def serve(location: StoreLocation, host: str, server_args: Sequence[str], log=None) -> int:
    log = log or sys.stderr
    paths = host_paths(host, location.store_root, location.rag_root)
    for note in location.notes:
        print(f"[memory-store] {note}", file=log)
    try:
        command = server_command(location.config, os.environ)
    except NoServerRuntime as error:
        print(f"[memory-store] error: {error}", file=log)
        return NO_RUNTIME_EXIT
    paths.directory.mkdir(parents=True, exist_ok=True)
    paths.rag_index_dir.mkdir(parents=True, exist_ok=True)
    env = server_environment(location, host, os.environ)
    print(
        f"[memory-store] host={host} workspace={location.workspace or '-'} "
        f"db={env['MCP_MEMORY_DB_PATH']} synced={'yes' if location.synced else 'no'}",
        file=log,
    )
    if location.synced and not paths.db_path.exists():
        print("[memory-store] no database yet; run `memory-store import` to seed it from committed exports", file=log)

    # The child receives Ctrl+C from the same console; let it own shutdown.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    completed = subprocess.run([*command, *server_args], cwd=location.server_cwd, env=env)
    return completed.returncode
