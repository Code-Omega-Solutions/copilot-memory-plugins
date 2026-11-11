import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from memory_store_sync import cli, workspace
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

    def test_explicit_workspace_wins_over_environment(self):
        root, _ = workspace.resolve_workspace(str(self.repo), self.other, {"MEMORY_WORKSPACE": str(self.other)})
        self.assertEqual(root, self.repo)

    def test_environment_workspace_is_used_when_no_argument_is_supplied(self):
        root, _ = workspace.resolve_workspace(None, self.repo, {"MEMORY_WORKSPACE": str(self.other)})
        self.assertEqual(root, self.other)

    def test_argument_beats_working_directory(self):
        root, _ = workspace.resolve_workspace(str(self.repo), self.other, {})
        self.assertEqual(root, self.repo)

    def test_subdirectory_resolves_to_git_root(self):
        sub = self.repo / "a" / "b"
        sub.mkdir(parents=True)
        root, _ = workspace.resolve_workspace(None, sub, {})
        self.assertEqual(root, self.repo)

    def test_unexpanded_placeholder_fails_closed_instead_of_using_cwd(self):
        with self.assertRaisesRegex(workspace.WorkspaceRoutingError, "unexpanded placeholder"):
            workspace.resolve_workspace("${workspaceFolder}", self.repo, {})

    def test_missing_explicit_directory_fails_closed_instead_of_using_cwd(self):
        with self.assertRaisesRegex(workspace.WorkspaceRoutingError, "existing directory"):
            workspace.resolve_workspace(str(self.tmp / "nope"), self.repo, {})

    def test_empty_explicit_workspace_fails_closed(self):
        with self.assertRaisesRegex(workspace.WorkspaceRoutingError, "is empty"):
            workspace.resolve_workspace("", self.repo, {})

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

    def test_worktree_argument_isolated_from_parent_and_stale_environment(self):
        parent = make_repo(self.tmp / "parent")
        child = self.tmp / "child-worktree"
        child.mkdir()
        (child / ".git").write_text("gitdir: ../parent/.git/worktrees/child\n", encoding="utf-8")
        (child / CONFIG_FILENAME).write_text(json.dumps({"storeDir": "child-memory"}), encoding="utf-8")

        location = workspace.locate_store(
            str(child),
            parent,
            {"MEMORY_WORKSPACE": str(parent)},
            require_config=True,
        )

        self.assertEqual(location.workspace, child)
        self.assertEqual(location.store_root, child / "child-memory")
        self.assertNotEqual(location.store_root, parent / "mem")


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

    def test_server_refuses_to_use_fallback_for_a_resolved_unconfigured_workspace(self):
        repo = make_repo(self.tmp / "repo", opted_in=False)
        with self.assertRaisesRegex(workspace.WorkspaceRoutingError, "memory-store setup"):
            workspace.locate_store(str(repo), self.tmp, {}, require_config=True)

    def test_no_workspace_runs_in_fallback_root(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        data = self.tmp / "data"
        location = workspace.locate_store(
            None,
            plain,
            {"COPILOT_PLUGIN_DATA": str(data)},
            require_config=True,
        )
        self.assertIsNone(location.workspace)
        self.assertEqual(location.server_cwd, data)

    def test_fallback_defaults_to_home(self):
        self.assertEqual(workspace.fallback_root({"PLUGIN_DATA": "${PLUGIN_DATA}"}).name, ".copilot-memory")

    def test_cli_server_startup_rejects_unexpanded_workspace_without_fallback(self):
        error = io.StringIO()
        with redirect_stderr(error):
            status = cli.main(["serve", "--workspace", "${workspaceFolder}"])

        self.assertNotEqual(status, 0)
        self.assertIn("unexpanded placeholder", error.getvalue())
        self.assertIn("Configure a workspace-scoped server", error.getvalue())
        self.assertNotIn("using the unsynced fallback store", error.getvalue())


if __name__ == "__main__":
    unittest.main()
