"""``status``, ``export``, ``import`` and ``sync`` between host stores.

``export`` writes the durable part of the own database to
``<storeDir>/<host>/memories.json``. ``import`` adds every durable record from
any committed export whose id the own database does not have yet. It also
reports records that exist on both sides but changed elsewhere, without
applying them.

All database access goes through the upstream server's own CLI. The only
direct SQLite operation is a WAL checkpoint, so the committed ``.db`` file is
self-contained.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, TextIO

from .server import server_command
from .store import HostPaths, discover_hosts, host_paths, is_durable, prepare_export, read_export, write_export
from .workspace import StoreLocation


@dataclass(frozen=True)
class Conflict:
    memory_id: str
    title: str
    source_host: str
    own_updated_at: str
    other_updated_at: str


class MemoryCli:
    """Runs the upstream server's ``export``/``import`` subcommands on one database."""

    def __init__(self, location: StoreLocation, db_path: Path, base_env: Mapping[str, str] | None = None):
        self.location = location
        self.db_path = db_path
        self.base_env = dict(os.environ if base_env is None else base_env)

    def _env(self) -> dict[str, str]:
        env = {**self.base_env, **self.location.config.server_env()}
        env["MCP_ROOT"] = str(self.location.server_cwd)
        env["MCP_MEMORY_ENABLED"] = "true"
        env["MCP_RAG_ENABLED"] = "false"
        env["MCP_MEMORY_DB_PATH"] = str(self.db_path)
        return env

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*server_command(self.location.config, self.base_env), *args],
            cwd=self.location.server_cwd,
            env=self._env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )

    def export_all(self) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "export.json"
            self.run("export", "-o", str(out))
            return json.loads(out.read_text(encoding="utf-8"))

    def import_records(self, records: list[dict]) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "import.json"
            src.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
            completed = self.run("import", str(src))
            return (completed.stdout + completed.stderr).strip()


CliFactory = Callable[[StoreLocation, Path], MemoryCli]


def select_new_records(sources: Mapping[str, list[dict]], own_ids: set[str]) -> list[dict]:
    """Durable records whose id is unknown locally, de-duplicated by id in host order."""
    selected: dict[str, dict] = {}
    for host in sorted(sources):
        for record in sources[host]:
            memory_id = record.get("id")
            if not memory_id or memory_id in own_ids or memory_id in selected or not is_durable(record):
                continue
            selected[memory_id] = record
    return [selected[key] for key in sorted(selected)]


def find_conflicts(own_records: list[dict], sources: Mapping[str, list[dict]]) -> list[Conflict]:
    """Records known on both sides whose remote copy differs and is newer."""
    own_by_id = {r["id"]: r for r in own_records if r.get("id")}
    conflicts: list[Conflict] = []
    for host in sorted(sources):
        for record in sources[host]:
            own = own_by_id.get(record.get("id"))
            if own is None:
                continue
            same_content = own.get("content") == record.get("content") and own.get("title") == record.get("title")
            if same_content or (record.get("updated_at") or "") <= (own.get("updated_at") or ""):
                continue
            conflicts.append(
                Conflict(
                    memory_id=record["id"],
                    title=record.get("title") or "(untitled)",
                    source_host=host,
                    own_updated_at=own.get("updated_at") or "",
                    other_updated_at=record.get("updated_at") or "",
                )
            )
    return conflicts


