import io
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from memory_store_sync import store, sync
from memory_store_sync.config import StoreConfig
from memory_store_sync.workspace import StoreLocation


@unittest.skipUnless(os.environ.get("MEMORY_SYNC_LIVE_TEST") == "1", "Opt-in pinned Go server integration")
class LiveImportTests(unittest.TestCase):
    def test_partial_upstream_success_fails_then_reviewed_exclusion_completes_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            location = StoreLocation(root, StoreConfig(), root / "mem", root / "rag", root, True)
            source = store.host_paths("peer", location.store_root, location.rag_root).export_path
            store.write_export(source, [
                {"id": "current", "type": "semantic", "title": "Current", "content": "Current verified guidance"},
                {"id": "obsolete", "type": "documentation", "title": "Old", "content": "Removed file history"},
            ])
            before = source.read_bytes()
            out = io.StringIO()
            self.assertEqual(sync.command_import(location, "local", False, out=out), 1, out.getvalue())
            self.assertIn("Imported 1/2 memories", out.getvalue())
            self.assertIn("import verification failed for 1/2 records: obsolete", out.getvalue())
            location = replace(location, config=StoreConfig(excluded_memory_ids={"obsolete": "Removed paths"}))
            out = io.StringIO()
            self.assertEqual(sync.command_import(location, "local", False, out=out), 0, out.getvalue())
            self.assertIn("nothing to import", out.getvalue())
            self.assertEqual(sync.command_export(location, "local", out=out), 0, out.getvalue())
            exported = store.read_export(store.host_paths("local", location.store_root, location.rag_root).export_path)
            self.assertEqual([r["id"] for r in exported], ["current"])
            self.assertEqual(source.read_bytes(), before)
