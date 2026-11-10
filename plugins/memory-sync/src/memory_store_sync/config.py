"""Workspace opt-in file ``.memory-store.json`` and the server defaults."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

CONFIG_FILENAME = ".memory-store.json"
DEFAULT_MODULE = "github.com/ipiton/agent-memory-mcp/cmd/agent-memory-mcp@v0.13.3"
DEFAULT_STORE_DIR = "data/memory-store"
DEFAULT_RAG_DIR = "data/rag-index"

# Line-delimited stdio, memory only, no background indexing or stewarding.
DEFAULT_SERVER_ENV: Mapping[str, str] = {
    "MCP_ROOT": ".",
    "MCP_HTTP_MODE": "stdio",
    "MCP_STDIO_MODE": "line",
    "MCP_MEMORY_ENABLED": "true",
    "MCP_RAG_ENABLED": "false",
    "MCP_RAG_AUTO_INDEX": "false",
    "MCP_RAG_FILE_WATCHER": "false",
    "MCP_STEWARD_MODE": "manual",
}

# Always derived from the host key; a configured value would split the store.
RESERVED_ENV: frozenset[str] = frozenset({"MCP_MEMORY_DB_PATH", "MCP_RAG_INDEX_PATH"})


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class StoreConfig:
    store_dir: str = DEFAULT_STORE_DIR
    rag_dir: str = DEFAULT_RAG_DIR
    module: str = DEFAULT_MODULE
    binary: str | None = None
    extra_env: Mapping[str, str] = field(default_factory=dict)
    excluded_memory_ids: Mapping[str, str] = field(default_factory=dict)

    def server_env(self) -> dict[str, str]:
        return {**DEFAULT_SERVER_ENV, **self.extra_env}

    def to_json(self) -> dict[str, Any]:
        server: dict[str, Any] = {"module": self.module}
        if self.binary:
            server["binary"] = self.binary
        if self.extra_env:
            server["env"] = dict(self.extra_env)
        result = {"storeDir": self.store_dir, "ragDir": self.rag_dir, "server": server}
        if self.excluded_memory_ids:
            result["excludedMemoryIds"] = dict(self.excluded_memory_ids)
        return result


def _relative_dir(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ":" in value or ".." in path.parts:
        raise ConfigError(f"{name} must be a workspace-relative path without '..': {value!r}")
    return path.as_posix()


def parse_config(data: Any) -> StoreConfig:
    if not isinstance(data, dict):
        raise ConfigError("configuration must be a JSON object")
    server = data.get("server", {})
    if not isinstance(server, dict):
        raise ConfigError("server must be an object")
    env = server.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ConfigError("server.env must map strings to strings")
    reserved = RESERVED_ENV.intersection(env)
    if reserved:
        raise ConfigError(f"server.env must not set {', '.join(sorted(reserved))}; the store layout owns them")
    module = server.get("module", DEFAULT_MODULE)
    if not isinstance(module, str) or "@" not in module:
        raise ConfigError("server.module must be a pinned Go module reference (path@version)")
    binary = server.get("binary")
    if binary is not None and (not isinstance(binary, str) or not binary.strip()):
        raise ConfigError("server.binary must be a non-empty string when set")
    exclusions = data.get("excludedMemoryIds", {})
    if not isinstance(exclusions, dict) or not all(
        isinstance(key, str) and key.strip() and isinstance(reason, str) and reason.strip()
        for key, reason in exclusions.items()
    ):
        raise ConfigError("excludedMemoryIds must map non-empty memory IDs to non-empty review reasons")
    return StoreConfig(
        store_dir=_relative_dir(data.get("storeDir", DEFAULT_STORE_DIR), "storeDir"),
        rag_dir=_relative_dir(data.get("ragDir", DEFAULT_RAG_DIR), "ragDir"),
        module=module,
        binary=binary,
        extra_env=dict(env),
        excluded_memory_ids=dict(exclusions),
    )


def load_config(workspace: Path) -> StoreConfig | None:
    """The workspace's configuration, or ``None`` when it has not opted in."""
    path = workspace / CONFIG_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path}: {error}") from error
    try:
        return parse_config(data)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error}") from error
