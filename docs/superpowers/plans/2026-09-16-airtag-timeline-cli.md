# AirTag Timeline CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal, pip-installable CLI (`find-my-timeline`) that records AirTag location + battery history to SQLite and serves it as a self-hosted Leaflet map, replacing upstream `find-my-timeline`'s pyicloud-based (AirTag-incapable) auth layer with the `findmy` library.

**Architecture:** Click CLI → SQLite (`database.py`) → Flask + Leaflet web UI (`web.py` + `templates/index.html`), with a `findmy`-library-backed auth/poll layer (`auth.py`, `keys.py`, `poller.py`) as the only fundamentally new piece versus upstream.

**Tech Stack:** Python 3.10+, `findmy` (AirTag report fetch/decrypt), `click` (CLI), `flask` (web/API), `python-dotenv` (env config), stdlib `sqlite3`, `pytest` (dev only), Leaflet.js (CDN, in the HTML template) for the map.

## Global Constraints

- Design doc: `docs/superpowers/specs/2026-09-15-airtag-timeline-cli-design.md` — every task below implements a section of it.
- Package layout: `src/find_my_timeline/` with `templates/` packaged *inside* it (not at repo root) — required so `pip install` (non-editable) ships the HTML file.
- Data files under `~/.find-my-timeline/`: `account.json` (Apple session), `keys/*.json` (accessory keys), `ani_libs.bin` (anisette libs cache). `account.json` and every file under `keys/` are written with `0600` permissions.
- Default DB path: `~/.find-my-timeline/locations.db` (override via `DATABASE_PATH` env var).
- No Docker/Unraid artifacts, no `pyicloud`, no `schedule` dependency (unused upstream).
- Every code task ships with a passing test before its commit step. Tests use stdlib `unittest` (matches the spec's "no framework, no fixtures" call) except where Flask's own `test_client()` or Click's `CliRunner` is the natural tool.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/find_my_timeline/__init__.py`
- Create: `.gitignore`
- Create: `README.md` (placeholder — full content in Task 9)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: an installable package named `find_my_timeline` under `src/`, with `findmy`, `click`, `flask`, `python-dotenv` as runtime dependencies and `pytest` as a dev dependency. All later tasks assume `pip install -e ".[dev]"` has been run in this directory.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "find-my-timeline"
version = "0.1.0"
description = "Track AirTag location and battery history from Apple Find My"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "findmy>=0.10.0",
    "click>=8.0.0",
    "flask>=3.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0"]

[project.scripts]
find-my-timeline = "find_my_timeline.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/find_my_timeline"]

[tool.hatch.build.targets.sdist]
include = ["/src"]
```

- [ ] **Step 2: Write `src/find_my_timeline/__init__.py`**

```python
"""AirTag Timeline: track AirTag location and battery history."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
*.egg-info/
build/
dist/
data/
*.db
.env
account.json
ani_libs.bin
```

- [ ] **Step 4: Write placeholder `README.md`**

```markdown
# AirTag Timeline

Track AirTag location and battery history. Full documentation lands in
Task 9 of `docs/superpowers/plans/2026-09-16-airtag-timeline-cli.md`.
```

- [ ] **Step 5: Create a venv and install the package**

Run:
```bash
cd ~/find-my-timeline
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```
Expected: install succeeds, pulling in `findmy`, `click`, `flask`, `python-dotenv`, `pytest`.

- [ ] **Step 6: Verify the package imports**

Run: `.venv/bin/python -c "import find_my_timeline; print(find_my_timeline.__version__)"`
Expected: prints `0.1.0`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/find_my_timeline/__init__.py .gitignore README.md
git commit -m "Scaffold find-my-timeline package"
```

---

### Task 2: Battery status decoding

**Files:**
- Create: `src/find_my_timeline/battery.py`
- Test: `tests/test_battery.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `decode_battery(status: int) -> str`, returning one of `"Full"`, `"Medium"`, `"Low"`, `"Very Low"`, `"Unknown"`. Used by Task 6 (`poller.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty) and `tests/test_battery.py`:

```python
import unittest

from find_my_timeline.battery import decode_battery


class TestDecodeBattery(unittest.TestCase):
    def test_full(self):
        self.assertEqual(decode_battery(0b00000000), "Full")

    def test_medium(self):
        self.assertEqual(decode_battery(0b01000000), "Medium")

    def test_low(self):
        self.assertEqual(decode_battery(0b10000000), "Low")

    def test_very_low(self):
        self.assertEqual(decode_battery(0b11000000), "Very Low")

    def test_ignores_lower_bits(self):
        # Lower 6 bits carry unrelated flags; only bits 6-7 encode battery.
        self.assertEqual(decode_battery(0b11111111), "Very Low")
        self.assertEqual(decode_battery(0b00111111), "Full")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_battery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'find_my_timeline.battery'`

- [ ] **Step 3: Write the implementation**

```python
"""Decode the AirTag battery-status byte into a human-readable level."""

_BATTERY_LEVELS = {0b00: "Full", 0b01: "Medium", 0b10: "Low", 0b11: "Very Low"}


def decode_battery(status: int) -> str:
    """Extract the battery level from a LocationReport status byte.

    The top two bits of the status byte encode battery level; the rest
    carry unrelated accessory flags.
    """
    battery_id = (status >> 6) & 0b11
    return _BATTERY_LEVELS.get(battery_id, "Unknown")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_battery.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/find_my_timeline/battery.py tests/__init__.py tests/test_battery.py
git commit -m "Add battery status byte decoder"
```

---

### Task 3: Location database

**Files:**
- Create: `src/find_my_timeline/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `class LocationDatabase` with:
  - `__init__(self, db_path: str | Path)`
  - `upsert_device(self, device_id: str, name: str, device_display_name: str | None = None, device_class: str | None = None) -> None`
  - `record_location(self, device_id: str, latitude: float, longitude: float, timestamp: datetime, horizontal_accuracy: float | None = None, confidence: int | None = None, battery_status: str | None = None) -> int`
  - `get_devices(self) -> list[dict]`
  - `get_locations(self, device_id: str | None = None, start_time: datetime | None = None, end_time: datetime | None = None, limit: int | None = None) -> list[dict]`
  - `get_latest_location(self, device_id: str) -> dict | None`
  - `get_location_count(self, device_id: str | None = None) -> int`

  Used by Task 6 (`poller.py`) and Task 7 (`web.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_database.py
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'find_my_timeline.database'`

- [ ] **Step 3: Write the implementation**

```python
# src/find_my_timeline/database.py
"""SQLite database for storing AirTag location history."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


