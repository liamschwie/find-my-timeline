"""Export AirTag/accessory private keys from this Mac's local Find My cache."""

from pathlib import Path

from findmy import FindMyAccessory
from findmy.plist import list_accessories

# macOS 15+ keeps searchparty's records in the group container; older
# versions used ~/Library/com.apple.icloud.searchpartyd. Both layouts hold
# OwnedBeacons/ plus the BeaconNamingRecord/ and KeyAlignmentRecords/ dirs
# that findmy reads for accessory names and key alignment.
SEARCH_PATHS = [
    Path.home()
    / "Library/Group Containers/group.com.apple.icloud.searchpartyuseragent"
    / "Library/Storage",
    Path.home() / "Library/com.apple.icloud.searchpartyd",
]
KEYS_DIR = Path.home() / ".find-my-timeline" / "keys"


def find_search_path(candidates: list[Path] | None = None) -> Path | None:
    """Return the first searchparty storage directory that holds beacon records."""
    for path in candidates if candidates is not None else SEARCH_PATHS:
        if any(path.glob("OwnedBeacons/*.record")):
            return path
    return None


def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _write(accessories: list[FindMyAccessory], dest_dir: Path) -> list[Path]:
    """Write accessories as JSON key files, one per accessory, mode 0600."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.chmod(0o700)

    written = []
    for accessory in accessories:
        name = accessory.name or accessory.identifier
        dest_path = dest_dir / f"{_safe_filename(name)}.json"
        accessory.to_json(dest_path)
        dest_path.chmod(0o600)
        written.append(dest_path)

    return written


def export_keys(
    search_path: Path | None = None,
    dest_dir: Path = KEYS_DIR,
) -> list[Path]:
    """Export every accessory in this Mac's Find My cache as a JSON key file.

    Needs the BeaconStore key from the keychain, which macOS 15+ restricts to
    Apple-signed binaries -- see `import_from` for machines where that fails.

    Returns the list of JSON paths written.
    """
    search_path = search_path or find_search_path()
    if search_path is None:
        return []
    return _write(list_accessories(search_path=search_path), dest_dir)


def import_from(source: Path, dest_dir: Path = KEYS_DIR) -> list[Path]:
    """Import accessory keys exported elsewhere: a JSON file, a decrypted
    .plist, or a directory of either.

    Covers the machines where `export_keys` cannot run (macOS 15+ locks the
    BeaconStore key behind an Apple-only entitlement), so the keys are
    exported on another Mac or by a tool like OpenTagViewer and copied over.
    """
    paths = sorted(source.iterdir()) if source.is_dir() else [source]

    accessories = []
    for path in paths:
        if path.suffix == ".json":
            accessories.append(FindMyAccessory.from_json(path))
        elif path.suffix in (".plist", ".record"):
            try:
                accessories.append(FindMyAccessory.from_plist(path))
            except TypeError as exc:  # a list plist is still-encrypted ciphertext
                raise ValueError(
                    f"{path.name} is still encrypted; export it as a decrypted "
                    f".plist or a findmy .json key file first"
                ) from exc

    return _write(accessories, dest_dir)


def load_keys(keys_dir: Path = KEYS_DIR) -> list[FindMyAccessory]:
    """Load all previously exported accessory keys."""
    if not keys_dir.exists():
        return []
    return [FindMyAccessory.from_json(p) for p in sorted(keys_dir.glob("*.json"))]