def checkpoint_wal(db_path: Path, log: TextIO | None = None) -> bool:
    """Fold pending WAL frames into the main file; safe while the server runs."""
    if not db_path.exists():
        return False
    try:
        # sqlite3's context manager only commits; closing releases the file on Windows.
        with closing(sqlite3.connect(db_path, timeout=5)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return True
    except sqlite3.Error as error:
        print(f"warning: WAL checkpoint skipped: {error}", file=log or sys.stderr)
        return False


def load_sources(location: StoreLocation, own_host: str, include_own: bool) -> dict[str, list[dict]]:
    sources: dict[str, list[dict]] = {}
    for host in discover_hosts(location.store_root):
        if host == own_host and not include_own:
            continue
        sources[host] = read_export(host_paths(host, location.store_root, location.rag_root).export_path)
    return sources


def reviewed_sources(location: StoreLocation, host: str, include_own: bool, out: TextIO) -> dict[str, list[dict]]:
    sources = load_sources(location, host, include_own)
    exclusions = location.config.excluded_memory_ids
    for source_host, records in sources.items():
        for record in records:
            memory_id = record.get("id")
            if memory_id in exclusions:
                print(f"{source_host}: excluded {memory_id}: {exclusions[memory_id]}", file=out)
        sources[source_host] = [record for record in records if record.get("id") not in exclusions]
    return sources


def _paths(location: StoreLocation, host: str) -> HostPaths:
    return host_paths(host, location.store_root, location.rag_root)


def command_status(location: StoreLocation, host: str, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    paths = _paths(location, host)
    print(f"workspace:     {location.workspace}", file=out)
    print(f"host:          {host}", file=out)
    print(f"database:      {paths.db_path}  ({'present' if paths.db_path.exists() else 'missing'})", file=out)
    own_export = read_export(paths.export_path)
    print(f"own export:    {paths.export_path}  ({len(own_export)} records)", file=out)
    own_ids = {r["id"] for r in own_export if r.get("id")}
    for other, records in reviewed_sources(location, host, include_own=False, out=out).items():
        pending = len(select_new_records({other: records}, own_ids))
        print(f"other host:    {other}  ({len(records)} records, {pending} not in own export)", file=out)
    return 0


def command_export(location: StoreLocation, host: str, cli_factory: CliFactory = MemoryCli, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    paths = _paths(location, host)
    if not paths.db_path.exists():
        print(f"error: {paths.db_path} does not exist; run `memory-store import` first", file=sys.stderr)
        return 1
    records = prepare_export(cli_factory(location, paths.db_path).export_all())
    write_export(paths.export_path, records)
    checkpoint_wal(paths.db_path)
    print(f"exported {len(records)} durable records to {paths.export_path}", file=out)
    return 0


def command_import(
    location: StoreLocation, host: str, dry_run: bool, cli_factory: CliFactory = MemoryCli, out: TextIO | None = None
) -> int:
    out = out or sys.stdout
    paths = _paths(location, host)
    paths.directory.mkdir(parents=True, exist_ok=True)
    cli = cli_factory(location, paths.db_path)
    own_records = cli.export_all() if paths.db_path.exists() else []
    own_ids = {r["id"] for r in own_records if r.get("id")}
    sources = reviewed_sources(location, host, include_own=not own_records, out=out)
    new_records = select_new_records(sources, own_ids)
    conflicts = find_conflicts(own_records, sources)

    for other, records in sorted(sources.items()):
        print(f"{other}: {len(select_new_records({other: records}, own_ids))} new durable records", file=out)
    failed = []
    if new_records and not dry_run:
        print(cli.import_records(new_records), file=out)
        persisted = {record["id"]: record for record in cli.export_all() if record.get("id")}
        for record in new_records:
            actual = persisted.get(record["id"])
            if actual is None or any(actual.get(key) != record.get(key) for key in ("title", "content", "type")):
                failed.append(record["id"])
        if failed:
            print(
                f"error: import verification failed for {len(failed)}/{len(new_records)} records: "
                f"{', '.join(failed)}; inspect upstream warnings and review unsupported or obsolete records",
                file=out,
            )
    elif new_records:
        print(f"dry run: {len(new_records)} records would be imported", file=out)
    else:
        if not dry_run and not paths.db_path.exists():
            cli.import_records([])
            if not paths.db_path.is_file():
                print("error: import did not initialize the host database", file=out)
                return 1
        print("nothing to import", file=out)

    if conflicts:
        print(f"\n{len(conflicts)} record(s) changed on another host; reconcile them with the memory update tools:", file=out)
        for conflict in conflicts:
            print(
                f"  - {conflict.memory_id}  {conflict.title!r}  from {conflict.source_host}"
                f"  (own {conflict.own_updated_at or '-'} / other {conflict.other_updated_at})",
                file=out,
            )
    return 1 if failed else 0
