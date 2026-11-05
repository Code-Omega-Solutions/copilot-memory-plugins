import json
import tempfile
import unittest
from pathlib import Path

from memory_store_sync import workspace
from memory_store_sync.config import CONFIG_FILENAME


def make_repo(root: Path, opted_in: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir()
    if opted_in:
        (root / CONFIG_FILENAME).write_text(json.dumps({"storeDir": "mem"}), encoding="utf-8")
    return root


class ResolveWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.repo = make_repo(self.tmp / "repo")
        self.other = make_repo(self.tmp / "other")
        self.plugin = self.tmp / "plugin"
        self.plugin.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_environment_override_wins(self):
        root, _ = workspace.resolve_workspace(str(self.repo), self.other, {"MEMORY_WORKSPACE": str(self.other)})
        self.assertEqual(root, self.other)

    def test_argument_beats_working_directory(self):
        root, _ = workspace.resolve_workspace(str(self.repo), self.other, {})
        self.assertEqual(root, self.repo)

    def test_subdirectory_resolves_to_git_root(self):
        sub = self.repo / "a" / "b"
        sub.mkdir(parents=True)
        root, _ = workspace.resolve_workspace(None, sub, {})
        self.assertEqual(root, self.repo)

    def test_unexpanded_placeholder_is_ignored_with_a_note(self):
        root, notes = workspace.resolve_workspace("${workspaceFolder}", self.repo, {})
        self.assertEqual(root, self.repo)
        self.assertIn("unexpanded placeholder", notes[0])

    def test_missing_directory_is_ignored(self):
        root, notes = workspace.resolve_workspace(str(self.tmp / "nope"), self.repo, {})
        self.assertEqual(root, self.repo)
        self.assertIn("not a directory", notes[0])

    def test_plugin_directory_is_never_the_workspace(self):
        root, notes = workspace.resolve_workspace(None, self.plugin, {"PLUGIN_ROOT": str(self.plugin)})
        self.assertIsNone(root)
        self.assertTrue(notes)

    def test_git_repo_inside_plugin_data_is_rejected(self):
        nested = make_repo(self.plugin / "cache")
        root, notes = workspace.resolve_workspace(None, nested, {"PLUGIN_DATA": str(self.plugin)})
        self.assertIsNone(root)
        self.assertIn("plugin's own directories", notes[-1])

    def test_working_directory_outside_git_is_rejected_but_explicit_dir_is_accepted(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertIsNone(workspace.resolve_workspace(None, plain, {})[0])
        self.assertEqual(workspace.resolve_workspace(str(plain), self.plugin, {})[0], plain)


class LocateStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def test_opted_in_workspace_uses_configured_store(self):
        repo = make_repo(self.tmp / "repo")
        location = workspace.locate_store(None, repo, {})
        self.assertTrue(location.synced)
        self.assertEqual(location.store_root, repo / "mem")
        self.assertEqual(location.server_cwd, repo)

    def test_workspace_without_config_uses_fallback(self):
        repo = make_repo(self.tmp / "repo", opted_in=False)
        data = self.tmp / "data"
        location = workspace.locate_store(None, repo, {"PLUGIN_DATA": str(data)})
        self.assertFalse(location.synced)
        self.assertEqual(location.store_root, data / "memory-store")
        self.assertEqual(location.server_cwd, repo)
        self.assertIn("memory-store init", location.notes[-1])

    def test_no_workspace_runs_in_fallback_root(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        data = self.tmp / "data"
        location = workspace.locate_store(None, plain, {"COPILOT_PLUGIN_DATA": str(data)})
        self.assertIsNone(location.workspace)
        self.assertEqual(location.server_cwd, data)

    def test_fallback_defaults_to_home(self):
        self.assertEqual(workspace.fallback_root({"PLUGIN_DATA": "${PLUGIN_DATA}"}).name, ".copilot-memory")


if __name__ == "__main__":
    unittest.main()
