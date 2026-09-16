import tempfile
import unittest
from pathlib import Path
from unittest import mock

from find_my_timeline import keys


class FakeAccessory:
    def __init__(self, name):
        self.name = name
        self.identifier = f"id-{name}"
        self.written_to = None

    def to_json(self, path):
        self.written_to = Path(path)
        Path(path).write_text("{}")


class TestExportKeys(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.TemporaryDirectory()
        self.dst = tempfile.TemporaryDirectory()
        self.src_path = Path(self.src.name)
        self.dst_path = Path(self.dst.name) / "keys"

    def tearDown(self):
        self.src.cleanup()
        self.dst.cleanup()

    def test_no_records_returns_empty(self):
        result = keys.export_keys(self.src_path, self.dst_path)
        self.assertEqual(result, [])

    def test_missing_source_dir_returns_empty(self):
        result = keys.export_keys(self.src_path / "nope", self.dst_path)
        self.assertEqual(result, [])

    def test_exports_each_record(self):
        (self.src_path / "A.record").write_bytes(b"fake plist")
        (self.src_path / "B.record").write_bytes(b"fake plist")

        with mock.patch.object(
            keys.FindMyAccessory,
            "from_plist",
            side_effect=[FakeAccessory("Backpack"), FakeAccessory("Keys")],
        ):
            written = keys.export_keys(self.src_path, self.dst_path)

        self.assertEqual(len(written), 2)
        for path in written:
            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".json")

    def test_sanitizes_unsafe_characters_in_name(self):
        (self.src_path / "A.record").write_bytes(b"fake plist")

        with mock.patch.object(
            keys.FindMyAccessory,
            "from_plist",
            return_value=FakeAccessory("My/AirTag: 1"),
        ):
            written = keys.export_keys(self.src_path, self.dst_path)

        self.assertEqual(len(written), 1)
        self.assertNotIn("/", written[0].name)
        self.assertNotIn(":", written[0].name)

    def test_export_keys_sets_0600_permission(self):
        (self.src_path / "A.record").write_bytes(b"fake plist")

        with mock.patch.object(
            keys.FindMyAccessory,
            "from_plist",
            return_value=FakeAccessory("Backpack"),
        ):
            written = keys.export_keys(self.src_path, self.dst_path)

        self.assertEqual(len(written), 1)
        perms = oct(written[0].stat().st_mode)[-3:]
        self.assertEqual(perms, "600")

    def test_load_keys_empty_directory(self):
        result = keys.load_keys(self.dst_path)
        self.assertEqual(result, [])

    def test_load_keys_round_trip(self):
        (self.src_path / "A.record").write_bytes(b"fake plist")
        (self.src_path / "B.record").write_bytes(b"fake plist")

        with mock.patch.object(
            keys.FindMyAccessory,
            "from_plist",
            side_effect=[FakeAccessory("Backpack"), FakeAccessory("Keys")],
        ):
            written = keys.export_keys(self.src_path, self.dst_path)

        with mock.patch.object(
            keys.FindMyAccessory,
            "from_json",
            side_effect=[FakeAccessory("Backpack"), FakeAccessory("Keys")],
        ):
            loaded = keys.load_keys(self.dst_path)

        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].name, "Backpack")
        self.assertEqual(loaded[1].name, "Keys")


if __name__ == "__main__":
    unittest.main()
