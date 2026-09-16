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
