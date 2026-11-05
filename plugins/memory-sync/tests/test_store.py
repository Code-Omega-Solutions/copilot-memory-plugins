import json
import tempfile
import unittest
from pathlib import Path

from memory_store_sync import store


def record(memory_id, memory_type="semantic", **extra):
    base = {"id": memory_id, "type": memory_type, "title": f"t{memory_id}", "content": f"c{memory_id}"}
    base.update(extra)
    return base


class HostKeyTests(unittest.TestCase):
    def test_override_wins_over_hostname(self):
        self.assertEqual(store.resolve_host({"MEMORY_STORE_HOST": " box-a "}), "box-a")

    def test_hostname_is_used_without_override(self):
        self.assertTrue(store.resolve_host({}))

    def test_path_like_host_keys_are_rejected(self):
        for bad in ("", "..", "a/b", "a\\b", "c:x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                store.validate_host(bad)


class LayoutTests(unittest.TestCase):
    def test_host_paths_are_per_host(self):
        paths = store.host_paths("box", Path("s"), Path("r"))
        self.assertEqual(paths.db_path, Path("s/box/memories.db"))
        self.assertEqual(paths.export_path, Path("s/box/memories.json"))
        self.assertEqual(paths.rag_index_dir, Path("r/box"))

    def test_discover_hosts_requires_an_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b").mkdir()
            (root / "b" / "memories.json").write_text("[]", encoding="utf-8")
            (root / "a").mkdir()
            (root / "a" / "memories.json").write_text("[]", encoding="utf-8")
            (root / "empty").mkdir()
            self.assertEqual(store.discover_hosts(root), ["a", "b"])
            self.assertEqual(store.discover_hosts(root / "missing"), [])


class ExportFormatTests(unittest.TestCase):
    def test_prepare_export_keeps_durable_records_sorted_without_telemetry(self):
        records = [
            record("2", access_count=4, accessed_at="x", targeted_access_count=1),
            record("1", "procedural"),
            record("3", "working"),
        ]
        prepared = store.prepare_export(records)
        self.assertEqual([r["id"] for r in prepared], ["1", "2"])
        self.assertNotIn("access_count", prepared[1])
        self.assertNotIn("accessed_at", prepared[1])

    def test_written_export_is_canonical_lf_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h" / "memories.json"
            store.write_export(path, [{"id": "1", "title": "Zürich", "b": 1, "a": 2}])
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"]\n"))
            self.assertIn("Zürich", raw.decode("utf-8"))
            self.assertLess(raw.index(b'"a"'), raw.index(b'"b"'))
            self.assertEqual(store.read_export(path), json.loads(raw))

    def test_read_export_rejects_non_arrays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memories.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                store.read_export(path)
            self.assertEqual(store.read_export(Path(tmp) / "missing.json"), [])


if __name__ == "__main__":
    unittest.main()
