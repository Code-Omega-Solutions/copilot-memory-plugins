import io
import tempfile
import unittest
from pathlib import Path

from memory_store_sync import server
from memory_store_sync.config import StoreConfig
from memory_store_sync.workspace import StoreLocation


class ServerCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = {"PLUGIN_DATA": self._tmp.name}

    def test_environment_binary_wins(self):
        command = server.server_command(StoreConfig(binary="/cfg"), {server.BINARY_ENV: "/env"}, which=lambda _: None)
        self.assertEqual(command, ["/env"])

    def test_configured_binary_beats_go(self):
        self.assertEqual(server.server_command(StoreConfig(binary="/cfg"), self.data, which=lambda _: "/go"), ["/cfg"])

    def test_go_runs_the_pinned_module(self):
        config = StoreConfig()
        self.assertEqual(server.server_command(config, self.data, which=lambda _: "/go"), ["/go", "run", config.module])

    def test_installed_binary_beats_go_run(self):
        config = StoreConfig()
        managed = server.managed_binary_path(config, self.data)
        managed.parent.mkdir(parents=True)
        managed.write_text("")
        self.assertEqual(server.server_command(config, self.data, which=lambda _: "/go"), [str(managed)])

    def test_missing_runtime_is_reported(self):
        with self.assertRaisesRegex(server.NoServerRuntime, "go install"):
            server.server_command(StoreConfig(), self.data, which=lambda _: None)


class ServerEnvironmentTests(unittest.TestCase):
    def test_paths_are_relative_to_the_server_directory_when_possible(self):
        root = Path(tempfile.gettempdir()).resolve() / "ws"
        location = StoreLocation(
            workspace=root,
            config=StoreConfig(extra_env={"MCP_ALLOW_DIRS": "docs"}),
            store_root=root / "data" / "memory-store",
            rag_root=root / "data" / "rag-index",
            server_cwd=root,
            synced=True,
        )
        env = server.server_environment(location, "box", {"KEEP": "1"})
        self.assertEqual(env["MCP_MEMORY_DB_PATH"], "data/memory-store/box/memories.db")
        self.assertEqual(env["MCP_RAG_INDEX_PATH"], "data/rag-index/box")
        self.assertEqual(env["MCP_ALLOW_DIRS"], "docs")
        self.assertEqual(env["KEEP"], "1")

    def test_paths_outside_the_server_directory_stay_absolute(self):
        base = Path(tempfile.gettempdir()).resolve()
        location = StoreLocation(None, StoreConfig(), base / "a", base / "b", base / "c", False)
        env = server.server_environment(location, "box", {})
        self.assertEqual(Path(env["MCP_MEMORY_DB_PATH"]), base / "a" / "box" / "memories.db")


class ServeTests(unittest.TestCase):
    def test_serve_without_runtime_exits_with_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            location = StoreLocation(None, StoreConfig(), root / "s", root / "r", root, False, ("note",))
            original = server.server_command

            def no_runtime(*_args, **_kwargs):
                raise server.NoServerRuntime("missing")

            server.server_command = no_runtime
            try:
                log = io.StringIO()
                self.assertEqual(server.serve(location, "box", [], log=log), server.NO_RUNTIME_EXIT)
            finally:
                server.server_command = original
            self.assertIn("note", log.getvalue())
            self.assertIn("missing", log.getvalue())


if __name__ == "__main__":
    unittest.main()
