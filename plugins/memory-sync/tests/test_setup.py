import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_store_sync import setup as setup_mod
from memory_store_sync.config import CONFIG_FILENAME, StoreConfig


def git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


class InstructionsTests(unittest.TestCase):
    def test_create_update_and_preserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(setup_mod.write_instructions(root), "created")
            self.assertEqual(setup_mod.write_instructions(root), "unchanged")
            path = root / setup_mod.INSTRUCTIONS_PATH
            text = path.read_text(encoding="utf-8")
            path.write_text("# Mine\n\n" + text.replace("Project memory", "Old"), encoding="utf-8")
            self.assertEqual(setup_mod.write_instructions(root), "updated")
            result = path.read_text(encoding="utf-8")
            self.assertTrue(result.startswith("# Mine"))
            self.assertEqual(result.count(setup_mod.BEGIN_MARKER), 1)
            self.assertIn("Project memory", result)

    def test_appends_to_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / setup_mod.INSTRUCTIONS_PATH
            path.parent.mkdir(parents=True)
            path.write_text("# Existing\n", encoding="utf-8")
            self.assertEqual(setup_mod.write_instructions(Path(tmp)), "updated")
            self.assertTrue(path.read_text(encoding="utf-8").startswith("# Existing\n\n<!-- memory-sync:begin"))


class InstallServerTests(unittest.TestCase):
    def test_missing_go_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            ok = setup_mod.install_server(StoreConfig(), {"PLUGIN_DATA": tmp}, out, which=lambda _: None)
            self.assertFalse(ok)
            self.assertIn("go", out.getvalue())

    def test_go_install_targets_managed_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PLUGIN_DATA": tmp}
            config = StoreConfig()
            target = setup_mod.managed_binary_path(config, env)
            calls = []

            def run(cmd, **kwargs):
                calls.append((cmd, kwargs["env"]["GOBIN"]))
                target.write_text("")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            self.assertTrue(setup_mod.install_server(config, env, io.StringIO(), which=lambda _: "/go", run=run))
            self.assertEqual(calls, [(["/go", "install", config.module], str(target.parent))])
            self.assertTrue(setup_mod.install_server(config, env, io.StringIO(), which=lambda _: "/go", run=run))
            self.assertEqual(len(calls), 1)


class CommandSetupTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.home = Path(home.name)
        self.addCleanup(home.cleanup)
        home_patch = patch.object(setup_mod.Path, "home", return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    @staticmethod
    def install_managed_server(config, env, out):
        target = setup_mod.managed_binary_path(config, env)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("test server", encoding="utf-8")
        return True

    def test_setup_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_repo(root)
            env = {"PLUGIN_DATA": str(root / "plugin-data")}
            for index in range(2):
                out = io.StringIO()
                status = setup_mod.command_setup(root, "laptop", env, out, install=self.install_managed_server)
                self.assertEqual(status, 0, out.getvalue())
                self.assertIn("only the expected plugin registration", out.getvalue())
                self.assertNotIn("warning:", out.getvalue())
                self.assertNotIn("next: restart the memory server", out.getvalue())
                if index == 0:
                    self.assertIn("restart required", out.getvalue())
                else:
                    self.assertNotIn("restart required", out.getvalue())
            self.assertTrue((root / CONFIG_FILENAME).is_file())
            self.assertTrue((root / setup_mod.INSTRUCTIONS_PATH).is_file())
            self.assertTrue((root / "data" / "memory-store" / "laptop").is_dir())
            self.assertEqual((root / ".gitignore").read_text().count("memory-sync:"), 1)

    def test_standalone_init_keeps_restart_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_repo(root)
            out = io.StringIO()

            status = setup_mod.command_init(root, "laptop", out=out)

            self.assertEqual(status, 0)
            self.assertIn("next: restart the memory server", out.getvalue())

    def test_server_installation_requires_restart_when_workspace_is_already_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_repo(root)
            setup_mod.command_init(root, "laptop", out=io.StringIO())
            out = io.StringIO()

            status = setup_mod.command_setup(
                root, "laptop", {"PLUGIN_DATA": str(root / "plugin-data")}, out,
                install=self.install_managed_server,
            )

            self.assertEqual(status, 0, out.getvalue())
            self.assertIn("restart required", out.getvalue())
            self.assertIn("MCP: List Servers", out.getvalue())
            self.assertIn("agent-memory-mcp", out.getvalue())
            self.assertIn("Restart", out.getvalue())

    def test_registration_warning_is_separate_from_restart_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_repo(root)
            user_config = self.home / ".copilot" / "mcp-config.json"
            user_config.parent.mkdir(parents=True)
            user_config.write_text(
                '{"mcpServers":{"agent-memory-mcp":{"command":"agent-memory-mcp"}}}',
                encoding="utf-8",
            )
            out = io.StringIO()

            status = setup_mod.command_setup(
                root, "laptop", {"PLUGIN_DATA": str(root / "plugin-data")}, out,
                install=self.install_managed_server,
            )

            self.assertEqual(status, 0, out.getvalue())
            self.assertIn("setup complete with MCP registration warnings", out.getvalue())
            self.assertIn("restart required", out.getvalue())
            self.assertNotIn("active connection uses", out.getvalue())

    def test_missing_runtime_reports_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_repo(root)
            status = setup_mod.command_setup(root, "laptop", {}, io.StringIO(), install=lambda *a: False)
            self.assertEqual(status, 2)

    def test_seeds_database_from_other_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_repo(root)
            other = root / "data" / "memory-store" / "other"
            other.mkdir(parents=True)
            (other / "memories.json").write_text("{}", encoding="utf-8")
            seeded = []
            setup_mod.command_setup(
                root, "laptop", {"PLUGIN_DATA": str(root / "pd")}, io.StringIO(),
                install=lambda *a: True, importer=lambda loc, host, dry: seeded.append(host) or 0,
            )
            self.assertEqual(seeded, ["laptop"])

    def test_opt_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_repo(root)
            self.assertEqual(setup_mod.command_setup(root, "h", {setup_mod.DISABLE_ENV: "0"}, io.StringIO()), 0)
            self.assertFalse((root / CONFIG_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
