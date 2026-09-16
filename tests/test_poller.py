# tests/test_poller.py
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from find_my_timeline.database import LocationDatabase
from find_my_timeline.poller import AccessoryPoller


@dataclass(frozen=True)
class FakeAccessory:
    identifier: str
    name: str


@dataclass
class FakeReport:
    latitude: float
    longitude: float
    horizontal_accuracy: float
    confidence: int
    status: int
    timestamp: datetime


class FakeAccount:
    def __init__(self, reports_by_accessory):
        self._reports = reports_by_accessory

    def fetch_location(self, accessories):
        return {a: self._reports.get(a) for a in accessories}


class TestAccessoryPoller(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = LocationDatabase(Path(self.tmpdir.name) / "test.db")
        self.accessory = FakeAccessory(identifier="tag-1", name="Backpack")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_poll_once_records_location(self):
        report = FakeReport(
            latitude=37.7749,
            longitude=-122.4194,
            horizontal_accuracy=5.0,
            confidence=3,
            status=0b00000000,  # Full battery
            timestamp=datetime.now(),
        )
        account = FakeAccount({self.accessory: report})
        poller = AccessoryPoller(account, [self.accessory], self.db)

        recorded = poller.poll_once()

        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["device_id"], "tag-1")
        self.assertEqual(recorded[0]["battery_status"], "Full")
        self.assertEqual(self.db.get_location_count(), 1)

    def test_poll_once_skips_accessory_with_no_report(self):
        account = FakeAccount({self.accessory: None})
        poller = AccessoryPoller(account, [self.accessory], self.db)

        recorded = poller.poll_once()

        self.assertEqual(recorded, [])
        self.assertEqual(self.db.get_location_count(), 0)
        # Device row is still created/updated even without a location.
        self.assertEqual(len(self.db.get_devices()), 1)

    def test_poll_once_skips_duplicate_timestamp(self):
        ts = datetime.now()
        report = FakeReport(1.0, 1.0, 5.0, 3, 0b00000000, ts)
        account = FakeAccount({self.accessory: report})
        poller = AccessoryPoller(account, [self.accessory], self.db)

        first = poller.poll_once()
        second = poller.poll_once()

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(self.db.get_location_count(), 1)

    def test_on_poll_callback_invoked(self):
        report = FakeReport(1.0, 1.0, 5.0, 3, 0b00000000, datetime.now())
        account = FakeAccount({self.accessory: report})
        poller = AccessoryPoller(account, [self.accessory], self.db)

        seen = []
        poller.on_poll(seen.append)
        poller.poll_once()

        self.assertEqual(len(seen), 1)
        self.assertEqual(len(seen[0]), 1)


if __name__ == "__main__":
    unittest.main()