class LocationDatabase:
    """Manages SQLite database for accessory location history."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    device_display_name TEXT,
                    device_class TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    horizontal_accuracy REAL,
                    confidence INTEGER,
                    battery_status TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices(id)
                );

                CREATE INDEX IF NOT EXISTS idx_locations_device_id
                    ON locations(device_id);
                CREATE INDEX IF NOT EXISTS idx_locations_timestamp
                    ON locations(timestamp);
                CREATE INDEX IF NOT EXISTS idx_locations_device_timestamp
                    ON locations(device_id, timestamp);
            """)

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_device(
        self,
        device_id: str,
        name: str,
        device_display_name: str | None = None,
        device_class: str | None = None,
    ) -> None:
        """Insert or update a device."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO devices (id, name, device_display_name, device_class, last_seen)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    device_display_name = excluded.device_display_name,
                    device_class = excluded.device_class,
                    last_seen = CURRENT_TIMESTAMP
                """,
                (device_id, name, device_display_name, device_class),
            )

    def record_location(
        self,
        device_id: str,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        horizontal_accuracy: float | None = None,
        confidence: int | None = None,
        battery_status: str | None = None,
    ) -> int:
        """Record a location point for a device. Returns the location ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO locations
                    (device_id, latitude, longitude, horizontal_accuracy,
                     confidence, battery_status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    latitude,
                    longitude,
                    horizontal_accuracy,
                    confidence,
                    battery_status,
                    timestamp,
                ),
            )
            return cursor.lastrowid

    def get_devices(self) -> list[dict]:
        """Get all known devices."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM devices ORDER BY last_seen DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_locations(
        self,
        device_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Get location history with optional filters."""
        query = "SELECT * FROM locations WHERE 1=1"
        params: list = []

        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_latest_location(self, device_id: str) -> dict | None:
        """Get the most recent location for a device."""
        locations = self.get_locations(device_id=device_id, limit=1)
        return locations[0] if locations else None

    def get_location_count(self, device_id: str | None = None) -> int:
        """Get total number of recorded locations."""
        query = "SELECT COUNT(*) FROM locations"
        params: list = []

        if device_id:
            query += " WHERE device_id = ?"
            params.append(device_id)

        with self._get_connection() as conn:
            return conn.execute(query, params).fetchone()[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_database.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/find_my_timeline/database.py tests/test_database.py
git commit -m "Add SQLite location database"
```

---

### Task 4: Accessory key export

**Files:**
- Create: `src/find_my_timeline/keys.py`
- Test: `tests/test_keys.py`

**Interfaces:**
- Consumes: `findmy.FindMyAccessory` (from the `findmy` PyPI package — `from_plist(path) -> FindMyAccessory`, `.to_json(path)`, `.name`, `.identifier`; `from_json(path) -> FindMyAccessory`).
- Produces:
  - `OWNED_BEACONS_DIR: Path` — `~/Library/Group Containers/group.com.apple.icloud.searchpartyuseragent/Library/Storage/OwnedBeacons`
  - `KEYS_DIR: Path` — `~/.find-my-timeline/keys`
  - `export_keys(source_dir: Path = OWNED_BEACONS_DIR, dest_dir: Path = KEYS_DIR) -> list[Path]`
  - `load_keys(keys_dir: Path = KEYS_DIR) -> list[FindMyAccessory]`

  Used by Task 8 (`cli.py`'s `import-keys` command and poller setup).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_keys.py
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_keys.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'find_my_timeline.keys'`

- [ ] **Step 3: Write the implementation**

```python
# src/find_my_timeline/keys.py
"""Export AirTag/accessory private keys from this Mac's local Find My cache."""

from pathlib import Path

from findmy import FindMyAccessory

OWNED_BEACONS_DIR = (
    Path.home()
    / "Library/Group Containers/group.com.apple.icloud.searchpartyuseragent"
    / "Library/Storage/OwnedBeacons"
)
KEYS_DIR = Path.home() / ".find-my-timeline" / "keys"


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def export_keys(
    source_dir: Path = OWNED_BEACONS_DIR,
    dest_dir: Path = KEYS_DIR,
) -> list[Path]:
    """Convert every OwnedBeacons .record file into a portable JSON key file.

    Returns the list of JSON paths written.
    """
    if not source_dir.exists():
        return []

    dest_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for record_path in sorted(source_dir.glob("*.record")):
        accessory = FindMyAccessory.from_plist(record_path)
        name = accessory.name or accessory.identifier or record_path.stem
        dest_path = dest_dir / f"{_safe_filename(name)}.json"
        accessory.to_json(dest_path)
        dest_path.chmod(0o600)
        written.append(dest_path)

    return written


