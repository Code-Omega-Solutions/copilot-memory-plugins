"""Launcher used by the plugin's mcp.json: runs the package from this plugin checkout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from memory_store_sync.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
