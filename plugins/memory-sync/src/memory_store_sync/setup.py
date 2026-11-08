"""``setup``: idempotent one-shot provisioning of a workspace.

Checks MCP registrations and prerequisites, installs the pinned server binary, opts the
workspace in (``init``), writes the agent instructions and seeds the own
database from the committed exports. Safe to run on every session start.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, TextIO

from .config import CONFIG_FILENAME, StoreConfig
from .init import command_init
from .server import BINARY_ENV, managed_binary_path
from .store import host_paths
from .workspace import PACKAGE_PLUGIN_ROOT, StoreLocation, find_git_root, locate_store

INSTRUCTIONS_PATH = Path(".github") / "copilot-instructions.md"
BEGIN_MARKER = "<!-- memory-sync:begin (managed by the memory-sync plugin; edits inside are overwritten) -->"
END_MARKER = "<!-- memory-sync:end -->"
DISABLE_ENV = "MEMORY_STORE_AUTO_SETUP"

INSTRUCTIONS = """\
## Project memory (memory-sync)

This workspace keeps durable project memory in the `agent-memory-mcp` MCP server,
one store per workstation, synchronized through git.

- At session start, run `memory-store status` and, when another host has pending
  records, `memory-store import`. Follow the `memory-sync` skill.
- Store decisions, verified fixes, incidents and runbooks with the memory tools;
  recall before re-deriving earlier findings.
- At session end, run `memory-store export` and commit the own host folder under
  the store directory together with `.memory-store.json`.
- Never edit `memories.db` or `memories.json` by hand and never write into another
  host's folder.
- If `memory-store` is not on `PATH`, run it with `uv run --no-project` on the
  plugin's `bin/memory-store.py`, or install it with
  `uv tool install "git+https://github.com/Code-Omega-Solutions/copilot-memory-plugins#subdirectory=plugins/memory-sync"`.
