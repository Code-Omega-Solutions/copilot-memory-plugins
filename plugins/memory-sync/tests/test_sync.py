import io
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from memory_store_sync import store, sync
from memory_store_sync.config import StoreConfig
from memory_store_sync.workspace import StoreLocation


def record(memory_id, updated="2026-01-01", memory_type="semantic", **extra):
    base = {"id": memory_id, "type": memory_type, "title": f"t{memory_id}", "content": f"c{memory_id}", "updated_at": updated}
    base.update(extra)
    return base


class FakeCli:
    """Stands in for the upstream server CLI; the database is a list of records."""

    databases: dict = {}

    def __init__(self, location, db_path):
        self.db_path = db_path

    def export_all(self):
        return list(self.databases.get(self.db_path, []))

    def import_records(self, records):
        self.databases.setdefault(self.db_path, []).extend(records)
        Path(self.db_path).touch()
        return f"imported {len(records)}"


class SelectionTests(unittest.TestCase):
    def test_only_unknown_durable_records_are_selected_once(self):
        sources = {
            "b": [record("1"), record("2", memory_type="working"), record("3")],
            "a": [record("3"), record("4")],
        }
        selected = sync.select_new_records(sources, own_ids={"1"})
        self.assertEqual([r["id"] for r in selected], ["3", "4"])

    def test_conflicts_require_a_newer_different_remote_copy(self):
        own = [record("1", "2026-02-01"), record("2", "2026-02-01"), record("3", "2026-02-01")]
        sources = {
            "b": [
                record("1", "2026-03-01", content="changed"),
                record("2", "2026-01-01", content="older"),
                record("3", "2026-03-01"),
            ]
        }
        conflicts = sync.find_conflicts(own, sources)
        self.assertEqual([(c.memory_id, c.source_host) for c in conflicts], [("1", "b")])


class CommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.location = StoreLocation(root, StoreConfig(), root / "mem", root / "rag", root, True)
        FakeCli.databases = {}

    def tearDown(self):
        self._tmp.cleanup()

    def paths(self, host):
        return store.host_paths(host, self.location.store_root, self.location.rag_root)

    def test_import_seeds_an_empty_store_from_all_exports_including_its_own(self):
        store.write_export(self.paths("a").export_path, [record("1")])
        store.write_export(self.paths("b").export_path, [record("2"), record("3", memory_type="working")])
        out = io.StringIO()
        self.assertEqual(sync.command_import(self.location, "a", False, cli_factory=FakeCli, out=out), 0)
        imported = FakeCli.databases[self.paths("a").db_path]
        self.assertEqual(sorted(r["id"] for r in imported), ["1", "2"])

    def test_dry_run_does_not_write(self):
        store.write_export(self.paths("b").export_path, [record("2")])
        out = io.StringIO()
        sync.command_import(self.location, "a", True, cli_factory=FakeCli, out=out)
        self.assertEqual(FakeCli.databases, {})
        self.assertIn("would be imported", out.getvalue())

    def test_reviewed_exclusion_skips_only_selected_id_without_changing_sources(self):
        self.location = replace(
            self.location, config=StoreConfig(excluded_memory_ids={"old": "Removed documentation paths"})
        )
        source = self.paths("b").export_path
        store.write_export(source, [record("old", memory_type="documentation"), record("current")])
        before = source.read_bytes()
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                out = io.StringIO()
                self.assertEqual(sync.command_import(self.location, "a", dry_run, FakeCli, out), 0)
                self.assertIn("excluded old: Removed documentation paths", out.getvalue())
        self.assertEqual([r["id"] for r in FakeCli.databases[self.paths("a").db_path]], ["current"])
        self.assertEqual(source.read_bytes(), before)

    def test_exclusion_applies_to_status_and_conflicts_but_does_not_delete_local_record(self):
        self.location = replace(self.location, config=StoreConfig(excluded_memory_ids={"old": "Obsolete"}))
        db = self.paths("a").db_path
        db.parent.mkdir(parents=True)
        db.touch()
        original = record("old", "2026-01-01")
        FakeCli.databases[db] = [original]
        store.write_export(self.paths("b").export_path, [record("old", "2026-05-01", title="renamed")])
        for command in (
            lambda out: sync.command_status(self.location, "a", out),
            lambda out: sync.command_import(self.location, "a", False, FakeCli, out),
        ):
            out = io.StringIO()
            self.assertEqual(command(out), 0)
            self.assertIn("excluded old: Obsolete", out.getvalue())
            self.assertNotIn("changed on another host", out.getvalue())
            self.assertNotIn("1 not in own export", out.getvalue())
        self.assertEqual(FakeCli.databases[db], [original])

    def test_zero_exit_partial_import_is_a_failure_and_retry_selects_only_missing_id(self):
        class PartialCli(FakeCli):
            def import_records(self, records):
                super().import_records(records[:1])
                return "Imported 1/2 memories"

        store.write_export(self.paths("b").export_path, [record("1"), record("2")])
        out = io.StringIO()
        self.assertEqual(sync.command_import(self.location, "a", False, PartialCli, out), 1)
        self.assertIn("import verification failed for 1/2 records: 2", out.getvalue())
        self.assertEqual(sync.command_import(self.location, "a", False, FakeCli, io.StringIO()), 0)
        self.assertEqual([r["id"] for r in FakeCli.databases[self.paths("a").db_path]], ["1", "2"])

    def test_zero_exit_rejected_legacy_type_is_a_failure(self):
        class RejectingCli(FakeCli):
            def import_records(self, records):
                return "Imported 0/1 memories"

        store.write_export(self.paths("b").export_path, [record("legacy", memory_type="documentation")])
        out = io.StringIO()
        self.assertEqual(sync.command_import(self.location, "a", False, RejectingCli, out), 1)
        self.assertIn("import verification failed for 1/1 records: legacy", out.getvalue())

    def test_import_verifies_persisted_content_type_and_title_not_just_id(self):
        for field in ("title", "content", "type"):
            class MismatchingCli(FakeCli):
                def import_records(self, records):
                    return super().import_records([{**r, field: "unexpected"} for r in records])

            with self.subTest(field=field):
                FakeCli.databases = {}
                store.write_export(self.paths("b").export_path, [record("1")])
                out = io.StringIO()
                self.assertEqual(sync.command_import(self.location, "a", False, MismatchingCli, out), 1)
                self.assertIn("import verification failed", out.getvalue())

    def test_import_reports_conflicts_without_applying_them(self):
        db = self.paths("a").db_path
        db.parent.mkdir(parents=True)
        db.touch()
        FakeCli.databases[db] = [record("1", "2026-01-01")]
        store.write_export(self.paths("b").export_path, [record("1", "2026-05-01", title="renamed")])
        out = io.StringIO()
        sync.command_import(self.location, "a", False, cli_factory=FakeCli, out=out)
        self.assertEqual(FakeCli.databases[db], [record("1", "2026-01-01")])
        self.assertIn("changed on another host", out.getvalue())
        self.assertIn("'renamed'", out.getvalue())

    def test_export_writes_only_durable_records_and_is_stable(self):
        db = self.paths("a").db_path
        db.parent.mkdir(parents=True)
        sqlite3.connect(db).close()
        FakeCli.databases[db] = [record("2", access_count=3), record("1"), record("9", memory_type="working")]
        out = io.StringIO()
        self.assertEqual(sync.command_export(self.location, "a", cli_factory=FakeCli, out=out), 0)
        first = self.paths("a").export_path.read_bytes()
        sync.command_export(self.location, "a", cli_factory=FakeCli, out=out)
        self.assertEqual(self.paths("a").export_path.read_bytes(), first)
        exported = store.read_export(self.paths("a").export_path)
        self.assertEqual([r["id"] for r in exported], ["1", "2"])
        self.assertNotIn("access_count", exported[1])

    def test_export_without_database_fails(self):
        self.assertEqual(sync.command_export(self.location, "a", cli_factory=FakeCli, out=io.StringIO()), 1)

    def test_status_lists_other_hosts(self):
        store.write_export(self.paths("a").export_path, [record("1")])
        store.write_export(self.paths("b").export_path, [record("1"), record("2")])
        out = io.StringIO()
        sync.command_status(self.location, "a", out=out)
        self.assertIn("own export:", out.getvalue())
        self.assertIn("b  (2 records, 1 not in own export)", out.getvalue())


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_folds_wal_into_the_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "m.db"
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE t (x)")
            conn.execute("INSERT INTO t VALUES (1)")
            conn.commit()
            try:
                self.assertTrue(sync.checkpoint_wal(db))
            finally:
                conn.close()
            self.assertFalse(sync.checkpoint_wal(Path(tmp) / "missing.db"))


if __name__ == "__main__":
    unittest.main()
