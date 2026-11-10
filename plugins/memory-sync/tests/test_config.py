import json
import tempfile
import unittest
from pathlib import Path

from memory_store_sync import config


class ParseConfigTests(unittest.TestCase):
    def test_defaults_apply_to_an_empty_object(self):
        parsed = config.parse_config({})
        self.assertEqual(parsed.store_dir, "data/memory-store")
        self.assertEqual(parsed.rag_dir, "data/rag-index")
        self.assertEqual(parsed.module, config.DEFAULT_MODULE)
        self.assertEqual(parsed.server_env()["MCP_STDIO_MODE"], "line")

    def test_extra_env_extends_and_overrides_defaults(self):
        parsed = config.parse_config({"server": {"env": {"MCP_ALLOW_DIRS": "docs", "MCP_STEWARD_MODE": "auto"}}})
        env = parsed.server_env()
        self.assertEqual(env["MCP_ALLOW_DIRS"], "docs")
        self.assertEqual(env["MCP_STEWARD_MODE"], "auto")
        self.assertEqual(env["MCP_RAG_ENABLED"], "false")

    def test_invalid_values_are_rejected(self):
        cases = [
            [],
            {"storeDir": "/abs"},
            {"storeDir": "../outside"},
            {"ragDir": "C:/x"},
            {"server": []},
            {"server": {"env": {"A": 1}}},
            {"server": {"env": {"MCP_MEMORY_DB_PATH": "x"}}},
            {"server": {"module": "github.com/x/y"}},
            {"server": {"binary": ""}},
            {"excludedMemoryIds": []},
            {"excludedMemoryIds": {"obsolete": ""}},
            {"excludedMemoryIds": {" ": "obsolete"}},
            {"excludedMemoryIds": {"obsolete": 1}},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(config.ConfigError):
                config.parse_config(case)

    def test_round_trip_through_json(self):
        original = config.StoreConfig(
            store_dir="mem", binary="/opt/server", extra_env={"MCP_ALLOW_DIRS": "docs"},
            excluded_memory_ids={"obsolete": "Replaced by maintained guidance"},
        )
        self.assertEqual(config.parse_config(original.to_json()), original)


class LoadConfigTests(unittest.TestCase):
    def test_missing_file_means_not_opted_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(config.load_config(Path(tmp)))

    def test_malformed_file_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / config.CONFIG_FILENAME).write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(config.ConfigError, "memory-store.json"):
                config.load_config(Path(tmp))

    def test_valid_file_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / config.CONFIG_FILENAME).write_text(json.dumps({"storeDir": "m"}), encoding="utf-8")
            self.assertEqual(config.load_config(Path(tmp)).store_dir, "m")


if __name__ == "__main__":
    unittest.main()
