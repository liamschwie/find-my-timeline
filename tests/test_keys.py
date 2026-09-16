import tempfile
import unittest
from pathlib import Path
from unittest import mock

from find_my_timeline import keys


class FakeAccessory:
    def __init__(self, name):
        self.name = name
        self.identifier = f"id-{name}"

    def to_json(self, path):
        Path(path).write_text("{}")


class TestExportKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src_path = Path(self.tmp.name) / "Storage"
        self.src_path.mkdir()
        self.dst_path = Path(self.tmp.name) / "keys"

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_search_path_returns_empty(self):
        with mock.patch.object(keys, "find_search_path", return_value=None):
            self.assertEqual(keys.export_keys(dest_dir=self.dst_path), [])

    def test_exports_each_accessory(self):
        with mock.patch.object(
            keys,
            "list_accessories",
            return_value=[FakeAccessory("Backpack"), FakeAccessory("Keys")],
        ):
            written = keys.export_keys(self.src_path, self.dst_path)

        self.assertEqual(len(written), 2)
        for path in written:
            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".json")

    def test_sanitizes_unsafe_characters_in_name(self):
        with mock.patch.object(
            keys, "list_accessories", return_value=[FakeAccessory("My/AirTag: 1")]
        ):
            written = keys.export_keys(self.src_path, self.dst_path)

        self.assertEqual(len(written), 1)
        self.assertNotIn("/", written[0].name)
        self.assertNotIn(":", written[0].name)

    def test_falls_back_to_identifier_when_unnamed(self):
        unnamed = FakeAccessory("Backpack")
        unnamed.name = None

        with mock.patch.object(keys, "list_accessories", return_value=[unnamed]):
            written = keys.export_keys(self.src_path, self.dst_path)

        self.assertEqual(written[0].stem, "id-Backpack")

    def test_export_keys_sets_restrictive_permissions(self):
        with mock.patch.object(
            keys, "list_accessories", return_value=[FakeAccessory("Backpack")]
        ):
            written = keys.export_keys(self.src_path, self.dst_path)

        self.assertEqual(oct(written[0].stat().st_mode)[-3:], "600")
        self.assertEqual(oct(self.dst_path.stat().st_mode)[-3:], "700")


class TestFindSearchPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_none_when_no_records_anywhere(self):
        empty = self.root / "empty"
        (empty / "OwnedBeacons").mkdir(parents=True)
        self.assertIsNone(keys.find_search_path([self.root / "missing", empty]))

    def test_returns_first_path_holding_records(self):
        populated = self.root / "populated"
        (populated / "OwnedBeacons").mkdir(parents=True)
        (populated / "OwnedBeacons" / "A.record").write_bytes(b"x")

        found = keys.find_search_path([self.root / "missing", populated])
        self.assertEqual(found, populated)


class TestImportFrom(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dst_path = self.root / "keys"

    def tearDown(self):
        self.tmp.cleanup()

    def test_imports_json_files_from_directory(self):
        source = self.root / "exported"
        source.mkdir()
        (source / "a.json").write_text("{}")
        (source / "b.json").write_text("{}")
        (source / "notes.txt").write_text("ignored")

        with mock.patch.object(
            keys.FindMyAccessory,
            "from_json",
            side_effect=[FakeAccessory("Backpack"), FakeAccessory("Keys")],
        ):
            written = keys.import_from(source, self.dst_path)

        self.assertEqual([p.stem for p in written], ["Backpack", "Keys"])

    def test_imports_single_decrypted_plist(self):
        source = self.root / "tag.plist"
        source.write_bytes(b"plist")

        with mock.patch.object(
            keys.FindMyAccessory, "from_plist", return_value=FakeAccessory("Backpack")
        ):
            written = keys.import_from(source, self.dst_path)

        self.assertEqual(len(written), 1)

    def test_still_encrypted_record_raises_actionable_error(self):
        source = self.root / "tag.record"
        source.write_bytes(b"encrypted")

        with mock.patch.object(
            keys.FindMyAccessory, "from_plist", side_effect=TypeError("list indices")
        ):
            with self.assertRaises(ValueError) as ctx:
                keys.import_from(source, self.dst_path)

        self.assertIn("still encrypted", str(ctx.exception))


class TestLoadKeys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.keys_dir = Path(self.tmp.name) / "keys"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_keys_missing_directory(self):
        self.assertEqual(keys.load_keys(self.keys_dir), [])

    def test_load_keys_round_trip(self):
        with mock.patch.object(
            keys,
            "list_accessories",
            return_value=[FakeAccessory("Backpack"), FakeAccessory("Keys")],
        ):
            keys.export_keys(Path(self.tmp.name), self.keys_dir)

        with mock.patch.object(
            keys.FindMyAccessory,
            "from_json",
            side_effect=[FakeAccessory("Backpack"), FakeAccessory("Keys")],
        ):
            loaded = keys.load_keys(self.keys_dir)

        self.assertEqual([a.name for a in loaded], ["Backpack", "Keys"])


if __name__ == "__main__":
    unittest.main()
