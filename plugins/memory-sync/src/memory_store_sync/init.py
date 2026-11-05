"""``init``: opt a git workspace in to the synchronized memory store."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from .config import CONFIG_FILENAME, StoreConfig, load_config
from .store import host_paths
from .workspace import find_git_root

IGNORE_HEADER = "# memory-sync: rebuildable index and SQLite side files stay local"


UNIGNORE_HEADER = "# memory-sync: keep the committed memory store out of broader ignore rules"


def ignore_rules(config: StoreConfig) -> list[str]:
    return [
        f"{config.rag_dir}/",
        f"{config.store_dir}/*/*.db-wal",
        f"{config.store_dir}/*/*.db-shm",
    ]


def _append_ignores(gitignore: Path, rules: list[str], header: str = IGNORE_HEADER) -> list[str]:
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []
    missing = [rule for rule in rules if rule not in existing]
    if not missing:
        return []
    prefix = "" if not existing or existing[-1] == "" else "\n"
    with gitignore.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + "\n".join([header, *missing]) + "\n")
    return missing


def is_ignored(root: Path, relative: str) -> bool:
    try:
        return subprocess.run(["git", "check-ignore", "-q", "--", relative], cwd=root, stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def unignore_rules(root: Path, config: StoreConfig, host: str) -> list[str]:
    """Negations that re-include the committed store files when an existing rule ignores them."""
    store = config.store_dir.strip("/")
    tracked = [CONFIG_FILENAME, f"{store}/{host}/memories.db", f"{store}/{host}/memories.json"]
    if not any(is_ignored(root, path) for path in tracked):
        return []
    rules: list[str] = []
    parts = store.split("/")
    for depth in range(1, len(parts) + 1):
        rules.append("!" + "/".join(parts[:depth]) + "/")
    rules += [f"!{store}/*/", f"!{store}/*/memories.db", f"!{store}/*/memories.json", f"!{CONFIG_FILENAME}"]
    return rules


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
    negations = unignore_rules(root, config, host)
    if negations:
        # Appended last so they win over the workspace's earlier rules.
        existing = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        for rule in negations:
            if rule in existing:
                existing.remove(rule)
        (root / ".gitignore").write_text("\n".join(existing).rstrip("\n") + "\n", encoding="utf-8", newline="\n")
        _append_ignores(root / ".gitignore", negations, UNIGNORE_HEADER)
        print(f"re-included the store files that existing rules ignored ({len(negations)} rule(s))", file=out)
        remaining = [p for p in (CONFIG_FILENAME, f"{config.store_dir}/{host}/memories.db") if is_ignored(root, p)]
        if remaining:
            print(f"warning: still ignored by another source (global or nested ignore file): {', '.join(remaining)}", file=out)
    print(
        "next: restart the memory server, store or import knowledge, then run "
        "`memory-store export` and commit the host folder together with .memory-store.json",
        file=out,
    )
    return 0
