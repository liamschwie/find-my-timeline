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
    def test_no_records_on_this_mac_exits_nonzero(self):
        runner = CliRunner()
        with mock.patch.object(cli, "find_search_path", return_value=None):
            result = runner.invoke(cli.main, ["import-keys"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("No Find My accessory records found", result.output)

    def test_locked_keychain_key_explains_the_workaround(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cli, "find_search_path", return_value=Path(tmp)), \
                    mock.patch.object(cli, "export_keys", side_effect=ValueError("no key")):
                result = runner.invoke(cli.main, ["import-keys"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("import-keys --from", result.output)

    def test_no_keys_found_reports_zero(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cli, "find_search_path", return_value=Path(tmp)), \
                    mock.patch.object(cli, "export_keys", return_value=[]):
                result = runner.invoke(cli.main, ["import-keys"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No AirTags found", result.output)

    def test_import_from_writes_keys(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "exported"
            source.mkdir()
            written = [Path(tmp) / "keys" / "Backpack.json"]
            with mock.patch.object(cli, "import_from", return_value=written) as imported:
                result = runner.invoke(cli.main, ["import-keys", "--from", str(source)])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Backpack", result.output)
        self.assertEqual(imported.call_args.args[0], source)


if __name__ == "__main__":
    unittest.main()
