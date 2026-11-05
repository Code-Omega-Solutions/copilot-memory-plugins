"""``init``: opt a git workspace in to the synchronized memory store."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from .config import CONFIG_FILENAME, StoreConfig, load_config
from .store import host_paths
from .workspace import find_git_root

IGNORE_HEADER = "# memory-sync: rebuildable index and SQLite side files stay local"


def ignore_rules(config: StoreConfig) -> list[str]:
    return [
        f"{config.rag_dir}/",
        f"{config.store_dir}/*/*.db-wal",
        f"{config.store_dir}/*/*.db-shm",
    ]


def _append_ignores(gitignore: Path, rules: list[str]) -> list[str]:
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []
    missing = [rule for rule in rules if rule not in existing]
    if not missing:
        return []
    prefix = "" if not existing or existing[-1] == "" else "\n"
    with gitignore.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + "\n".join([IGNORE_HEADER, *missing]) + "\n")
    return missing


def command_init(target: Path, host: str, force: bool = False, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    root = find_git_root(target)
    if root is None:
        print(f"error: {target} is not inside a git work tree; memory sync shares knowledge through git", file=sys.stderr)
        return 1
    config_path = root / CONFIG_FILENAME
    config = StoreConfig()
    if config_path.is_file() and not force:
        print(f"kept existing {config_path}", file=out)
        config = load_config(root) or config
    else:
        config_path.write_text(json.dumps(config.to_json(), indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {config_path}", file=out)

    paths = host_paths(host, root / config.store_dir, root / config.rag_dir)
    paths.directory.mkdir(parents=True, exist_ok=True)
    print(f"store for host {host}: {paths.directory}", file=out)

    added = _append_ignores(root / ".gitignore", ignore_rules(config))
    print(f"added {len(added)} ignore rule(s) to {root / '.gitignore'}" if added else "ignore rules already present", file=out)
    print(
        "next: restart the memory server, store or import knowledge, then run "
        "`memory-store export` and commit the host folder together with .memory-store.json",
        file=out,
    )
    return 0
