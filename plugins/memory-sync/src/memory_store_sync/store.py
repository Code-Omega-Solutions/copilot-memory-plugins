"""Per-host store layout and the durable export format.

Every machine owns one SQLite database and one JSON export under
``<workspace>/<storeDir>/<host>/``. Only durable memory types cross hosts, and
read telemetry is stripped so committed diffs only show knowledge changes.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

DB_FILENAME = "memories.db"
EXPORT_FILENAME = "memories.json"
HOST_OVERRIDE_ENV = "MEMORY_STORE_HOST"

# ``working`` memories are session-scoped scratch and are never exchanged.
DURABLE_TYPES: frozenset[str] = frozenset({"semantic", "procedural", "documentation", "episodic"})

VOLATILE_FIELDS: frozenset[str] = frozenset({"accessed_at", "access_count", "targeted_access_count"})


@dataclass(frozen=True)
class HostPaths:
    host: str
    directory: Path
    db_path: Path
    export_path: Path
    rag_index_dir: Path


def validate_host(host: str) -> str:
    """Reject host keys that cannot safely be used as one directory name."""
    host = host.strip()
    if not host or host in {".", ".."} or any(sep in host for sep in ("/", "\\", ":")):
        raise ValueError(f"invalid host key {host!r}; set {HOST_OVERRIDE_ENV} to a plain name")
    return host


def resolve_host(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    override = env.get(HOST_OVERRIDE_ENV, "").strip()
    return validate_host(override or socket.gethostname())


def host_paths(host: str, store_root: Path, rag_root: Path) -> HostPaths:
    directory = store_root / validate_host(host)
    return HostPaths(
        host=host,
        directory=directory,
        db_path=directory / DB_FILENAME,
        export_path=directory / EXPORT_FILENAME,
        rag_index_dir=rag_root / host,
    )


def discover_hosts(store_root: Path) -> list[str]:
    """Hosts that have a committed export under the store root, sorted."""
    if not store_root.is_dir():
        return []
    return sorted(
        entry.name for entry in store_root.iterdir() if entry.is_dir() and (entry / EXPORT_FILENAME).is_file()
    )


def is_durable(record: Mapping) -> bool:
    return record.get("type") in DURABLE_TYPES


def normalize_record(record: Mapping) -> dict:
    return {key: value for key, value in record.items() if key not in VOLATILE_FIELDS}


def prepare_export(records: Iterable[Mapping]) -> list[dict]:
    """Durable records only, volatile fields removed, stable order by id."""
    prepared = [normalize_record(r) for r in records if is_durable(r)]
    prepared.sort(key=lambda r: r.get("id", ""))
    return prepared


def render_export(records: list[dict]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_export(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_export(records), encoding="utf-8", newline="\n")


def read_export(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of memories")
    return data
