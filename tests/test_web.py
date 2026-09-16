import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from find_my_timeline.database import LocationDatabase
from find_my_timeline.web import create_app


class TestWebApi(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = LocationDatabase(Path(self.tmpdir.name) / "test.db")
        self.db.upsert_device("tag-1", "Backpack", "AirTag", "AirTag")
        self.db.record_location(
            device_id="tag-1",
            latitude=37.7749,
            longitude=-122.4194,
            timestamp=datetime.now(),
            horizontal_accuracy=5.0,
            confidence=3,
            battery_status="Full",
        )
        app = create_app(self.db)
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_index_serves_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"<html", resp.data.lower())

    def test_api_devices(self):
        resp = self.client.get("/api/devices")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Backpack")

    def test_api_locations(self):
        resp = self.client.get("/api/locations")
        data = resp.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["battery_status"], "Full")

    def test_api_locations_filters_by_device(self):
        resp = self.client.get("/api/locations?device_id=nonexistent")
        self.assertEqual(resp.get_json(), [])

    def test_api_stats(self):
        resp = self.client.get("/api/stats")
        data = resp.get_json()
        self.assertEqual(data["total_devices"], 1)
        self.assertEqual(data["total_locations"], 1)


if __name__ == "__main__":
    unittest.main()
