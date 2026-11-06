import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_store_sync import setup


class McpRegistrationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.home = self.root / "home"
        self.workspace = self.root / "workspace"
        self.plugin = self.root / "plugin"
        self.workspace.mkdir()
        (self.workspace / ".git").mkdir()
        self.plugin_config = self.plugin / "mcp.json"
        self.user_config = self.home / ".copilot" / "mcp-config.json"
        self.vscode_config = self.workspace / ".vscode" / "mcp.json"
        self.workspace_config = self.workspace / ".mcp.json"
        self.write_config(self.plugin_config)

    def write_config(self, path, key="mcpServers", name="agent-memory-mcp", server=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({key: {name: server or {"command": "agent-memory-mcp"}}}), encoding="utf-8")

    def check(self):
        out = io.StringIO()
        clean = setup.check_mcp_registrations(self.workspace, out, self.home, self.plugin)
        return clean, out.getvalue()

    def test_only_expected_plugin_registration_is_clean(self):
        clean, text = self.check()
        self.assertTrue(clean, text)
        self.assertIn("only the expected plugin registration", text)
        self.assertNotIn("warning:", text)

    def test_unrelated_servers_are_not_conflicts(self):
        self.write_config(self.user_config, name="other", server={"command": "other"})
        self.write_config(self.vscode_config, key="servers", name="remote", server={"url": "https://example.invalid"})
        self.assertTrue(self.check()[0])

    def test_user_duplicate_reports_source_without_secrets(self):
        self.write_config(self.user_config, server={"command": "agent-memory-mcp", "env": {"TOKEN": "secret-value"}})
        clean, text = self.check()
        self.assertFalse(clean)
        self.assertIn(str(self.user_config), text)
        self.assertIn("in user config", text)
        self.assertIn("different database/workspace", text)
        self.assertIn("chat.mcp.collisionBehavior=disable", text)
        self.assertNotIn("secret-value", text)

    def test_workspace_duplicates_in_both_supported_files(self):
        for path, key in ((self.vscode_config, "servers"), (self.workspace_config, "mcpServers")):
            with self.subTest(path=path):
                self.write_config(path, key=key)
                clean, text = self.check()
                self.assertFalse(clean)
                self.assertIn(str(path), text)
                self.assertIn("in workspace config", text)
                path.unlink()

    def test_user_and_workspace_duplicates_are_all_reported(self):
        for path, key in ((self.user_config, "mcpServers"), (self.vscode_config, "servers"), (self.workspace_config, "mcpServers")):
            self.write_config(path, key=key)
        clean, text = self.check()
        self.assertFalse(clean)
        self.assertEqual(text.count("warning: additional"), 3)
        for path in (self.user_config, self.vscode_config, self.workspace_config):
            self.assertIn(str(path), text)

    def test_aliases_detected_by_binary_module_or_plugin_wrapper(self):
        for server in (
            {"command": r"C:\tools\agent-memory-mcp.exe"},
            {"command": "go", "args": ["run", "github.com/ipiton/agent-memory-mcp/cmd/agent-memory-mcp"]},
            {"command": "uv", "args": ["run", "--no-project", r"C:\plugin\bin\memory-store.py", "serve"]},
            {"command": "memory-store", "args": ["serve", "--workspace", "private-value"]},
        ):
            with self.subTest(server=server):
                self.write_config(self.user_config, name="legacy-memory", server=server)
                clean, text = self.check()
                self.assertFalse(clean)
                self.assertIn("'legacy-memory'", text)
                self.assertNotIn("private-value", text)

    def test_malformed_configs_never_report_clean(self):
        for path in (self.user_config, self.vscode_config, self.workspace_config, self.plugin_config):
            for content in ('{"secret-value":', "[]", '{"servers": null}', '{"mcpServers": {"x": []}}',
                            '{"servers": {"x": {"args": "secret-value"}}}', '{"servers": {"x": {"command": null}}}'):
                with self.subTest(path=path, content=content):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                    clean, text = self.check()
                    self.assertFalse(clean)
                    self.assertIn(str(path), text)
                    self.assertIn("conflict check incomplete", text)
                    self.assertNotIn("only the expected", text)
                    self.assertNotIn("secret-value", text)
            path.unlink()
            if path == self.plugin_config:
                self.write_config(path)

    def test_unreadable_config_is_actionable_not_silent(self):
        read_text = Path.read_text

        def read(path, *args, **kwargs):
            if path == self.user_config:
                raise PermissionError("secret-value")
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", read):
            clean, text = self.check()
        self.assertFalse(clean)
        self.assertIn(str(self.user_config), text)
        self.assertIn("check permissions/encoding", text)
        self.assertIn("conflict check incomplete", text)
        self.assertNotIn("secret-value", text)

    def test_invalid_encoding_is_reported(self):
        self.user_config.parent.mkdir(parents=True)
        self.user_config.write_bytes(b"\xff")
        clean, text = self.check()
        self.assertFalse(clean)
        self.assertIn("conflict check incomplete", text)

    def test_missing_plugin_config_is_not_conflict_free(self):
        self.plugin_config.unlink()
        clean, text = self.check()
        self.assertFalse(clean)
        self.assertIn("expected plugin MCP config is missing", text)

    def test_plugin_alias_is_additional_not_expected(self):
        self.write_config(self.plugin_config, name="alias")
        clean, text = self.check()
        self.assertFalse(clean)
        self.assertIn("in plugin config", text)
        self.assertIn("expected agent-memory-mcp registration is missing", text)

    def test_expected_plugin_entry_does_not_hide_an_additional_plugin_registration(self):
        config = {
            "mcpServers": {
                "agent-memory-mcp": {"command": "agent-memory-mcp"},
                "legacy": {"command": "memory-store", "args": ["serve"]},
            }
        }
        self.plugin_config.write_text(json.dumps(config), encoding="utf-8")
        clean, text = self.check()
        self.assertFalse(clean)
        self.assertEqual(text.count("warning: additional"), 1)
        self.assertIn("'legacy'", text)
        self.assertNotIn("registration is missing", text)

    def test_setup_with_duplicate_is_idempotent_and_read_only_for_mcp_configs(self):
        self.write_config(self.user_config)
        original = self.user_config.read_bytes()
        env = {"PLUGIN_DATA": str(self.root / "data")}
        snapshots = []
        with patch.object(setup.Path, "home", return_value=self.home):
            for _ in range(2):
                out = io.StringIO()
                status = setup.command_setup(self.workspace, "box", env, out, install=lambda *args: True)
                self.assertEqual(status, 0, out.getvalue())
                self.assertIn("setup complete with MCP registration warnings", out.getvalue())
                self.assertIn(str(self.user_config), out.getvalue())
                self.assertEqual(self.user_config.read_bytes(), original)
                snapshots.append({
                    str(path.relative_to(self.workspace)): path.read_bytes()
                    for path in self.workspace.rglob("*") if path.is_file()
                })
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertFalse(self.workspace_config.exists())
        self.assertFalse(self.vscode_config.exists())

    def test_setup_with_malformed_config_does_not_claim_clean_completion(self):
        self.workspace_config.write_text("{", encoding="utf-8")
        with patch.object(setup.Path, "home", return_value=self.home):
            out = io.StringIO()
            status = setup.command_setup(self.workspace, "box", {}, out, install=lambda *args: True)
        self.assertEqual(status, 0)
        self.assertIn("conflict check incomplete", out.getvalue())
        self.assertIn("setup complete with MCP registration warnings", out.getvalue())
        self.assertNotIn("only the expected", out.getvalue())
        self.assertEqual(self.workspace_config.read_text(encoding="utf-8"), "{")


if __name__ == "__main__":
    unittest.main()