"""


def render_block() -> str:
    return f"{BEGIN_MARKER}\n{INSTRUCTIONS}{END_MARKER}\n"


def write_instructions(root: Path) -> str:
    """Create or refresh the managed block; returns ``created``, ``updated`` or ``unchanged``."""
    path = root / INSTRUCTIONS_PATH
    block = render_block()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8", newline="\n")
        return "created"
    text = path.read_text(encoding="utf-8")
    start = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER, start) if start != -1 else -1
    if start != -1 and end != -1:
        new = text[:start] + block + text[end + len(END_MARKER):].lstrip("\n")
    else:
        new = text.rstrip("\n") + "\n\n" + block if text.strip() else block
    if new == text:
        return "unchanged"
    path.write_text(new, encoding="utf-8", newline="\n")
    return "updated"


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _is_memory_registration(name: str, server: dict) -> bool:
    if name.lower().replace("_", "-") == "agent-memory-mcp":
        return True
    command = server.get("command", "").lower()
    args = [arg.lower() for arg in server.get("args", [])]
    tokens = [command, *args]
    if any("agent-memory-mcp" in token for token in tokens):
        return True
    return "serve" in args and any(
        token.replace("\\", "/").rsplit("/", 1)[-1] in
        {"memory-store", "memory-store.exe", "memory-store.py"}
        for token in tokens
    )


def check_mcp_registrations(
    root: Path,
    out: TextIO,
    home: Path | None = None,
    plugin_root: Path = PACKAGE_PLUGIN_ROOT,
) -> bool:
    """Warn about extra registrations or an incomplete scan without changing configs."""
    home = Path.home() if home is None else home
    plugin_config = plugin_root / "mcp.json"
    sources = [
        ("plugin", plugin_config),
        ("user", home / ".copilot" / "mcp-config.json"),
        ("workspace", root / ".vscode" / "mcp.json"),
        ("workspace", root / ".mcp.json"),
    ]
    clean = True
    expected = False
    for scope, path in sources:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            if scope == "plugin":
                clean = False
                print(f"warning: expected plugin MCP config is missing: {path}; conflict check incomplete", file=out)
            continue
        except (OSError, UnicodeError):
            clean = False
            print(f"warning: cannot read {scope} MCP config: {path}; check permissions/encoding; conflict check incomplete", file=out)
            continue
        try:
            config = json.loads(text)
            if not isinstance(config, dict):
                raise ValueError
            registrations = []
            for key in ("mcpServers", "servers"):
                servers = config.get(key, {})
                if not isinstance(servers, dict):
                    raise ValueError
                for name, server in servers.items():
                    if not isinstance(server, dict):
                        raise ValueError
                    if not isinstance(server.get("command", ""), str):
                        raise ValueError
                    args = server.get("args", [])
                    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                        raise ValueError
                    if _is_memory_registration(name, server):
                        registrations.append(name)
        except ValueError:
            clean = False
            print(f"warning: invalid JSON or MCP server structure in {scope} config: {path}; fix the config; conflict check incomplete", file=out)
            continue
        for name in registrations:
            if scope == "plugin" and name == "agent-memory-mcp" and not expected:
                expected = True
                continue
            clean = False
            print(f"warning: additional agent-memory-mcp registration {name!r} in {scope} config: {path}", file=out)
        if scope == "plugin" and not expected:
            clean = False
            print(f"warning: expected agent-memory-mcp registration is missing from {path}; conflict check incomplete", file=out)
    if clean:
        print("MCP registrations: only the expected plugin registration found in checked configs", file=out)
    else:
        print(
            "MCP routing/config warning: clients may shadow a registration or expose multiple memory servers, "
            "so tools can use a different database/workspace from memory-store setup/import/export. "
            "Review the listed configs and keep one intended registration active; if using a workspace override, "
            "disable the plugin registration in your client and set an explicit serve --workspace DIR. "
            "In VS Code, workspace setting chat.mcp.collisionBehavior=disable disables lower-priority "
            "same-name duplicates; suffix enables both with numeric suffixes. This does not fix differently named aliases. "
            "Restart the affected MCP connections after manual changes. No MCP configs were changed.",
            file=out,
        )
    return clean


def install_server(
    config: StoreConfig,
    environ: Mapping[str, str],
    out: TextIO,
    which: Callable[[str], str | None] = shutil.which,
    run: Runner = subprocess.run,
) -> bool:
    """Make sure a server runtime exists; returns False when none can be provided."""
    explicit = environ.get(BINARY_ENV, "").strip() or config.binary
    if explicit:
        found = Path(explicit).is_file() or which(explicit)
        print(f"server binary {explicit}: {'found' if found else 'NOT FOUND'}", file=out)
        return bool(found)
    target = managed_binary_path(config, environ)
    if target.is_file():
        print(f"server binary already installed: {target}", file=out)
        return True
    go = which("go")
    if go is None:
        print(
            "error: `go` is not on PATH and no server binary is configured; install Go 1.22+ "
            "(https://go.dev/dl/) or set AGENT_MEMORY_MCP_BIN, then run `memory-store setup` again",
            file=out,
        )
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"installing {config.module} (first run compiles it, about a minute) ...", file=out)
    env = {**environ, "GOBIN": str(target.parent)}
    result = run([go, "install", config.module], env=env, capture_output=True, text=True)
    produced = target.parent / ("agent-memory-mcp.exe" if sys.platform == "win32" else "agent-memory-mcp")
    if result.returncode != 0 or not produced.is_file():
        print(f"error: go install failed:\n{(result.stderr or result.stdout).strip()}", file=out)
        return False
    print(f"installed {produced}", file=out)
    return True


def command_setup(
    root: Path,
    host: str,
    environ: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    install: Callable[..., bool] = install_server,
    importer: Callable[[StoreLocation, str, bool], int] | None = None,
) -> int:
    out = out or sys.stdout
    env = os.environ if environ is None else environ
    if env.get(DISABLE_ENV, "").strip().lower() in {"0", "false", "no", "off"}:
        print(f"setup skipped: {DISABLE_ENV} disables it", file=out)
        return 0
    if find_git_root(root) is None:
        print(f"error: {root} is not inside a git work tree", file=sys.stderr)
        return 1
    if shutil.which("git") is None:
        print("error: git is not on PATH", file=sys.stderr)
        return 1

    registrations_clean = check_mcp_registrations(root, out)
    configuration_created = not (root / CONFIG_FILENAME).is_file()
    status = command_init(root, host, out=out, announce_next=False)
    if status:
        return status
    location = locate_store(str(root), environ=env)
    print(f"instructions {INSTRUCTIONS_PATH.as_posix()}: {write_instructions(location.workspace or root)}", file=out)

    managed_server = not (env.get(BINARY_ENV, "").strip() or location.config.binary)
    managed_binary = managed_binary_path(location.config, env)
    server_was_installed = managed_server and managed_binary.is_file()
    ready = install(location.config, env, out)
    server_installed = ready and managed_server and not server_was_installed and managed_binary.is_file()
    if ready and importer is None:
        from .sync import command_import as importer
    paths = host_paths(host, location.store_root, location.rag_root)
    if ready and not paths.db_path.exists() and any(location.store_root.glob("*/memories.json")):
        print("seeding the own database from the committed exports ...", file=out)
        if importer(location, host, False):
            print("warning: seeding failed; run `memory-store import` later", file=out)
    if ready:
        print("setup complete" if registrations_clean else "setup complete with MCP registration warnings: review the messages above", file=out)
        if configuration_created or server_installed:
            print(
                "restart required: restart the `agent-memory-mcp` connection to apply the workspace settings.",
                file=out,
            )
            print(
                "In VS Code: MCP: List Servers -> agent-memory-mcp -> Restart. "
                "The active connection has not been verified.",
                file=out,
            )
    else:
        print("setup incomplete: see the error above", file=out)
    return 0 if ready else 2