def load_keys(keys_dir: Path = KEYS_DIR) -> list[FindMyAccessory]:
    """Load all previously exported accessory keys."""
    if not keys_dir.exists():
        return []
    return [FindMyAccessory.from_json(p) for p in sorted(keys_dir.glob("*.json"))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_keys.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/find_my_timeline/keys.py tests/test_keys.py
git commit -m "Add accessory key export from local Find My cache"
```

---

### Task 5: Apple account authentication

**Files:**
- Create: `src/find_my_timeline/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `findmy.AppleAccount`, `findmy.LocalAnisetteProvider`, `findmy.LoginState`, `findmy.SmsSecondFactorMethod`, `findmy.TrustedDeviceSecondFactorMethod` (all top-level exports of the `findmy` package).
- Produces:
  - `class AuthenticationError(Exception)`
  - `STORE_DIR: Path`, `ACCOUNT_PATH: Path`, `ANISETTE_LIBS_PATH: Path`
  - `login(username: str, password: str) -> AppleAccount` — runs the interactive login (prompting for a 2FA method/code on stdin if required), persists the session, returns the account.
  - `load_session() -> AppleAccount` — restores a saved session; raises `AuthenticationError` if none exists.

  Used by Task 8 (`cli.py`'s `auth` command and poller setup).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth.py
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from find_my_timeline import auth
from find_my_timeline.auth import AuthenticationError


class FakeAccount:
    def __init__(self, login_state="OK", methods=None):
        self._login_state = login_state
        self._methods = methods or []
        self.saved_to = None

    def login(self, username, password):
        return self._login_state

    def get_2fa_methods(self):
        return self._methods

    def to_json(self, path):
        self.saved_to = Path(path)
        Path(path).write_text("{}")


class FakeMethod:
    def __init__(self, code="123456"):
        self.requested = False
        self.submitted_code = None
        self._code = code

    def request(self):
        self.requested = True

    def submit(self, code):
        self.submitted_code = code


class TestLoadSession(unittest.TestCase):
    def test_raises_when_no_session_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "ACCOUNT_PATH", Path(tmp) / "account.json"):
                with self.assertRaises(AuthenticationError):
                    auth.load_session()


class TestLogin(unittest.TestCase):
    def test_login_without_2fa_saves_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_path = Path(tmp) / "account.json"
            fake_account = FakeAccount(login_state=auth.LoginState.LOGGED_IN)

            with (
                mock.patch.object(auth, "ACCOUNT_PATH", account_path),
                mock.patch.object(auth, "STORE_DIR", Path(tmp)),
                mock.patch.object(auth, "LocalAnisetteProvider", return_value=mock.Mock()),
                mock.patch.object(auth, "AppleAccount", return_value=fake_account),
            ):
                result = auth.login("user@example.com", "hunter2")

            self.assertIs(result, fake_account)
            self.assertTrue(account_path.exists())

    def test_login_with_2fa_prompts_and_submits_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_path = Path(tmp) / "account.json"
            method = FakeMethod()
            fake_account = FakeAccount(
                login_state=auth.LoginState.REQUIRE_2FA, methods=[method]
            )

            with (
                mock.patch.object(auth, "ACCOUNT_PATH", account_path),
                mock.patch.object(auth, "STORE_DIR", Path(tmp)),
                mock.patch.object(auth, "LocalAnisetteProvider", return_value=mock.Mock()),
                mock.patch.object(auth, "AppleAccount", return_value=fake_account),
                mock.patch("builtins.input", side_effect=["0", "123456"]),
            ):
                auth.login("user@example.com", "hunter2")

            self.assertTrue(method.requested)
            self.assertEqual(method.submitted_code, "123456")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'find_my_timeline.auth'`

- [ ] **Step 3: Write the implementation**

```python
# src/find_my_timeline/auth.py
"""Apple account authentication via the findmy library."""

from pathlib import Path

from findmy import (
    AppleAccount,
    LocalAnisetteProvider,
    LoginState,
    SmsSecondFactorMethod,
    TrustedDeviceSecondFactorMethod,
)


class AuthenticationError(Exception):
    """Raised when authentication fails or no session is available."""


STORE_DIR = Path.home() / ".find-my-timeline"
ACCOUNT_PATH = STORE_DIR / "account.json"
ANISETTE_LIBS_PATH = STORE_DIR / "ani_libs.bin"


def _handle_2fa(account: AppleAccount) -> None:
    """Prompt for and submit a 2FA code on stdin."""
    methods = account.get_2fa_methods()

    print("Two-factor authentication required. Available methods:")
    for index, method in enumerate(methods):
        if isinstance(method, TrustedDeviceSecondFactorMethod):
            print(f"  {index}: Trusted Device")
        elif isinstance(method, SmsSecondFactorMethod):
            print(f"  {index}: SMS ({method.phone_number})")
        else:
            print(f"  {index}: {type(method).__name__}")

    choice = int(input("Select method: ").strip())
    method = methods[choice]
    method.request()

    code = input("Enter the verification code: ").strip()
    method.submit(code)


def login(username: str, password: str) -> AppleAccount:
    """Authenticate with Apple and persist the session. Returns the logged-in account."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    anisette = LocalAnisetteProvider(libs_path=str(ANISETTE_LIBS_PATH))
    account = AppleAccount(anisette)

    state = account.login(username, password)
    if state == LoginState.REQUIRE_2FA:
        _handle_2fa(account)

    ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    account.to_json(str(ACCOUNT_PATH))
    ACCOUNT_PATH.chmod(0o600)

    return account


def load_session() -> AppleAccount:
    """Restore a previously saved session.

    Raises AuthenticationError if no session has been saved yet.
    """
    if not ACCOUNT_PATH.exists():
        raise AuthenticationError(
            "No saved session found. Run 'find-my-timeline auth' first."
        )

    return AppleAccount.from_json(
        str(ACCOUNT_PATH), anisette_libs_path=str(ANISETTE_LIBS_PATH)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/find_my_timeline/auth.py tests/test_auth.py
git commit -m "Add Apple account authentication via findmy"
```

---

### Task 6: Accessory location poller

**Files:**
- Create: `src/find_my_timeline/poller.py`
- Test: `tests/test_poller.py`

**Interfaces:**
- Consumes: `LocationDatabase` (Task 3), `decode_battery` (Task 2), an `AppleAccount`-shaped object with `.fetch_location(accessories) -> dict[accessory, report_or_None]` (Task 5's return type), and `FindMyAccessory`-shaped objects with `.identifier`, `.name` (Task 4).
- Produces: `class AccessoryPoller` with:
  - `__init__(self, account, accessories: list, database: LocationDatabase, min_interval: int = 7, max_interval: int = 10)`
  - `self.database` — the `LocationDatabase` instance, exposed so `cli.py`'s `start` command can share it with the web app.
  - `on_poll(self, callback: Callable[[list[dict]], None]) -> None`
  - `poll_once(self) -> list[dict]`
  - `start(self, setup_signals: bool = True) -> None`
  - `stop(self) -> None`

  Used by Task 8 (`cli.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_poller.py
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from find_my_timeline.database import LocationDatabase
from find_my_timeline.poller import AccessoryPoller


@dataclass
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_poller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'find_my_timeline.poller'`

- [ ] **Step 3: Write the implementation**

```python
# src/find_my_timeline/poller.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_poller.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/find_my_timeline/poller.py tests/test_poller.py
git commit -m "Add accessory location poller"
```

---

### Task 7: Web UI (Flask API + Leaflet map)

**Files:**
- Create: `src/find_my_timeline/web.py`
- Create: `src/find_my_timeline/templates/index.html`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `LocationDatabase` (Task 3).
- Produces: `create_app(database: LocationDatabase) -> Flask`, exposing `GET /`, `GET /api/devices`, `GET /api/locations`, `GET /api/locations/latest`, `GET /api/stats`.

  Used by Task 8 (`cli.py`'s `web` and `start` commands).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'find_my_timeline.web'`

- [ ] **Step 3: Write `src/find_my_timeline/web.py`**

```python
"""Flask web application for viewing AirTag location history."""

from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request

from .database import LocationDatabase


def create_app(database: LocationDatabase) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/devices")
    def api_devices():
        return jsonify(database.get_devices())

    @app.route("/api/locations")
    def api_locations():
        device_id = request.args.get("device_id")
        hours = request.args.get("hours", type=int)
        start = request.args.get("start")
        end = request.args.get("end")
        limit = request.args.get("limit", type=int, default=1000)

        start_time = None
        end_time = None

        if hours:
            start_time = datetime.now() - timedelta(hours=hours)
        elif start:
            start_time = datetime.fromisoformat(start)

        if end:
            end_time = datetime.fromisoformat(end)

        locations = database.get_locations(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        return jsonify(locations)

    @app.route("/api/locations/latest")
    def api_latest_locations():
        devices = database.get_devices()
        latest = []
        for device in devices:
            location = database.get_latest_location(device["id"])
            if location:
                location["device_name"] = device["name"]
                location["device_display_name"] = device["device_display_name"]
                latest.append(location)
        return jsonify(latest)

    @app.route("/api/stats")
    def api_stats():
        devices = database.get_devices()
        total_locations = database.get_location_count()

        device_stats = []
        for device in devices:
            count = database.get_location_count(device["id"])
            latest = database.get_latest_location(device["id"])
            device_stats.append({
                "id": device["id"],
                "name": device["name"],
                "location_count": count,
                "last_seen": device["last_seen"],
                "latest_location": latest,
            })

        return jsonify({
            "total_devices": len(devices),
            "total_locations": total_locations,
            "devices": device_stats,
        })

    return app
```

- [ ] **Step 4: Write `src/find_my_timeline/templates/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AirTag Timeline</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            height: 100vh;
        }

        #sidebar {
            width: 320px;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        h1 {
            font-size: 1.4rem;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        h1::before {
            content: "🏷️";
        }

        .section {
            background: #16213e;
            border-radius: 8px;
            padding: 15px;
        }

        .section h2 {
            font-size: 0.9rem;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }

        .device {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px;
            background: #1a1a2e;
            border-radius: 6px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }

        .device:hover {
            background: #0f3460;
        }

        .device.active {
            background: #0f3460;
            border-left: 3px solid #00d9ff;
        }

        .device-icon {
            font-size: 1.5rem;
        }

        .device-info {
            flex: 1;
        }

        .device-name {
            font-weight: 500;
            margin-bottom: 2px;
        }

        .device-meta {
            font-size: 0.8rem;
            color: #888;
        }

        .battery {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 0.8rem;
        }

        .controls {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        label {
            font-size: 0.85rem;
            color: #aaa;
        }

        select, input {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #333;
            border-radius: 6px;
            background: #1a1a2e;
            color: #fff;
            font-size: 0.9rem;
        }

        button {
            padding: 10px 16px;
            border: none;
            border-radius: 6px;
            background: #00d9ff;
            color: #000;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }

        button:hover {
            background: #00b8d9;
        }

        .stats {
            font-size: 0.85rem;
            color: #888;
        }

        .stats span {
            color: #00d9ff;
            font-weight: 500;
        }

        #map {
            flex: 1;
            height: 100%;
        }

        .leaflet-popup-content-wrapper {
            background: #1a1a2e;
            color: #fff;
            border-radius: 8px;
        }

        .leaflet-popup-tip {
            background: #1a1a2e;
        }

        .popup-content {
            padding: 5px;
        }

        .popup-content h3 {
            margin-bottom: 8px;
            font-size: 1rem;
        }

        .popup-content p {
            margin: 4px 0;
            font-size: 0.85rem;
            color: #aaa;
        }

        .timeline-marker {
            background: #00d9ff;
            border: 2px solid #fff;
            border-radius: 50%;
        }

        .current-marker {
            background: #00ff88;
            border: 3px solid #fff;
            border-radius: 50%;
            box-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
        }

        #timeline-panel {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 350px;
            max-height: calc(100vh - 40px);
            background: #1a1a2e;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
            display: none;
            flex-direction: column;
            z-index: 1000;
            overflow: hidden;
        }

        #timeline-panel.visible {
            display: flex;
        }

        .timeline-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            border-bottom: 1px solid #333;
        }

        .timeline-header h2 {
            font-size: 1rem;
            color: #fff;
            margin: 0;
        }

        #timeline-close {
            background: transparent;
            border: none;
            color: #888;
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0 5px;
            line-height: 1;
        }

        #timeline-close:hover {
            color: #fff;
        }

        .timeline-summary {
            padding: 12px 20px;
            background: #16213e;
            font-size: 0.85rem;
            color: #aaa;
            border-bottom: 1px solid #333;
        }

        .timeline-summary span {
            color: #00d9ff;
            font-weight: 500;
        }

        .timeline-list {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
        }

        .timeline-item {
            display: flex;
            gap: 12px;
            padding: 12px;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s;
            margin-bottom: 4px;
        }

        .timeline-item:hover {
            background: #16213e;
        }

        .timeline-item.active {
            background: #0f3460;
            border-left: 3px solid #00d9ff;
        }

        .timeline-item.latest {
            border-left: 3px solid #00ff88;
        }

        .timeline-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #00d9ff;
            margin-top: 4px;
            flex-shrink: 0;
        }

        .timeline-item.latest .timeline-dot {
            background: #00ff88;
            box-shadow: 0 0 8px rgba(0, 255, 136, 0.5);
        }

        .timeline-content {
            flex: 1;
            min-width: 0;
        }

        .timeline-time {
            font-size: 0.9rem;
            color: #fff;
            margin-bottom: 4px;
        }

        .timeline-details {
            font-size: 0.8rem;
            color: #888;
        }

        .timeline-details span {
            margin-right: 10px;
        }

        .timeline-battery {
            font-size: 0.8rem;
            color: #888;
            white-space: nowrap;
        }
    </style>
</head>
<body>
    <div id="sidebar">
        <h1>AirTag Timeline</h1>

        <div class="section">
            <h2>Devices</h2>
            <div id="devices-list">
                <p style="color: #666; font-size: 0.9rem;">Loading devices...</p>
            </div>
        </div>

        <div class="section">
            <h2>Time Range</h2>
            <div class="controls">
                <div>
                    <label for="time-range">Quick Select</label>
                    <select id="time-range">
                        <option value="1">Last 1 hour</option>
                        <option value="6">Last 6 hours</option>
                        <option value="24" selected>Last 24 hours</option>
                        <option value="168">Last 7 days</option>
                        <option value="720">Last 30 days</option>
                        <option value="0">All time</option>
                    </select>
                </div>
                <button id="refresh-btn">Refresh Map</button>
            </div>
        </div>

        <div class="section">
            <h2>Statistics</h2>
            <div id="stats" class="stats">
                Loading...
            </div>
        </div>
    </div>

    <div id="map"></div>

    <div id="timeline-panel">
        <div class="timeline-header">
            <h2><span id="timeline-device-name">Device Timeline</span></h2>
            <button id="timeline-close">&times;</button>
        </div>
        <div class="timeline-summary" id="timeline-summary"></div>
        <div class="timeline-list" id="timeline-list"></div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const map = L.map('map').setView([37.7749, -122.4194], 12);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        let markers = [];
        let markersById = {};
        let polylines = [];
        let selectedDevice = null;
        let selectedLocationId = null;
        let currentLocations = [];

        const deviceIcons = {
            'default': '🏷️'
        };

        function getDeviceIcon() {
            return deviceIcons.default;
        }

        function formatDate(dateStr) {
            const date = new Date(dateStr);
            return date.toLocaleString();
        }

        function formatBattery(status) {
            if (!status) return '';
            const icons = { 'Full': '🔋', 'Medium': '🔋', 'Low': '🪫', 'Very Low': '🔴' };
            const icon = icons[status] || '🔋';
            return `${icon} ${status}`;
        }

        async function loadDevices() {
            try {
                const response = await fetch('/api/devices');
                const devices = await response.json();

                const container = document.getElementById('devices-list');

                if (devices.length === 0) {
                    container.innerHTML = '<p style="color: #666;">No devices found. Start the poller to begin tracking.</p>';
                    return;
                }

                container.innerHTML = devices.map(device => `
                    <div class="device ${selectedDevice === device.id ? 'active' : ''}"
                         data-id="${device.id}">
                        <span class="device-icon">${getDeviceIcon()}</span>
                        <div class="device-info">
                            <div class="device-name">${device.name}</div>
                            <div class="device-meta">${device.device_display_name || ''}</div>
                        </div>
                    </div>
                `).join('');

                container.querySelectorAll('.device').forEach(el => {
                    el.addEventListener('click', () => {
                        const id = el.dataset.id;
                        if (selectedDevice === id) {
                            selectedDevice = null;
                            hideTimelinePanel();
                        } else {
                            selectedDevice = id;
                        }
                        selectedLocationId = null;
                        loadDevices();
                        loadLocations();
                        loadStats();
                    });
                });
            } catch (error) {
                console.error('Failed to load devices:', error);
            }
        }

        async function loadLocations() {
            markers.forEach(m => map.removeLayer(m));
            polylines.forEach(p => map.removeLayer(p));
            markers = [];
            markersById = {};
            polylines = [];
            currentLocations = [];

            const hours = document.getElementById('time-range').value;
            let url = '/api/locations?limit=5000';

            if (hours !== '0') {
                url += `&hours=${hours}`;
            }

            if (selectedDevice) {
                url += `&device_id=${encodeURIComponent(selectedDevice)}`;
            }

            try {
                const response = await fetch(url);
                const locations = await response.json();

                if (locations.length === 0) {
                    hideTimelinePanel();
                    return;
                }

                const byDevice = {};
                locations.forEach(loc => {
                    if (!byDevice[loc.device_id]) {
                        byDevice[loc.device_id] = [];
                    }
                    byDevice[loc.device_id].push(loc);
                });

                const colors = ['#00d9ff', '#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3'];
                let colorIndex = 0;
                const bounds = [];

                for (const [, deviceLocations] of Object.entries(byDevice)) {
                    const color = colors[colorIndex % colors.length];
                    colorIndex++;

                    deviceLocations.sort((a, b) =>
                        new Date(a.timestamp) - new Date(b.timestamp)
                    );

                    const path = deviceLocations.map(loc => [loc.latitude, loc.longitude]);
                    if (path.length > 1) {
                        const polyline = L.polyline(path, {
                            color: color,
                            weight: 3,
                            opacity: 0.7
                        }).addTo(map);
                        polylines.push(polyline);
                    }

                    deviceLocations.forEach((loc, index) => {
                        const isLatest = index === deviceLocations.length - 1;
                        const marker = L.circleMarker([loc.latitude, loc.longitude], {
                            radius: isLatest ? 10 : 6,
                            fillColor: isLatest ? '#00ff88' : color,
                            color: '#fff',
                            weight: isLatest ? 3 : 2,
                            opacity: 1,
                            fillOpacity: 0.8
                        }).addTo(map);

                        marker.bindPopup(`
                            <div class="popup-content">
                                <h3>${getDeviceIcon()} ${loc.device_id}</h3>
                                <p><strong>Time:</strong> ${formatDate(loc.timestamp)}</p>
                                <p><strong>Confidence:</strong> ${loc.confidence != null ? loc.confidence + '/3' : 'Unknown'}</p>
                                <p><strong>Accuracy:</strong> ${loc.horizontal_accuracy ? loc.horizontal_accuracy.toFixed(0) + 'm' : 'Unknown'}</p>
                                ${loc.battery_status ? `<p><strong>Battery:</strong> ${formatBattery(loc.battery_status)}</p>` : ''}
                            </div>
                        `);

                        markers.push(marker);
                        markersById[loc.id] = marker;
                        bounds.push([loc.latitude, loc.longitude]);
                    });

                    if (selectedDevice) {
                        currentLocations = deviceLocations;
                    }
                }

                if (bounds.length > 0) {
                    map.fitBounds(bounds, { padding: [50, 50] });
                }

                if (selectedDevice && currentLocations.length > 0) {
                    updateTimelinePanel();
                } else {
                    hideTimelinePanel();
                }

            } catch (error) {
                console.error('Failed to load locations:', error);
            }
        }

        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();

                document.getElementById('stats').innerHTML = `
                    <p><span>${stats.total_devices}</span> devices tracked</p>
                    <p><span>${stats.total_locations.toLocaleString()}</span> locations recorded</p>
                `;

            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }

        function updateTimelinePanel() {
            const panel = document.getElementById('timeline-panel');
            const deviceName = document.getElementById('timeline-device-name');
            const summary = document.getElementById('timeline-summary');
            const list = document.getElementById('timeline-list');

            const sortedLocations = [...currentLocations].reverse();

            deviceName.textContent = `${getDeviceIcon()} Timeline`;

            summary.innerHTML = `<span>${sortedLocations.length}</span> data points in selected time range`;

            list.innerHTML = sortedLocations.map((loc, index) => {
                const isLatest = index === 0;
                const isActive = selectedLocationId === loc.id;
                const date = new Date(loc.timestamp);
                const timeStr = date.toLocaleTimeString();
                const dateStr = date.toLocaleDateString();

                let accuracyStr = '';
                if (loc.horizontal_accuracy) {
                    accuracyStr = loc.horizontal_accuracy.toFixed(0) + 'm';
                }

                const confidenceStr = loc.confidence != null ? `Confidence ${loc.confidence}/3` : '';

                return `
                    <div class="timeline-item ${isLatest ? 'latest' : ''} ${isActive ? 'active' : ''}"
                         data-id="${loc.id}"
                         data-lat="${loc.latitude}"
                         data-lng="${loc.longitude}">
                        <div class="timeline-dot"></div>
                        <div class="timeline-content">
                            <div class="timeline-time">${timeStr}</div>
                            <div class="timeline-details">
                                <span>${dateStr}</span>
                                <span>${confidenceStr}</span>
                                <span>${accuracyStr}</span>
                            </div>
                        </div>
                        ${loc.battery_status ? `<div class="timeline-battery">${formatBattery(loc.battery_status)}</div>` : ''}
                    </div>
                `;
            }).join('');

            list.querySelectorAll('.timeline-item').forEach(item => {
                item.addEventListener('click', () => {
                    const id = parseInt(item.dataset.id);
                    const lat = parseFloat(item.dataset.lat);
                    const lng = parseFloat(item.dataset.lng);

                    selectedLocationId = id;
                    list.querySelectorAll('.timeline-item').forEach(i => i.classList.remove('active'));
                    item.classList.add('active');

                    map.setView([lat, lng], 16);
                    if (markersById[id]) {
                        markersById[id].openPopup();
                    }
                });
            });

            panel.classList.add('visible');
        }

        function hideTimelinePanel() {
            document.getElementById('timeline-panel').classList.remove('visible');
        }

        document.getElementById('refresh-btn').addEventListener('click', () => {
            loadDevices();
            loadLocations();
            loadStats();
        });

        document.getElementById('time-range').addEventListener('change', loadLocations);

        document.getElementById('timeline-close').addEventListener('click', () => {
            selectedDevice = null;
            selectedLocationId = null;
            hideTimelinePanel();
            loadDevices();
            loadLocations();
        });

        loadDevices();
        loadLocations();
        loadStats();

        setInterval(() => {
            loadDevices();
            loadLocations();
            loadStats();
        }, 5 * 60 * 1000);
    </script>
</body>
</html>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/find_my_timeline/web.py src/find_my_timeline/templates/index.html tests/test_web.py
git commit -m "Add Flask API and Leaflet map UI"
```

---

### Task 8: CLI wiring

**Files:**
- Create: `src/find_my_timeline/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2–7 (`decode_battery` indirectly via `poller`, `LocationDatabase`, `export_keys`/`load_keys`/`KEYS_DIR`/`OWNED_BEACONS_DIR`, `login`/`load_session`/`AuthenticationError`, `AccessoryPoller`, `create_app`).
- Produces: `main` — the Click group referenced by `pyproject.toml`'s `find-my-timeline = "find_my_timeline.cli:main"` entry point. Commands: `import-keys`, `auth`, `poll`, `web`, `start`, `stats`, `devices`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'find_my_timeline.cli'`

- [ ] **Step 3: Write the implementation**

```python
# src/find_my_timeline/cli.py
"""Command-line interface for AirTag Timeline."""

import logging
import os
import sys
import webbrowser
from pathlib import Path
from threading import Thread

import click
from dotenv import load_dotenv

from .auth import AuthenticationError, login, load_session
from .database import LocationDatabase
from .keys import KEYS_DIR, OWNED_BEACONS_DIR, export_keys, load_keys
from .poller import AccessoryPoller
from .web import create_app

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_config() -> dict:
    """Get configuration from environment variables."""
    default_db = str(Path.home() / ".find-my-timeline" / "locations.db")
    return {
        "min_interval": int(os.getenv("POLL_MIN_INTERVAL", "7")),
        "max_interval": int(os.getenv("POLL_MAX_INTERVAL", "10")),
        "db_path": os.getenv("DATABASE_PATH", default_db),
        "web_host": os.getenv("WEB_HOST", "127.0.0.1"),
        "web_port": int(os.getenv("WEB_PORT", "5000")),
    }


@click.group()
@click.version_option(version="0.1.0")
def main():
    """AirTag Timeline - track AirTag location and battery history."""


@main.command("import-keys")
def import_keys_cmd():
    """Export AirTag private keys from this Mac's local Find My cache (one-time)."""
    if not OWNED_BEACONS_DIR.exists():
        click.echo(f"No Find My accessory data found at {OWNED_BEACONS_DIR}", err=True)
        click.echo("Make sure Find My is set up on this Mac with at least one AirTag.", err=True)
        sys.exit(1)

    written = export_keys(source_dir=OWNED_BEACONS_DIR)
    if not written:
        click.echo("No AirTags found to export.")
        return

    click.echo(f"Exported {len(written)} accessory key(s) to {KEYS_DIR}:")
    for path in written:
        click.echo(f"  - {path.stem}")


@main.command()
@click.option("--username", "-u", help="Apple ID email address")
@click.option("--password", "-p", help="Apple ID password", hide_input=True)
def auth(username, password):
    """Authenticate with Apple and store the session."""
    username = username or os.getenv("ICLOUD_USERNAME") or click.prompt("Enter your Apple ID")
    password = password or os.getenv("ICLOUD_PASSWORD") or click.prompt(
        "Enter your password", hide_input=True
    )

    click.echo(f"Authenticating as {username}...")
    try:
        login(username, password)
        click.echo("Authentication successful! Session saved.")
    except AuthenticationError as e:
        click.echo(f"Authentication failed: {e}", err=True)
        sys.exit(1)


def _build_poller(config: dict) -> AccessoryPoller:
    """Load the saved session and accessory keys, and build a poller. Exits on failure."""
    try:
        account = load_session()
    except AuthenticationError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    accessories = load_keys()
    if not accessories:
        click.echo(
            f"No accessory keys found in {KEYS_DIR}. Run 'find-my-timeline import-keys' first.",
            err=True,
        )
        sys.exit(1)

    database = LocationDatabase(config["db_path"])
    return AccessoryPoller(
        account=account,
        accessories=accessories,
        database=database,
        min_interval=config["min_interval"],
        max_interval=config["max_interval"],
    )


@main.command()
def poll():
    """Start the location polling service."""
    config = get_config()
    poller = _build_poller(config)

    click.echo(f"Starting poller (interval: {config['min_interval']}-{config['max_interval']} minutes)")
    click.echo(f"Database: {config['db_path']}")

    poller.on_poll(lambda locs: click.echo(f"Recorded {len(locs)} location(s)") if locs else None)

    try:
        poller.start()
    except KeyboardInterrupt:
        click.echo("\nStopping poller...")


@main.command()
@click.option("--host", "-h", help="Host to bind to")
@click.option("--port", "-p", type=int, help="Port to bind to")
@click.option("--open/--no-open", "open_browser", default=True, help="Open the map in your browser")
def web(host, port, open_browser):
    """Start the web interface."""
    config = get_config()
    host = host or config["web_host"]
    port = port or config["web_port"]

    database = LocationDatabase(config["db_path"])
    app = create_app(database)

    url = f"http://{host}:{port}"
    click.echo(f"Starting web server at {url}")
    if open_browser:
        webbrowser.open(url)
    app.run(host=host, port=port, debug=False)


@main.command()
@click.option("--host", help="Web server host")
@click.option("--port", type=int, help="Web server port")
@click.option("--open/--no-open", "open_browser", default=True, help="Open the map in your browser")
def start(host, port, open_browser):
    """Start both the poller and the web interface."""
    config = get_config()
    host = host or config["web_host"]
    port = port or config["web_port"]

    poller = _build_poller(config)
    app = create_app(poller.database)

    url = f"http://{host}:{port}"
    click.echo("Starting AirTag Timeline")
    click.echo(f"  Polling interval: {config['min_interval']}-{config['max_interval']} minutes")
    click.echo(f"  Web interface: {url}")
    click.echo(f"  Database: {config['db_path']}")

    poller_thread = Thread(target=poller.start, kwargs={"setup_signals": False}, daemon=True)
    poller_thread.start()

    if open_browser:
        webbrowser.open(url)

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        poller.stop()


@main.command()
def stats():
    """Show database statistics."""
    config = get_config()
    db_path = Path(config["db_path"])

    if not db_path.exists():
        click.echo("No database found. Run 'poll' or 'start' first to begin collecting data.")
        return

    database = LocationDatabase(db_path)
    devices = database.get_devices()
    total = database.get_location_count()

    click.echo(f"Database: {db_path}")
    click.echo(f"Total locations: {total:,}")
    click.echo(f"Devices: {len(devices)}")

    for device in devices:
        count = database.get_location_count(device["id"])
        latest = database.get_latest_location(device["id"])
        latest_time = latest["timestamp"] if latest else "Never"

        click.echo(f"\n  {device['name']}")
        click.echo(f"    Locations: {count:,}")
        click.echo(f"    Last seen: {latest_time}")


@main.command()
def devices():
    """List all tracked AirTags."""
    config = get_config()
    db_path = Path(config["db_path"])

    if not db_path.exists():
        click.echo("No database found. Run 'poll' or 'start' first to begin collecting data.")
        return

    database = LocationDatabase(db_path)
    device_list = database.get_devices()

    if not device_list:
        click.echo("No devices found.")
        return

    click.echo(f"Tracked devices ({len(device_list)}):\n")
    for device in device_list:
        latest = database.get_latest_location(device["id"])
        click.echo(f"  {device['name']}")
        click.echo(f"    ID: {device['id']}")
        if latest:
            click.echo(f"    Last location: ({latest['latitude']:.6f}, {latest['longitude']:.6f})")
            click.echo(f"    Battery: {latest.get('battery_status') or 'Unknown'}")
            click.echo(f"    Last seen: {latest['timestamp']}")
        click.echo()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (all tests from Tasks 2–8, no failures)

- [ ] **Step 6: Verify the installed entry point works**

Run: `.venv/bin/find-my-timeline --help`
Expected: prints the command list (`import-keys`, `auth`, `poll`, `web`, `start`, `stats`, `devices`)

- [ ] **Step 7: Commit**

```bash
git add src/find_my_timeline/cli.py tests/test_cli.py
git commit -m "Wire up the find-my-timeline CLI"
```

---

### Task 9: Packaging verification and README

**Files:**
- Modify: `README.md` (replace Task 1's placeholder)

**Interfaces:**
- Consumes: nothing new — this task documents and verifies the finished package.
- Produces: nothing consumed by other tasks (final task).

- [ ] **Step 1: Verify the built wheel includes the HTML template**

This is the concrete regression test for the packaging fix called out in the
design doc (upstream's `template_folder="../../templates"` ships an empty
wheel).

Run:
```bash
.venv/bin/pip install build
.venv/bin/python -m build --wheel --outdir /tmp/fmt-wheel-check
unzip -l /tmp/fmt-wheel-check/*.whl | grep index.html
```
Expected: a line showing `find_my_timeline/templates/index.html` inside the wheel.

- [ ] **Step 2: Write the full `README.md`**

```markdown
# AirTag Timeline

Track AirTag location and battery history from Apple Find My, stored
locally in SQLite and viewable as a self-hosted map.

This started as a fork of
[kennym/find-my-timeline](https://github.com/kennym/find-my-timeline),
whose SQLite + Flask + Leaflet design this project reuses. Its auth/poll
layer is different: upstream uses `pyicloud`, which only supports Apple's
"Devices" API (iPhone/iPad/Mac/Watch/AirPods) and cannot see AirTags at
all. This project uses [`findmy`](https://github.com/malmeloo/FindMy.py)
instead, which implements the actual AirTag report-fetch-and-decrypt
protocol.

## How it works

AirTags don't report their location to your account directly — nearby
iPhones relay encrypted "sightings" to Apple, and only the AirTag's owner
can decrypt them, using a private key that lives on the Mac(s) where the
AirTag was set up. This tool:

1. Exports that private key, once, from this Mac's local Find My cache.
2. Logs into your Apple ID (the same account the AirTag is paired to).
3. Periodically asks Apple for encrypted sightings and decrypts them
   locally with the exported key.
4. Stores the decoded location + battery level in SQLite.
5. Serves a local map (Leaflet + OpenStreetMap tiles) over the history.

## Setup

```bash
git clone <this repo>
cd find-my-timeline
python3 -m venv .venv
.venv/bin/pip install -e .

# One-time: export your AirTags' private keys from this Mac
.venv/bin/find-my-timeline import-keys

# Log into the Apple ID your AirTags are paired to (prompts for 2FA)
.venv/bin/find-my-timeline auth

# Poll in the background and open the map
.venv/bin/find-my-timeline start
```

By default the map opens at `http://127.0.0.1:5000`.

## Commands

| Command | Description |
|---|---|
| `find-my-timeline import-keys` | One-time: export AirTag keys from this Mac |
| `find-my-timeline auth` | Log into Apple ID (2FA supported) |
| `find-my-timeline poll` | Run the polling loop only |
| `find-my-timeline web [--open/--no-open]` | Serve the map only |
| `find-my-timeline start` | Poll + serve the map together |
| `find-my-timeline devices` | List tracked AirTags |
| `find-my-timeline stats` | Show database statistics |

## Configuration

Environment variables (or a `.env` file in the working directory):

| Variable | Default | Description |
|---|---|---|
| `ICLOUD_USERNAME` | — | Apple ID email, used by `auth` if not passed as `--username` |
| `ICLOUD_PASSWORD` | — | Apple ID password; prompting interactively is recommended instead |
| `POLL_MIN_INTERVAL` | `7` | Minimum minutes between polls |
| `POLL_MAX_INTERVAL` | `10` | Maximum minutes between polls |
| `DATABASE_PATH` | `~/.find-my-timeline/locations.db` | SQLite database path |
| `WEB_HOST` | `127.0.0.1` | Web server bind address |
| `WEB_PORT` | `5000` | Web server port |

## Data locations

| Path | Contents |
|---|---|
| `~/.find-my-timeline/keys/*.json` | Exported AirTag private keys (`0600`) |
| `~/.find-my-timeline/account.json` | Apple session (`0600`) |
| `~/.find-my-timeline/locations.db` | Location + battery history |

## Security

- `keys/*.json` and `account.json` are sensitive. Anyone holding a key
  file can decrypt that AirTag's location history; `account.json` is an
  authenticated Apple session. Back them up like passwords, not like
  regular app data.
- The web UI has no authentication of its own. It binds to `127.0.0.1`
  by default — keep it that way unless you put a reverse proxy with
  auth in front of it.
- Location history is sensitive personal data. Protect `locations.db`
  accordingly.

## License

MIT — see `LICENSE`. Original SQLite/Flask/Leaflet design and copyright
from [kennym/find-my-timeline](https://github.com/kennym/find-my-timeline).
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Write full README with setup, commands, and security notes"
```

- [ ] **Step 4: Manual end-to-end verification (not automated — run once, by hand)**

1. `find-my-timeline import-keys` — confirm it reports exporting some
   number of AirTags (or a clear "no accessory data found" message if
   Find My isn't set up on this machine).
2. `find-my-timeline auth` — log in with the real Apple ID, complete 2FA.
3. `find-my-timeline start` — confirm the browser opens to the map,
   confirm the terminal logs "Recorded N location(s)" within one polling
   interval, confirm devices show up in the sidebar with a battery
   status.
4. `find-my-timeline stats` and `find-my-timeline devices` in a second
   terminal — confirm they reflect what `start` recorded.

This step has no code changes attached — it's the final sign-off that the
whole chain (key export → auth → poll → decrypt → store → serve) works
against real Apple servers and a real AirTag, which nothing in Tasks 1–8
can verify without live credentials.

---

## Self-Review Notes

- **Spec coverage:** every section of `2026-09-15-airtag-timeline-cli-design.md`
  maps to a task — architecture/package layout (Task 1, 7), `keys.py`/`import-keys`
  (Task 4), `auth.py` (Task 5), `poller.py` (Task 6), `database.py` schema
  (Task 3), `web.py`/`index.html` (Task 7), CLI surface (Task 8), dropped
  upstream files (never copied — Task 1 starts clean), setup docs (Task 9),
  error handling (covered inline in Tasks 4/5/6/8's implementations), testing
  (a test per task), security notes (`0600` in Tasks 4/5, documented in Task 9).
- **Type/signature consistency:** `LocationDatabase.record_location`'s
  `confidence`/`battery_status` params (Task 3) match what `poller.py`
  passes (Task 6) and what `web.py` returns unmodified via `dict(row)`
  (Task 7) and what `index.html`'s JS reads (`loc.confidence`,
  `loc.battery_status`) — checked across all four.
  `AccessoryPoller.__init__`'s `account`/`accessories` params (Task 6)
  match `_build_poller`'s call site in `cli.py` (Task 8). `export_keys`/
  `load_keys`/`KEYS_DIR`/`OWNED_BEACONS_DIR` (Task 4) match `cli.py`'s
  imports and usage (Task 8).
- **No placeholders:** every step has real code, not a description of code.
