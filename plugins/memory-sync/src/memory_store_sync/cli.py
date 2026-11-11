"""Command-line entry point: ``memory-store <command>``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError
from .init import command_init
from .server import serve
from .setup import command_setup
from .store import resolve_host, validate_host
from .sync import command_export, command_import, command_status
from .workspace import locate_store, resolve_workspace

NOT_OPTED_IN_EXIT = 1


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", help="workspace root (default: MEMORY_WORKSPACE, then the git work tree of the cwd)")
    common.add_argument("--host", help="host key (default: MEMORY_STORE_HOST, then the system hostname)")

    parser = argparse.ArgumentParser(prog="memory-store", description="Per-host agent memory store synchronized through git.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    serve_parser = commands.add_parser("serve", parents=[common], help="run the memory MCP server on stdio")
    serve_parser.add_argument("server_args", nargs=argparse.REMAINDER, help="arguments after -- are passed to the server")
    commands.add_parser("status", parents=[common], help="show the own store and the other hosts' exports")
    commands.add_parser("export", parents=[common], help="write the own durable export")
    for name, text in (("import", "add records from other hosts' exports"), ("sync", "import, then export")):
        sub = commands.add_parser(name, parents=[common], help=text)
        sub.add_argument("--dry-run", action="store_true", help="report what import would do without writing")
    init_parser = commands.add_parser("init", parents=[common], help="opt the workspace in to the synchronized store")
    init_parser.add_argument("--force", action="store_true", help="overwrite an existing .memory-store.json with defaults")
    setup_parser = commands.add_parser("setup", parents=[common], help="install the server, init the workspace, write instructions, seed the database")
    setup_parser.add_argument("--hook-input", action="store_true", help="read the session hook's workspace cwd from JSON on stdin")
    return parser


def _host(args: argparse.Namespace) -> str:
    return validate_host(args.host) if args.host else resolve_host()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        host = _host(args)
        if args.command == "setup" and args.hook_input:
            payload = json.load(sys.stdin)
            if not isinstance(payload, dict) or not isinstance(payload.get("cwd"), str) or not payload["cwd"].strip():
                raise ValueError("session hook input must contain a non-empty cwd string")
            if not args.workspace:
                args.workspace = payload["cwd"]
        if args.command in ("init", "setup"):
            root, notes = resolve_workspace(args.workspace, Path.cwd(), os.environ)
            if root is None:
                for note in notes:
                    print(note, file=sys.stderr)
                print("error: no workspace found; pass --workspace", file=sys.stderr)
                return NOT_OPTED_IN_EXIT
            if args.command == "setup":
                return command_setup(root, host)
            return command_init(root, host, force=args.force)

        location = locate_store(args.workspace, require_config=args.command == "serve")
        if args.command == "serve":
            server_args = args.server_args[1:] if args.server_args[:1] == ["--"] else args.server_args
            return serve(location, host, server_args)
        if not location.synced:
            for note in location.notes:
                print(note, file=sys.stderr)
            print("error: this workspace has not opted in; run `memory-store init` first", file=sys.stderr)
            return NOT_OPTED_IN_EXIT
        if args.command == "status":
            return command_status(location, host)
        if args.command == "export":
            return command_export(location, host)
        if args.command == "import":
            return command_import(location, host, args.dry_run)
        return command_import(location, host, args.dry_run) or command_export(location, host)
    except (ConfigError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return NOT_OPTED_IN_EXIT


if __name__ == "__main__":
    sys.exit(main())
