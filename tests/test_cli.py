# tests/test_cli.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from find_my_timeline import cli


class TestStatsAndDevicesCommands(unittest.TestCase):
    def test_stats_no_database(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nope" / "locations.db"
            with mock.patch.dict(os.environ, {"DATABASE_PATH": str(db_path)}):
                result = runner.invoke(cli.main, ["stats"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No database found", result.output)

    def test_devices_no_database(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nope" / "locations.db"
            with mock.patch.dict(os.environ, {"DATABASE_PATH": str(db_path)}):
                result = runner.invoke(cli.main, ["devices"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No database found", result.output)

    def test_stats_with_data(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "locations.db"
            from find_my_timeline.database import LocationDatabase
            db = LocationDatabase(db_path)
            db.upsert_device("tag-1", "Backpack")

            with mock.patch.dict(os.environ, {"DATABASE_PATH": str(db_path)}):
                result = runner.invoke(cli.main, ["stats"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Backpack", result.output)


class TestImportKeysCommand(unittest.TestCase):
    def test_missing_owned_beacons_dir_exits_nonzero(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            with mock.patch.object(cli, "OWNED_BEACONS_DIR", missing):
                result = runner.invoke(cli.main, ["import-keys"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("No Find My accessory data found", result.output)

    def test_no_keys_found_reports_zero(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            with mock.patch.object(cli, "OWNED_BEACONS_DIR", source):
                result = runner.invoke(cli.main, ["import-keys"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No AirTags found", result.output)


if __name__ == "__main__":
    unittest.main()
