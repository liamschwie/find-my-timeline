import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from find_my_timeline.database import LocationDatabase


class TestLocationDatabase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = LocationDatabase(Path(self.tmpdir.name) / "test.db")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_upsert_and_get_devices(self):
        self.db.upsert_device("tag-1", "Backpack", "AirTag", "AirTag")
        devices = self.db.get_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["name"], "Backpack")

    def test_upsert_device_updates_existing(self):
        self.db.upsert_device("tag-1", "Backpack")
        self.db.upsert_device("tag-1", "Backpack v2")
        devices = self.db.get_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["name"], "Backpack v2")

    def test_record_and_get_location(self):
        self.db.upsert_device("tag-1", "Backpack")
        now = datetime.now()
        loc_id = self.db.record_location(
            device_id="tag-1",
            latitude=37.7749,
            longitude=-122.4194,
            timestamp=now,
            horizontal_accuracy=5.0,
            confidence=3,
            battery_status="Full",
        )
        self.assertIsInstance(loc_id, int)

        locations = self.db.get_locations(device_id="tag-1")
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]["latitude"], 37.7749)
        self.assertEqual(locations[0]["battery_status"], "Full")
        self.assertEqual(locations[0]["confidence"], 3)

    def test_get_latest_location(self):
        self.db.upsert_device("tag-1", "Backpack")
        older = datetime.now() - timedelta(hours=1)
        newer = datetime.now()
        self.db.record_location("tag-1", 1.0, 1.0, older)
        self.db.record_location("tag-1", 2.0, 2.0, newer)

        latest = self.db.get_latest_location("tag-1")
        self.assertEqual(latest["latitude"], 2.0)

    def test_get_location_count(self):
        self.db.upsert_device("tag-1", "Backpack")
        self.db.record_location("tag-1", 1.0, 1.0, datetime.now())
        self.db.record_location("tag-1", 2.0, 2.0, datetime.now())

        self.assertEqual(self.db.get_location_count(), 2)
        self.assertEqual(self.db.get_location_count("tag-1"), 2)
        self.assertEqual(self.db.get_location_count("nonexistent"), 0)

    def test_get_locations_respects_limit(self):
        self.db.upsert_device("tag-1", "Backpack")
        for i in range(5):
            self.db.record_location("tag-1", float(i), float(i), datetime.now())

        self.assertEqual(len(self.db.get_locations(limit=2)), 2)

    def test_get_locations_respects_start_time(self):
        self.db.upsert_device("tag-1", "Backpack")
        now = datetime.now()
        old_time = now - timedelta(hours=2)
        mid_time = now - timedelta(hours=1)
        new_time = now

        self.db.record_location("tag-1", 1.0, 1.0, old_time)
        self.db.record_location("tag-1", 2.0, 2.0, mid_time)
        self.db.record_location("tag-1", 3.0, 3.0, new_time)

        # Query with start_time should exclude older locations
        locations = self.db.get_locations(device_id="tag-1", start_time=mid_time)
        self.assertEqual(len(locations), 2)
        self.assertIn(mid_time.timestamp(), [datetime.fromisoformat(loc["timestamp"].replace(" ", "T")).timestamp() for loc in locations])

    def test_get_locations_respects_end_time(self):
        self.db.upsert_device("tag-1", "Backpack")
        now = datetime.now()
        old_time = now - timedelta(hours=2)
        mid_time = now - timedelta(hours=1)
        new_time = now

        self.db.record_location("tag-1", 1.0, 1.0, old_time)
        self.db.record_location("tag-1", 2.0, 2.0, mid_time)
        self.db.record_location("tag-1", 3.0, 3.0, new_time)

        # Query with end_time should exclude newer locations
        locations = self.db.get_locations(device_id="tag-1", end_time=mid_time)
        self.assertEqual(len(locations), 2)
        self.assertIn(mid_time.timestamp(), [datetime.fromisoformat(loc["timestamp"].replace(" ", "T")).timestamp() for loc in locations])


if __name__ == "__main__":
    unittest.main()
