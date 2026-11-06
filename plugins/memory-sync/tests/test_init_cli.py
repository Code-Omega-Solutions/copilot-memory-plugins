import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_store_sync import cli
from memory_store_sync.config import CONFIG_FILENAME
from memory_store_sync.init import IGNORE_HEADER, command_init


class InitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def test_init_reincludes_store_ignored_by_existing_rules(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("data/\n*.db\n", encoding="utf-8")
        out = io.StringIO()
        self.assertEqual(command_init(self.root, "box", out=out), 0)
        for name in ("memories.db", "memories.json"):
            path = f"data/memory-store/box/{name}"
            ignored = subprocess.run(["git", "check-ignore", "-q", path], cwd=self.root).returncode == 0
            self.assertFalse(ignored, f"{path} still ignored: {out.getvalue()}")
        first = (self.root / ".gitignore").read_text(encoding="utf-8")
        command_init(self.root, "box", out=io.StringIO())
        self.assertEqual((self.root / ".gitignore").read_text(encoding="utf-8"), first)

    def test_init_ignores_flat_server_default_files(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        command_init(self.root, "box", out=io.StringIO())
        for path in ("data/memory-store/memories.db", "data/memory-store/memories.db-wal", "data/rag-index/vectors.db"):
            self.assertEqual(subprocess.run(["git", "check-ignore", "-q", path], cwd=self.root).returncode, 0, path)
        self.assertNotEqual(subprocess.run(["git", "check-ignore", "-q", "data/memory-store/box/memories.db"], cwd=self.root).returncode, 0)

    def test_init_requires_git(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(command_init(self.root, "box", out=io.StringIO()), 1)

    def test_init_is_idempotent_and_keeps_existing_config(self):
        (self.root / ".git").mkdir()
        (self.root / ".gitignore").write_text("node_modules/", encoding="utf-8")
        (self.root / CONFIG_FILENAME).write_text(json.dumps({"storeDir": "mem"}), encoding="utf-8")
        self.assertEqual(command_init(self.root, "box", out=io.StringIO()), 0)
        self.assertEqual(command_init(self.root, "box", out=io.StringIO()), 0)
        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(gitignore.count(IGNORE_HEADER), 1)
        self.assertIn("node_modules/\n", gitignore)
        self.assertIn("mem/*/*.db-wal", gitignore)
        self.assertTrue((self.root / "mem" / "box").is_dir())
        self.assertEqual(json.loads((self.root / CONFIG_FILENAME).read_text(encoding="utf-8")), {"storeDir": "mem"})

    def test_force_rewrites_defaults(self):
        (self.root / ".git").mkdir()
        (self.root / CONFIG_FILENAME).write_text(json.dumps({"storeDir": "mem"}), encoding="utf-8")
        command_init(self.root, "box", force=True, out=io.StringIO())
        self.assertEqual(json.loads((self.root / CONFIG_FILENAME).read_text(encoding="utf-8"))["storeDir"], "data/memory-store")


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / ".git").mkdir()
        self._env = dict(os.environ)
        for name in ("MEMORY_WORKSPACE", "PLUGIN_ROOT", "PLUGIN_DATA"):
            os.environ.pop(name, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self._tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_commands_refuse_a_workspace_that_has_not_opted_in(self):
        for command in ("status", "export", "import", "sync"):
            with self.subTest(command=command):
                code, _, err = self.run_cli(command, "--workspace", str(self.root), "--host", "box")
                self.assertEqual(code, cli.NOT_OPTED_IN_EXIT)
                self.assertIn("memory-store init", err)

    def test_init_then_status(self):
        code, out, _ = self.run_cli("init", "--workspace", str(self.root), "--host", "box")
        self.assertEqual(code, 0, out)
        code, out, _ = self.run_cli("status", "--workspace", str(self.root), "--host", "box")
        self.assertEqual(code, 0)
        self.assertIn("host:          box", out)

    def test_invalid_host_and_config_are_clean_errors(self):
        code, _, err = self.run_cli("status", "--workspace", str(self.root), "--host", "a/b")
        self.assertEqual((code, err.startswith("error:")), (1, True))
        (self.root / CONFIG_FILENAME).write_text("[]", encoding="utf-8")
        code, _, err = self.run_cli("status", "--workspace", str(self.root), "--host", "box")
        self.assertEqual((code, err.startswith("error:")), (1, True))

    def test_setup_uses_hook_workspace_instead_of_plugin_cwd(self):
        plugin = self.root / "plugin"
        plugin.mkdir()
        os.environ["PLUGIN_ROOT"] = str(plugin)
        with patch.object(cli.sys, "stdin", io.StringIO(json.dumps({"cwd": str(self.root)}))), \
                patch.object(cli.Path, "cwd", return_value=plugin), \
                patch.object(cli, "command_setup", return_value=0) as setup:
            code, _, err = self.run_cli("setup", "--hook-input", "--host", "box")
        self.assertEqual(code, 0, err)
        setup.assert_called_once_with(self.root, "box")

    def test_explicit_workspace_overrides_hook_workspace(self):
        with patch.object(cli.sys, "stdin", io.StringIO(json.dumps({"cwd": "unused"}))), \
                patch.object(cli, "command_setup", return_value=0) as setup:
            code, _, err = self.run_cli("setup", "--hook-input", "--workspace", str(self.root), "--host", "box")
        self.assertEqual(code, 0, err)
        setup.assert_called_once_with(self.root, "box")

    def test_setup_rejects_invalid_hook_input(self):
        for payload in ("", "{", "[]", "{}", '{"cwd": null}', '{"cwd": ""}'):
            with self.subTest(payload=payload), \
                    patch.object(cli.sys, "stdin", io.StringIO(payload)), \
                    patch.object(cli, "command_setup") as setup:
                code, _, err = self.run_cli("setup", "--hook-input", "--host", "box")
                self.assertEqual(code, 1)
                self.assertTrue(err.startswith("error:"), err)
                setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
