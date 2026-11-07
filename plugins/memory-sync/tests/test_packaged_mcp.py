import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def make_test_server(path: Path) -> Path:
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "Path(os.environ['MCP_TEST_CAPTURE']).write_text(json.dumps({"
        "'cwd': os.getcwd(), "
        "'db': os.environ['MCP_MEMORY_DB_PATH']"
        "}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


@unittest.skipUnless(os.name == "posix" and Path("/tmp").is_dir(), "Unix plugin-launch integration")
class PackagedMcpTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.plugin_install = self.tmp / "plugin-install"
        self.plugin_install.mkdir()
        self.manifest = json.loads((PLUGIN_ROOT / "mcp.json").read_text(encoding="utf-8"))
        self.registration = self.manifest["mcpServers"]["agent-memory-mcp"]

    def launch(self, workspace_argument: str):
        runner = shutil.which(self.registration["command"])
        if runner is None:
            self.skipTest(f"{self.registration['command']} is required by the packaged MCP registration")

        args = [
            arg.replace("${PLUGIN_ROOT}", str(PLUGIN_ROOT)).replace(
                "${workspaceFolder}", workspace_argument
            )
            for arg in self.registration["args"]
        ]
        env = os.environ.copy()
        env["PLUGIN_ROOT"] = str(PLUGIN_ROOT)
        env["PLUGIN_DATA"] = str(self.tmp / "plugin-data")
        capture = self.tmp / "server.json"
        env["MCP_TEST_CAPTURE"] = str(capture)
        env["AGENT_MEMORY_MCP_BIN"] = str(make_test_server(self.tmp / "fake-server"))
        result = subprocess.run(
            [runner, *args],
            cwd=self.plugin_install,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, capture

    def test_packaged_registration_starts_against_opted_in_workspace(self):
        workspace = self.tmp / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        (workspace / ".memory-store.json").write_text("{}", encoding="utf-8")

        result, capture = self.launch(str(workspace))

        self.assertEqual(result.returncode, 0, result.stderr)
        launched = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(Path(launched["cwd"]), workspace)
        self.assertTrue(launched["db"].startswith("data/memory-store/"))
        self.assertIn(f"workspace={workspace}", result.stderr)
        self.assertIn("synced=yes", result.stderr)

    def test_packaged_registration_reports_unexpanded_workspace(self):
        result, capture = self.launch("${workspaceFolder}")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(capture.is_file())
        self.assertIn("unexpanded placeholder", result.stderr)
        self.assertIn("using the unsynced fallback store", result.stderr)
        self.assertIn("synced=no", result.stderr)


if __name__ == "__main__":
    unittest.main()
