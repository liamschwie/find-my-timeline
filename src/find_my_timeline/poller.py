"""Location polling for tracked AirTags/accessories."""

import logging
import random
import signal
import time
from datetime import datetime
from typing import Callable

from .battery import decode_battery
from .database import LocationDatabase

logger = logging.getLogger(__name__)


class AccessoryPoller:
    """Polls accessory locations at random intervals and stores them."""

    def __init__(
        self,
        account,
        accessories: list,
        database: LocationDatabase,
        min_interval: int = 7,
        max_interval: int = 10,
    ):
        self.account = account
        self.accessories = accessories
        self.database = database
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._running = False
        self._on_poll_callbacks: list[Callable[[list[dict]], None]] = []

    def on_poll(self, callback: Callable[[list[dict]], None]) -> None:
        """Register a callback to be called after each poll."""
        self._on_poll_callbacks.append(callback)

    def _get_next_interval(self) -> float:
        """Get a random interval between min and max (in minutes), in seconds."""
        return random.uniform(self.min_interval, self.max_interval) * 60

    def poll_once(self) -> list[dict]:
        """Fetch and store the latest location for each tracked accessory."""
        try:
            locations = self.account.fetch_location(self.accessories)
        except Exception as e:
            logger.error(f"Failed to fetch locations: {e}")
            return []

        recorded = []

        for accessory in self.accessories:
            device_id = accessory.identifier
            name = accessory.name or device_id

            self.database.upsert_device(
                device_id=device_id,
                name=name,
                device_display_name=name,
                device_class="AirTag",
            )

            report = locations.get(accessory)
            if report is None:
                logger.warning(f"No location available for {name}")
                continue

            last_location = self.database.get_latest_location(device_id)
            if last_location and str(last_location.get("timestamp")) == str(report.timestamp):
                logger.debug(f"Skipping duplicate location for {name}")
                continue

            battery_status = decode_battery(report.status)

            location_id = self.database.record_location(
                device_id=device_id,
                latitude=report.latitude,
                longitude=report.longitude,
                timestamp=report.timestamp,
                horizontal_accuracy=report.horizontal_accuracy,
                confidence=report.confidence,
                battery_status=battery_status,
            )

            recorded_location = {
                "id": location_id,
                "device_id": device_id,
                "device_name": name,
                "latitude": report.latitude,
                "longitude": report.longitude,
                "timestamp": report.timestamp.isoformat(),
                "accuracy": report.horizontal_accuracy,
                "confidence": report.confidence,
                "battery_status": battery_status,
            }
            recorded.append(recorded_location)

            logger.info(
                f"Recorded location for {name}: "
                f"({report.latitude:.6f}, {report.longitude:.6f}) battery={battery_status}"
            )

        for callback in self._on_poll_callbacks:
            try:
                callback(recorded)
            except Exception as e:
                logger.error(f"Callback error: {e}")

        return recorded

    def start(self, setup_signals: bool = True) -> None:
        """Start the polling loop. Blocks until stopped.

        Args:
            setup_signals: Whether to set up SIGINT/SIGTERM handlers.
                Only works in the main thread; pass False when running
                this in a background thread.
        """
        self._running = True

        if setup_signals:
            try:
                def handle_signal(signum, frame):
                    logger.info(f"Received signal {signum}, stopping...")
                    self._running = False

                signal.signal(signal.SIGINT, handle_signal)
                signal.signal(signal.SIGTERM, handle_signal)
            except ValueError:
                pass  # Not in the main thread; caller handles shutdown.

        logger.info(
            f"Starting accessory poller (interval: {self.min_interval}-{self.max_interval} minutes)"
        )

        self.poll_once()

        while self._running:
            interval = self._get_next_interval()
            next_poll_time = datetime.fromtimestamp(
                datetime.now().timestamp() + interval
            ).strftime("%H:%M:%S")
            logger.info(f"Next poll in {interval / 60:.1f} minutes (at {next_poll_time})")

            sleep_end = time.time() + interval
            while self._running and time.time() < sleep_end:
                time.sleep(min(1, sleep_end - time.time()))

            if self._running:
                self.poll_once()

        logger.info("Poller stopped")

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
